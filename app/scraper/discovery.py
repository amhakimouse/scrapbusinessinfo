"""Turns a list of seed sources into candidate URLs to scrape.

Two ways to feed the scraper, use whichever fits how you already find leads:

1. SEED LIST (recommended, default) — you drop known affiliate-marketer
   site URLs into data/seeds.txt (one per line). You already have good
   ways to find these manually: Amazon's "onsite associates" storefront
   links, niche blog directories, YouTube "as an Amazon Associate..."
   video descriptions, review-roundup Google searches you do by hand, etc.
   This is the most reliable and lowest-risk approach.

2. KEYWORD SEARCH (optional, off by default) — search_candidate_urls()
   scrapes DuckDuckGo's HTML results page for a keyword like
   "best smart home review". This is here for convenience but search
   engines' ToS generally restrict automated querying, so: keep volumes
   low, add delay, and prefer method 1 for any serious volume of outreach.

The search queries are designed to find actual affiliate marketer blogs
and product review content — NOT affiliate program directories, network
landing pages, or brand partnership signup pages.
"""
import random
import threading
import time
from urllib.parse import quote_plus

from scrapling.fetchers import Fetcher

import config
from scraper.utils import get_domain

_SEARCH_LOCK = threading.Lock()
_LAST_SEARCH_TIME = 0.0
_MIN_SEARCH_INTERVAL = 0.8  # seconds between DuckDuckGo search requests to prevent anti-bot throttle


def _rate_limited_ddg_post(url: str, data: dict):
    global _LAST_SEARCH_TIME
    with _SEARCH_LOCK:
        now = time.time()
        elapsed = now - _LAST_SEARCH_TIME
        if elapsed < _MIN_SEARCH_INTERVAL:
            time.sleep(_MIN_SEARCH_INTERVAL - elapsed)
        try:
            return Fetcher.post(url, data=data, stealthy_headers=True)
        finally:
            _LAST_SEARCH_TIME = time.time()


def _rate_limited_ddg_get(url: str):
    global _LAST_SEARCH_TIME
    with _SEARCH_LOCK:
        now = time.time()
        elapsed = now - _LAST_SEARCH_TIME
        if elapsed < _MIN_SEARCH_INTERVAL:
            time.sleep(_MIN_SEARCH_INTERVAL - elapsed)
        try:
            return Fetcher.get(url, stealthy_headers=True)
        finally:
            _LAST_SEARCH_TIME = time.time()


# Domains to exclude from discovered affiliate leads:
# search engines, social platforms, affiliate networks/directories,
# affiliate SaaS tools, major retailers, large publishers, and meta-content sites.
EXCLUDED_DISCOVERY_DOMAINS = {
    # Search engines
    "amazon.com", "duckduckgo.com", "google.com", "bing.com", "yahoo.com",
    # Social platforms
    "youtube.com", "pinterest.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "linkedin.com", "tiktok.com", "reddit.com",
    # Reference / encyclopedias
    "wikipedia.org",
    # Affiliate networks & directories (the main offenders)
    "shareasale.com", "cj.com", "impact.com", "partnerstack.com",
    "clickbank.com", "rakuten.com", "awin.com", "flexoffers.com",
    "uppromote.com", "getlasso.co", "algorift.io", "affnext.com",
    "clickwire.io", "ainfluencer.com", "evolup.com",
    "refersion.com", "tapfiliate.com", "postaffiliatepro.com",
    "commission.academy", "authorityhacker.com",
    # Major retailers (we want bloggers reviewing products, not retailers)
    "walmart.com", "target.com", "ebay.com", "bestbuy.com", "etsy.com",
    "homedepot.com", "lowes.com", "wayfair.com", "overstock.com",
    "costco.com", "samsclub.com", "kohls.com", "macys.com",
    # Marketing / SEO tool sites (meta-content about affiliate marketing)
    "later.com", "semrush.com", "ahrefs.com", "moz.com",
    "influencermarketinghub.com", "bloggerspassion.com",
    "nichesiteu.com", "nicheblogzone.com",
    "hubspot.com", "neilpatel.com",
    # Large health / medical publishers
    "healthline.com", "medicalnewstoday.com", "verywellfit.com", "verywellmind.com",
    "verywellhealth.com", "webmd.com", "mayoclinic.org", "clevelandclinic.org",
    "hopkinsmedicine.org", "everydayhealth.com", "health.com", "sleepfoundation.org",
    "sleep.org", "self.com", "prevention.com", "shape.com",
    "womenshealthmag.com", "menshealth.com",
    # Large tech / consumer-electronics review publishers
    "tomsguide.com", "techradar.com", "pcmag.com", "cnet.com", "zdnet.com",
    "wirecutter.com", "rtings.com", "digitaltrends.com", "theverge.com",
    "engadget.com", "wired.com", "reviewed.com", "safewise.com", "security.org",
    # Large home / lifestyle publishers
    "goodhousekeeping.com", "rd.com", "bhg.com", "thespruce.com",
    "thespruceeats.com", "thesprucepets.com", "hgtv.com", "bobvila.com",
    "thisoldhouse.com", "familyhandyman.com", "countryliving.com",
    "housebeautiful.com", "realsimple.com", "marthastewart.com",
    # Large food / recipe publishers
    "allrecipes.com", "foodnetwork.com", "seriouseats.com", "thekitchn.com",
    "epicurious.com", "tastingtable.com", "delish.com", "tasteofhome.com",
    # Large fashion / beauty publishers
    "cosmopolitan.com", "elle.com", "vogue.com", "glamour.com", "popsugar.com",
    # Large finance publishers
    "investopedia.com", "bankrate.com", "nerdwallet.com", "creditkarma.com",
    "moneycrashers.com", "thebalancemoney.com", "kiplinger.com",
    # Large outdoor / sports publishers
    "outdoorlife.com", "fieldandstream.com", "gearjunkie.com",
    "outsideonline.com", "backpacker.com",
    # Large news / media publishers
    "businessinsider.com", "forbes.com", "entrepreneur.com", "inc.com",
    "consumerreports.org", "usatoday.com", "nytimes.com", "washingtonpost.com",
    "guardian.com", "telegraph.co.uk", "mirror.co.uk", "dailymail.co.uk",
    "cbsnews.com", "abcnews.com", "nbcnews.com", "foxnews.com",
    # Pet publishers
    "petmd.com", "akc.org", "aspca.org",
}

# Parent domain suffixes belonging to large media network groups.
# Catches sub-brands not individually listed above (e.g. future.net.uk sites).
_MEDIA_NETWORK_PARENTS = {
    "futureplc.com", "future.net.uk",   # TechRadar, Tom's Guide, PC Gamer, etc.
    "dotdash.com", "dotdashmdp.com",    # Investopedia, Verywell, Spruce, etc.
    "hearstmags.com",                   # Good Housekeeping, Cosmopolitan, etc.
    "condenast.com",                    # Vogue, Wired, GQ, etc.
    "meredith.com",                     # People, Real Simple, etc.
    "ziffmedia.com",                    # PCMag, Mashable, etc.
}

# URL path segments that indicate an affiliate program signup page,
# not a product review article written by an affiliate marketer.
EXCLUDED_URL_PATH_PATTERNS = (
    "/affiliate-program", "/affiliate-programs", "/pages/affiliate",
    "/partnership-program", "/become-an-affiliate", "/join-affiliate",
    "/referral-program", "/pages/partnership", "/partner-program",
)


def _is_program_page(url: str) -> bool:
    """Return True if the URL path suggests an affiliate program signup page."""
    path = url.lower().split("?")[0]
    return any(pattern in path for pattern in EXCLUDED_URL_PATH_PATTERNS)


def _is_large_publisher(domain: str) -> bool:
    """Return True if the domain belongs to a known large media network group.

    Catches sub-brands of media conglomerates that aren't individually listed
    in EXCLUDED_DISCOVERY_DOMAINS — e.g. sites hosted under future.net.uk.
    """
    dl = domain.lower()
    return any(dl == p or dl.endswith("." + p) for p in _MEDIA_NETWORK_PARENTS)


def load_seed_urls() -> list[str]:
    """Read data/seeds.txt — one URL per line, '#' comments ignored."""
    if not config.SEEDS_FILE.exists():
        return []
    urls = []
    for line in config.SEEDS_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def _extract_page_urls(page) -> list[str]:
    """Extract external URLs from a DuckDuckGo search result page."""
    urls = []
    if not page:
        return urls
    for a in page.css("a"):
        href = a.attrib.get("href") if hasattr(a, "attrib") else ""
        if not href or not isinstance(href, str):
            href = str(href or "")
        if href.startswith("http") and "duckduckgo.com" not in href:
            if href not in urls:
                urls.append(href)
    return urls


def _find_next_form(page) -> dict[str, str] | None:
    """Find and extract input parameters for the 'Next Page >' form in DuckDuckGo Lite."""
    if not page:
        return None
    for f in page.css("form"):
        inputs = {
            inp.attrib.get("name"): inp.attrib.get("value", "")
            for inp in f.css("input")
            if inp.attrib.get("name")
        }
        submit_vals = [inp.attrib.get("value", "") for inp in f.css("input")]
        # Ensure this is the Next page form (not the Search or Previous page form)
        if any("Next" in str(v) for v in submit_vals) and "s" in inputs and "vqd" in inputs:
            return inputs
    return None


def search_candidate_urls(
    keyword: str,
    limit: int | None = None,
    start_page: int | None = None,
    max_pages: int = 4,
) -> list[str]:
    """Best-effort keyword discovery via DuckDuckGo HTML search.
    Returns a de-duplicated list of result URLs. See module docstring
    for the caveats — use sparingly and prefer a curated seed list.

    start_page: which DuckDuckGo result page to begin from.
                Default=3 skips pages 1 and 2 (big-brand / top-SEO results)
                so you surface smaller, newer blogs instead.
    max_pages:  maximum number of pages to fetch per query after start_page.
    """
    limit = limit or config.SEARCH_RESULTS_PER_KEYWORD
    if start_page is None:
        start_page = config.SEARCH_START_PAGE

    urls: list[str] = []
    search_url = "https://lite.duckduckgo.com/lite/"

    try:
        page = _rate_limited_ddg_post(search_url, data={"q": keyword})
    except Exception:
        try:
            get_url = f"https://html.duckduckgo.com/html/?q={quote_plus(keyword)}"
            page = _rate_limited_ddg_get(get_url)
        except Exception:
            return []

    curr_page = 1
    # Only collect URLs if we are already at or past the start_page
    if curr_page >= start_page:
        for u in _extract_page_urls(page):
            if u not in urls:
                urls.append(u)

    # Page forward through DuckDuckGo using its stateful form tokens (vqd, s, dc)
    target_end_page = start_page + max_pages - 1
    while curr_page < target_end_page and len(urls) < limit:
        next_form = _find_next_form(page)
        if not next_form:
            break

        curr_page += 1
        time.sleep(config.REQUEST_DELAY + random.uniform(0.3, 0.8))

        try:
            page = _rate_limited_ddg_post(search_url, data=next_form)
        except Exception:
            break

        if curr_page >= start_page:
            for u in _extract_page_urls(page):
                if u not in urls:
                    urls.append(u)
                if len(urls) >= limit:
                    break

    return urls



def discover_by_niche(
    keyword: str,
    limit: int | None = None,
    start_page: int | None = None,
    progress_cb=None,
) -> list[str]:
    """Find candidate affiliate marketer blogs/articles for a given niche keyword.

    Generates 4 query variants targeting product review content written by
    affiliate marketers (not affiliate program directories or network pages).
    Queries DuckDuckGo starting from `start_page` (default: config.SEARCH_START_PAGE,
    which skips the first pages so big-brand / large-publisher results are avoided).
    Dedupes candidates by domain, filters out excluded domains, large publishers,
    and program signup pages, and excludes domains already present in data/leads.json.

    progress_cb: optional callable(url, domain) invoked for every candidate accepted.
                 Used by the SSE streaming endpoint to push real-time events.
    """
    cleaned_kw = keyword.strip()
    if not cleaned_kw:
        return []

    if start_page is None:
        start_page = config.SEARCH_START_PAGE

    queries = [
        f"best {cleaned_kw} review",
        f"top {cleaned_kw} buying guide 2026",
        f'"{cleaned_kw}" review "as an amazon associate"',
        f"best {cleaned_kw} tested recommended blog",
    ]

    discovered_urls: list[str] = []
    seen_domains = set(EXCLUDED_DISCOVERY_DOMAINS)

    for query in queries:
        if limit and len(discovered_urls) >= limit:
            break
        # Ask for 3× the remaining budget per query so domain deduplication
        # and program-page filtering don't starve later queries.
        remaining = (limit - len(discovered_urls)) if limit else None
        per_query_limit = (remaining * 3) if remaining else None
        urls = search_candidate_urls(query, limit=per_query_limit, start_page=start_page)
        for url in urls:
            domain = get_domain(url).lower()
            if not domain or domain in seen_domains:
                continue
            if _is_program_page(url):
                continue
            if _is_large_publisher(domain):
                continue
            seen_domains.add(domain)
            discovered_urls.append(url)
            if progress_cb:
                progress_cb(url, domain)
            if limit and len(discovered_urls) >= limit:
                return discovered_urls

    # Graceful fallback: if start_page > 1 returned 0 candidates, search from page 1
    if not discovered_urls and start_page and start_page > 1:
        for query in queries:
            if limit and len(discovered_urls) >= limit:
                break
            remaining = (limit - len(discovered_urls)) if limit else None
            per_query_limit = (remaining * 3) if remaining else None
            urls = search_candidate_urls(query, limit=per_query_limit, start_page=1)
            for url in urls:
                domain = get_domain(url).lower()
                if not domain or domain in seen_domains:
                    continue
                if _is_program_page(url):
                    continue
                if _is_large_publisher(domain):
                    continue
                seen_domains.add(domain)
                discovered_urls.append(url)
                if progress_cb:
                    progress_cb(url, domain)
                if limit and len(discovered_urls) >= limit:
                    return discovered_urls

    return discovered_urls



