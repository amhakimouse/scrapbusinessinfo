"""FastAPI backend for the React sheet UI.

Run with:  uvicorn api:app --reload --port 8000
Then the React dev server (npm run dev) talks to it on localhost:8000.
"""
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from scraper.discovery import load_seed_urls, discover_by_niche
from scraper.extractor import extract_lead, ExtractionError
from scraper.store import load_leads, upsert_lead, delete_leads

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

    candidate_limit = req.limit * 3 if req.has_email_only else req.limit
    discovered_urls = discover_by_niche(kw, limit=candidate_limit, start_page=req.start_page)
    new_leads = []
    leads_with_email = []

    for url in discovered_urls:
        try:
            lead = extract_lead(url, source_keyword=kw, mode=req.mode)
            upsert_lead(lead)
            new_leads.append(lead.model_dump())
            if lead.emails:
                leads_with_email.append(lead)
                if req.has_email_only and len(leads_with_email) >= req.limit:
                    break
            elif not req.has_email_only and len(new_leads) >= req.limit:
                break
        except ExtractionError:
            pass
        except Exception:  # noqa: BLE001
            pass

    current_leads = load_leads()
    return {
        "keyword": kw,
        "discovered_urls_count": len(discovered_urls),
        "scraped_count": len(new_leads),
        "with_email_count": len([l for l in new_leads if l.get("emails")]),
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
    """SSE streaming endpoint for real-time discovery and scraping events."""
    kw = keyword.strip()
    if not kw:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")

    def event_stream():
        def format_event(event_type: str, **kwargs) -> str:
            payload = json.dumps({"type": event_type, **kwargs})
            return f"data: {payload}\n\n"

        try:
            yield format_event(
                "searching",
                message=f"Searching DuckDuckGo for \"{kw}\" (skipping pages 1 & 2)...",
                keyword=kw,
                start_page=start_page,
            )

            candidate_limit = limit * 3 if has_email_only else limit
            discovered_urls = discover_by_niche(
                kw,
                limit=candidate_limit,
                start_page=start_page,
            )

            yield format_event(
                "discovery_done",
                total_candidates=len(discovered_urls),
                keyword=kw,
            )

            if not discovered_urls:
                current_leads = load_leads()
                yield format_event(
                    "done",
                    keyword=kw,
                    scraped=0,
                    with_email=0,
                    total_leads=len(current_leads),
                    leads=[l.model_dump() for l in current_leads],
                    message="No new candidate URLs discovered for this keyword.",
                )
                return

            yield format_event(
                "start_scraping",
                total=len(discovered_urls),
                keyword=kw,
            )

            new_leads = []
            leads_with_email = []

            for i, url in enumerate(discovered_urls, start=1):
                from scraper.utils import get_domain
                domain = get_domain(url)
                yield format_event(
                    "scraping",
                    url=url,
                    domain=domain,
                    index=i,
                    total=len(discovered_urls),
                )
                try:
                    lead = extract_lead(url, source_keyword=kw, mode=mode)
                    upsert_lead(lead)
                    new_leads.append(lead)
                    has_email = bool(lead.emails)
                    if has_email:
                        leads_with_email.append(lead)

                    yield format_event(
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
                    yield format_event(
                        "lead_skipped",
                        url=url,
                        domain=domain,
                        reason=str(e),
                        scraped_count=len(new_leads),
                        total=len(discovered_urls),
                    )
                except Exception as e:
                    yield format_event(
                        "lead_skipped",
                        url=url,
                        domain=domain,
                        reason=f"Unexpected error: {e}",
                        scraped_count=len(new_leads),
                        total=len(discovered_urls),
                    )

            current_leads = load_leads()
            yield format_event(
                "done",
                keyword=kw,
                scraped=len(new_leads),
                with_email=len(leads_with_email),
                total_leads=len(current_leads),
                leads=[l.model_dump() for l in current_leads],
            )
        except Exception as e:
            yield format_event("error", message=str(e))

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
