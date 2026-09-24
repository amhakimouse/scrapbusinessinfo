import pytest
from pathlib import Path
import config
from scraper.models import Lead
from scraper.store import load_leads, save_leads, upsert_lead, delete_leads

def test_store_save_load_upsert(tmp_path, monkeypatch):
    test_file = tmp_path / "test_leads.json"
    monkeypatch.setattr(config, "LEADS_FILE", test_file)

    assert load_leads() == []

    lead1 = Lead(domain="site1.com", url="https://site1.com", emails=["a@site1.com"])
    lead2 = Lead(domain="site2.com", url="https://site2.com", emails=["b@site2.com"])
    save_leads([lead1, lead2])

    loaded = load_leads()
    assert len(loaded) == 2
    assert {l.domain for l in loaded} == {"site1.com", "site2.com"}

    # Upsert with updated info for site1
    lead1_updated = Lead(domain="site1.com", url="https://site1.com", emails=["new@site1.com"])
    upsert_lead(lead1_updated)

    reloaded = load_leads()
    assert len(reloaded) == 2
    site1 = next(l for l in reloaded if l.domain == "site1.com")
    assert site1.emails == ["new@site1.com"]


def test_store_delete_leads(tmp_path, monkeypatch):
    test_file = tmp_path / "test_leads.json"
    monkeypatch.setattr(config, "LEADS_FILE", test_file)

    lead1 = Lead(domain="site1.com", url="https://site1.com", source_keyword="coffee")
    lead2 = Lead(domain="site2.com", url="https://site2.com", source_keyword="kitchen")
    lead3 = Lead(domain="site3.com", url="https://site3.com", source_keyword=None)
    save_leads([lead1, lead2, lead3])

    # Delete specific niche
    remaining, count = delete_leads("coffee")
    assert count == 1
    assert len(remaining) == 2
    assert {l.domain for l in remaining} == {"site2.com", "site3.com"}

    # Delete Seed List
    remaining, count = delete_leads("Seed List")
    assert count == 1
    assert len(remaining) == 1
    assert remaining[0].domain == "site2.com"

    # Delete all
    remaining, count = delete_leads("ALL")
    assert count == 1
    assert len(remaining) == 0

