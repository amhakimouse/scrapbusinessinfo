"""Tiny JSON file store for leads — no database needed for this volume."""
import json
import threading

import config
from scraper.models import Lead

_STORE_LOCK = threading.RLock()


def load_leads() -> list[Lead]:
    with _STORE_LOCK:
        if not config.LEADS_FILE.exists():
            return []
        raw = json.loads(config.LEADS_FILE.read_text())
        return [Lead(**item) for item in raw]


def save_leads(leads: list[Lead]) -> None:
    with _STORE_LOCK:
        config.LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.LEADS_FILE.write_text(
            json.dumps([lead.model_dump() for lead in leads], indent=2, ensure_ascii=False)
        )


def upsert_lead(new_lead: Lead) -> list[Lead]:
    """Add a lead, replacing any existing entry for the same domain. Returns the full updated list."""
    with _STORE_LOCK:
        leads = load_leads()
        leads = [l for l in leads if l.domain != new_lead.domain]
        leads.append(new_lead)
        save_leads(leads)
        return leads


def delete_leads(niche: str | None = None) -> tuple[list[Lead], int]:
    """Delete leads matching a niche, or all leads if niche is None or 'ALL'.
    
    Returns (remaining_leads, deleted_count).
    """
    with _STORE_LOCK:
        leads = load_leads()
        initial_count = len(leads)

        if not niche or niche.strip().upper() == "ALL" or niche.strip() == "*":
            remaining = []
        elif niche.strip().lower() == "seed list":
            remaining = [l for l in leads if l.source_keyword]
        else:
            target = niche.strip().lower()
            remaining = [
                l for l in leads
                if not (l.source_keyword and l.source_keyword.strip().lower() == target)
            ]

        deleted_count = initial_count - len(remaining)
        save_leads(remaining)
        return remaining, deleted_count


