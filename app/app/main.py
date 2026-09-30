"""CLI to run the scraper.

Usage:
    python main.py                       # scrape every URL in data/seeds.txt
    python main.py --mode stealthy       # use the headless-browser fetcher
    python main.py --url https://x.com   # scrape one URL ad hoc
    python main.py --keyword "kitchen"   # discover & scrape affiliate sites by niche
"""
import argparse
import sys
import time

import config
from scraper.discovery import load_seed_urls, discover_by_niche
from scraper.extractor import extract_lead, ExtractionError
from scraper.store import upsert_lead, load_leads


def run(urls: list[str], mode: str, source_keyword: str | None = None) -> None:
    if not urls:
        print("[INFO] No URLs to scrape.")
        return

    print(f"\nStarting scrape run: {len(urls)} target URL(s) [mode={mode}]")
    if source_keyword:
        print(f"Source keyword: \"{source_keyword}\"")
    print("-" * 60)

    stats = {
        "attempted": len(urls),
        "with_email": 0,
        "no_email": 0,
        "failed": 0,
        "error": 0,
    }

    for i, url in enumerate(urls, start=1):
        print(f"[{i}/{len(urls)}] Scraping: {url}")
        try:
            lead = extract_lead(url, source_keyword=source_keyword, mode=mode)
            upsert_lead(lead)

            if lead.emails:
                stats["with_email"] += 1
                emails_str = ", ".join(lead.emails)
                print(f"  └─ SUCCESS (emails found): {emails_str}")
            else:
                stats["no_email"] += 1
                print("  └─ SUCCESS (no email found on homepage or contact page)")

            if lead.niche_signal:
                print(f"     Affiliate signal: \"{lead.niche_signal[:80]}...\"")
            if lead.about_snippet:
                print(f"     About: \"{lead.about_snippet[:80]}...\"")

        except ExtractionError as e:
            stats["failed"] += 1
            print(f"  └─ FETCH FAILED / BLOCKED: {e}")
        except Exception as e:  # noqa: BLE001 — keep batch running on unexpected error
            stats["error"] += 1
            print(f"  └─ UNEXPECTED ERROR: {type(e).__name__} — {e}")

        if i < len(urls):
            time.sleep(config.REQUEST_DELAY)

    print("-" * 60)
    print("Scrape Run Summary:")
    print(f"  • Total URLs attempted : {stats['attempted']}")
    print(f"  • Scraped WITH email   : {stats['with_email']}")
    print(f"  • Scraped NO email     : {stats['no_email']}")
    print(f"  • Blocked / Failed     : {stats['failed']}")
    if stats["error"] > 0:
        print(f"  • Unexpected errors    : {stats['error']}")

    total_leads = len(load_leads())
    print(f"\nResults saved to: {config.LEADS_FILE.resolve()}")
    print(f"Total leads in store: {total_leads}")

    if stats["attempted"] > 0 and stats["failed"] + stats["error"] == stats["attempted"]:
        print(
            "\n[WARNING] All target fetches failed or were blocked. Possible causes:\n"
            "  1. The target sites blocked fast HTTP requests -> Try running with: python main.py --mode stealthy\n"
            "  2. Missing browser drivers -> Run: scrapling install\n"
            "  3. Invalid or unreachable URLs in input list."
        )
    elif stats["with_email"] == 0 and stats["no_email"] > 0:
        print(
            "\n[NOTE] Sites were fetched successfully, but no direct email addresses were discovered\n"
            "in the homepage or linked contact/about pages. Social links or form-based contact may still exist in the sheet."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape affiliate marketer blogs & sites for contact info.")
    parser.add_argument("--mode", choices=["fast", "stealthy"], default=config.DEFAULT_FETCH_MODE,
                        help="Fetch mode: 'fast' (HTTP) or 'stealthy' (headless browser).")
    parser.add_argument("--url", help="Scrape a single URL ad hoc.")
    parser.add_argument("--keyword", help="Discover candidate affiliate marketer sites for a single niche keyword, then scrape them.")
    parser.add_argument("--keywords", help="Discover candidate affiliate marketer sites for multiple niche keywords (comma-separated or JSON list), running concurrently.")
    parser.add_argument("--workers", type=int, default=8, help="Number of concurrent worker threads for bulk scraping (default: 8).")
    parser.add_argument("--limit", type=int, default=100, help="Max number of leads to collect per keyword (default: 100).")
    parser.add_argument("--start-page", type=int, default=3, dest="start_page",
                        help="Which DuckDuckGo result page to start from (default: 3, skips pages 1 & 2 to target small businesses).")
    args = parser.parse_args()

    if args.url:
        target_urls = [args.url]
        run(target_urls, mode=args.mode)
    elif args.keywords:
        import json
        from concurrent.futures import ThreadPoolExecutor

        raw = args.keywords.strip()
        if raw.startswith("[") and raw.endswith("]"):
            try:
                kws = [str(k).strip() for k in json.loads(raw) if str(k).strip()]
            except Exception:
                kws = [k.strip() for k in raw.split(",") if k.strip()]
        else:
            kws = [k.strip() for k in raw.split(",") if k.strip()]

        if not kws:
            print("[ERROR] No valid keywords provided.")
            sys.exit(1)

        workers = min(len(kws), max(1, args.workers))
        print(f"\n[BULK] Starting asynchronous bulk discovery for {len(kws)} niche(s) using {workers} concurrent worker(s)...")

        def process_niche(kw):
            print(f"\n▶ Discovering affiliate marketer blogs for niche: \"{kw}\" (limit: {args.limit}, starting from page {args.start_page}) ...")
            discovered_urls = discover_by_niche(kw, limit=args.limit, start_page=args.start_page)
            if not discovered_urls:
                print(f"  [INFO] No new candidate URLs discovered for keyword \"{kw}\".")
                return 0
            print(f"  ✓ Discovered {len(discovered_urls)} candidate site(s) for \"{kw}\". Starting extraction...")
            run(discovered_urls, mode=args.mode, source_keyword=kw)
            return len(discovered_urls)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_niche, kw) for kw in kws]
            for f in futures:
                f.result()

        print(f"\n[BULK COMPLETE] Finished processing {len(kws)} niches. Total leads stored: {len(load_leads())}")

    elif args.keyword:
        print(f"\nDiscovering affiliate marketer blogs for niche: \"{args.keyword}\" (limit: {args.limit}, starting from page {args.start_page}) ...")
        discovered_urls = discover_by_niche(args.keyword, limit=args.limit, start_page=args.start_page)
        if not discovered_urls:
            print(
                f"[INFO] No new candidate URLs discovered for keyword \"{args.keyword}\".\n"
                "Possible reasons: all discovered sites are already present in data/leads.json, "
                "or search engine rate limits / no results returned."
            )
            sys.exit(0)
        print(f"Discovered {len(discovered_urls)} candidate site(s) not yet in leads database.")
        run(discovered_urls, mode=args.mode, source_keyword=args.keyword)
    else:
        # Seed list mode
        target_urls = load_seed_urls()
        if not target_urls:
            print(
                f"[ERROR] No seed URLs found to scrape in {config.SEEDS_FILE.resolve()}.\n"
                "Please add Amazon-affiliate site URLs (one per line, not commented out with '#')\n"
                "or discover leads by keyword: python main.py --keyword \"<niche>\""
            )
            sys.exit(1)
        run(target_urls, mode=args.mode)

