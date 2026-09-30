"""FastAPI backend for the React sheet UI.

Run with:  uvicorn api:app --reload --port 8000
Then the React dev server (npm run dev) talks to it on localhost:8000.
"""
import asyncio
import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from scraper.discovery import load_seed_urls, discover_by_niche
from scraper.extractor import extract_lead, ExtractionError
from scraper.store import load_leads, upsert_lead, delete_leads
from scraper.utils import get_domain

app = FastAPI(title="Affiliate Marketer Leads API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite's default dev port
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


class DiscoverRequest(BaseModel):
    keyword: str
    mode: str = "fast"
    limit: int = 20
    start_page: int = 3  # skip pages 1 and 2 (big-brand results) by default
    has_email_only: bool = True


class BulkDiscoverRequest(BaseModel):
    keywords: list[str] = Field(..., min_length=1)
    mode: str = "fast"
    limit: int = 50
    start_page: int = 3
    has_email_only: bool = True
    max_workers: int = 8


def _clean_keywords_list(keywords_input: list[str] | str) -> list[str]:
    import re
    raw_list = []
    if isinstance(keywords_input, list):
        raw_list = keywords_input
    elif isinstance(keywords_input, str):
        trimmed = keywords_input.strip()
        if trimmed.startswith("[") and trimmed.endswith("]"):
            try:
                parsed = json.loads(trimmed)
                if isinstance(parsed, list):
                    raw_list = parsed
            except Exception:
                pass
        if not raw_list:
            raw_list = trimmed.replace("\n", ",").split(",")

    cleaned = []
    seen = set()
    for item in raw_list:
        s = str(item).strip().strip('"\'')
        # Strip leading numbers or bullets like "1. ", "- ", "* ", "• "
        s = re.sub(r'^\s*[\d\.\-\*\•\)]+\s*', '', s).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            cleaned.append(s)
    return cleaned


def _scrape_niche_worker(
    kw: str,
    limit: int,
    start_page: int,
    mode: str,
    has_email_only: bool,
    emit_fn=None,
):
    """Worker function to discover & scrape leads for a single niche."""
    def emit(event_type: str, **kwargs):
        if emit_fn:
            emit_fn(event_type, keyword=kw, **kwargs)

    emit("niche_start", message=f"Starting discovery for '{kw}'...")
    emit("searching", message=f"Searching DuckDuckGo for \"{kw}\" (starting page {start_page})...", start_page=start_page)

    candidate_limit = limit * 3 if has_email_only else limit
    try:
        discovered_urls = discover_by_niche(kw, limit=candidate_limit, start_page=start_page)
    except Exception as e:
        emit("niche_error", message=f"Discovery failed for {kw}: {e}")
        discovered_urls = []

    emit("discovery_done", total_candidates=len(discovered_urls))

    if not discovered_urls:
        emit("niche_done", scraped=0, with_email=0, total_candidates=0, message=f"No new candidates found for '{kw}'.")
        return {"keyword": kw, "scraped": 0, "with_email": 0, "candidates": 0}

    emit("start_scraping", total=len(discovered_urls))

    new_leads = []
    leads_with_email = []

    for i, url in enumerate(discovered_urls, start=1):
        domain = get_domain(url)
        emit("scraping", url=url, domain=domain, index=i, total=len(discovered_urls))
        try:
            lead = extract_lead(url, source_keyword=kw, mode=mode)
            upsert_lead(lead)
            new_leads.append(lead)
            has_email = bool(lead.emails)
            if has_email:
                leads_with_email.append(lead)

            emit(
                "lead_saved",
                domain=lead.domain,
                business_name=lead.business_name or lead.domain,
                emails=lead.emails or [],
                has_email=has_email,
                email_count=len(lead.emails or []),
                total_with_email=len(leads_with_email),
                scraped_count=len(new_leads),
                total=len(discovered_urls),
            )

            if has_email_only and len(leads_with_email) >= limit:
                break
            elif not has_email_only and len(new_leads) >= limit:
                break
        except ExtractionError as e:
            emit("lead_skipped", url=url, domain=domain, reason=str(e), scraped_count=len(new_leads), total=len(discovered_urls))
        except Exception as e:
            emit("lead_skipped", url=url, domain=domain, reason=f"Unexpected error: {e}", scraped_count=len(new_leads), total=len(discovered_urls))

    emit("niche_done", scraped=len(new_leads), with_email=len(leads_with_email), total_candidates=len(discovered_urls))
    return {
        "keyword": kw,
        "scraped": len(new_leads),
        "with_email": len(leads_with_email),
        "candidates": len(discovered_urls),
    }


@app.get("/api/health")
def health_check():
    """Diagnostic health check for the API, files, and paths."""
    leads_exist = config.LEADS_FILE.exists()
    leads = load_leads() if leads_exist else []
    seeds = load_seed_urls()

    return {
        "status": "ok",
        "leads_file_exists": leads_exist,
        "leads_file_path": str(config.LEADS_FILE.resolve()),
        "leads_count": len(leads),
        "seeds_file_exists": config.SEEDS_FILE.exists(),
        "seeds_file_path": str(config.SEEDS_FILE.resolve()),
        "seeds_count": len(seeds),
    }


@app.get("/api/leads")
def get_leads(has_email: bool | None = None, niche: str | None = None):
    leads = load_leads()
    if niche:
        cleaned_niche = niche.strip().lower()
        if cleaned_niche == "seed list":
            leads = [l for l in leads if not l.source_keyword]
        elif cleaned_niche != "all":
            leads = [
                l for l in leads
                if l.source_keyword and l.source_keyword.strip().lower() == cleaned_niche
            ]
    if has_email is True:
        leads = [l for l in leads if l.emails]
    elif has_email is False:
        leads = [l for l in leads if not l.emails]
    return [lead.model_dump() for lead in leads]


@app.get("/api/stats")
def get_stats():
    leads = load_leads()
    with_email = [l for l in leads if l.emails]
    return {
        "total": len(leads),
        "with_email": len(with_email),
        "no_email": len(leads) - len(with_email),
    }


@app.post("/api/discover")
def discover_leads(req: DiscoverRequest):
    """Discover candidate Amazon-affiliate sites for a keyword and scrape them."""
    kw = req.keyword.strip()
    if not kw:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")

    res = _scrape_niche_worker(
        kw=kw,
        limit=req.limit,
        start_page=req.start_page,
        mode=req.mode,
        has_email_only=req.has_email_only,
    )
    current_leads = load_leads()
    return {
        "keyword": kw,
        "discovered_urls_count": res["candidates"],
        "scraped_count": res["scraped"],
        "with_email_count": res["with_email"],
        "total_leads_count": len(current_leads),
        "leads": [l.model_dump() for l in current_leads],
    }


@app.post("/api/discover/bulk")
def discover_leads_bulk(req: BulkDiscoverRequest):
    """Asynchronously discover & scrape leads for multiple niches in parallel."""
    clean_kws = _clean_keywords_list(req.keywords)
    if not clean_kws:
        raise HTTPException(status_code=400, detail="At least one valid keyword is required")

    workers = min(len(clean_kws), max(1, req.max_workers))
    results = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                _scrape_niche_worker,
                kw=kw,
                limit=req.limit,
                start_page=req.start_page,
                mode=req.mode,
                has_email_only=req.has_email_only,
            )
            for kw in clean_kws
        ]
        for f in futures:
            try:
                res = f.result()
                if res:
                    results.append(res)
            except Exception as e:
                results.append({"keyword": "unknown", "scraped": 0, "with_email": 0, "candidates": 0, "error": str(e)})

    current_leads = load_leads()
    return {
        "total_niches": len(clean_kws),
        "niche_results": results,
        "total_scraped": sum(r.get("scraped", 0) for r in results),
        "total_with_email": sum(r.get("with_email", 0) for r in results),
        "total_leads_count": len(current_leads),
        "leads": [l.model_dump() for l in current_leads],
    }


@app.get("/api/discover/stream")
def discover_stream(
    keyword: str,
    limit: int = 50,
    start_page: int = 3,
    mode: str = "fast",
    has_email_only: bool = True,
):
    """SSE streaming endpoint for single keyword discovery and scraping events."""
    kw = keyword.strip()
    if not kw:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")

    def event_stream():
        event_q = queue.Queue()

        def emit(event_type: str, **kwargs):
            event_q.put({"type": event_type, **kwargs})

        def worker():
            try:
                res = _scrape_niche_worker(
                    kw=kw,
                    limit=limit,
                    start_page=start_page,
                    mode=mode,
                    has_email_only=has_email_only,
                    emit_fn=emit,
                )
                current_leads = load_leads()
                emit(
                    "done",
                    keyword=kw,
                    scraped=res["scraped"],
                    with_email=res["with_email"],
                    total_leads=len(current_leads),
                    leads=[l.model_dump() for l in current_leads],
                )
            except Exception as e:
                emit("error", message=str(e))
            finally:
                event_q.put(None)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        while True:
            item = event_q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/discover/bulk/stream")
def discover_bulk_stream(
    keywords: str = Query(..., description="Comma or newline separated list of keywords, or JSON array"),
    limit: int = 50,
    start_page: int = 3,
    mode: str = "fast",
    has_email_only: bool = True,
    max_workers: int = 8,
):
    """SSE streaming endpoint for concurrent multi-niche discovery and extraction."""
    import random
    import time
    clean_kws = _clean_keywords_list(keywords)

    if not clean_kws:
        raise HTTPException(status_code=400, detail="At least one valid keyword is required")

    def event_stream():
        event_q = queue.Queue()
        workers_count = min(len(clean_kws), max(1, max_workers))

        def emit(event_type: str, **kwargs):
            event_q.put({"type": event_type, **kwargs})

        emit(
            "bulk_start",
            total_niches=len(clean_kws),
            keywords=clean_kws,
            max_workers=workers_count,
            message=f"Starting bulk discovery for {len(clean_kws)} niches with {workers_count} parallel workers...",
        )

        niche_results = []
        results_lock = threading.Lock()

        def run_all_workers():
            with ThreadPoolExecutor(max_workers=workers_count) as executor:
                def task(niche_kw, idx):
                    # Slight initial jitter so threads stagger initial search engine requests
                    time.sleep(idx * 0.15)
                    res = _scrape_niche_worker(
                        kw=niche_kw,
                        limit=limit,
                        start_page=start_page,
                        mode=mode,
                        has_email_only=has_email_only,
                        emit_fn=emit,
                    )
                    with results_lock:
                        if res:
                            niche_results.append(res)

                futures = [executor.submit(task, kw, i) for i, kw in enumerate(clean_kws)]
                for f in futures:
                    try:
                        f.result()
                    except Exception as e:
                        emit("error", message=f"Worker error: {e}")

            current_leads = load_leads()
            emit(
                "bulk_done",
                total_niches=len(clean_kws),
                total_scraped=sum(r.get("scraped", 0) for r in niche_results),
                total_with_email=sum(r.get("with_email", 0) for r in niche_results),
                total_leads=len(current_leads),
                leads=[l.model_dump() for l in current_leads],
                message=f"Bulk discovery complete for {len(clean_kws)} niches!",
            )
            event_q.put(None)

        bg_thread = threading.Thread(target=run_all_workers, daemon=True)
        bg_thread.start()

        while True:
            item = event_q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



@app.delete("/api/leads")
def delete_leads_endpoint(niche: str | None = None, delete_all: bool = False):
    """Delete a selected niche sheet or all leads.

    - If delete_all is True or niche == 'ALL': deletes all leads.
    - If niche is provided (e.g. 'smart home' or 'Seed List'): deletes leads for that niche.
    """
    if not niche and not delete_all:
        raise HTTPException(status_code=400, detail="Must specify 'niche' or 'delete_all=true'")

    target_niche = "ALL" if delete_all else (niche or "").strip()
    remaining, deleted_count = delete_leads(target_niche)

    return {
        "status": "ok",
        "deleted_niche": target_niche,
        "deleted_count": deleted_count,
        "remaining_count": len(remaining),
        "leads": [l.model_dump() for l in remaining],
    }

