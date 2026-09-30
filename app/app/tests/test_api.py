import pytest
from httpx import AsyncClient, ASGITransport
import config
from scraper.models import Lead
from scraper.store import save_leads
from api import app

@pytest.mark.asyncio
async def test_api_health(tmp_path, monkeypatch):
    leads_file = tmp_path / "leads.json"
    seeds_file = tmp_path / "seeds.txt"
    seeds_file.write_text("https://test-site.com\n# Comment\nhttps://test-site-2.com\n")
    
    monkeypatch.setattr(config, "LEADS_FILE", leads_file)
    monkeypatch.setattr(config, "SEEDS_FILE", seeds_file)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["leads_file_exists"] is False
        assert data["seeds_file_exists"] is True
        assert data["seeds_count"] == 2

@pytest.mark.asyncio
async def test_api_leads_and_stats(tmp_path, monkeypatch):
    leads_file = tmp_path / "leads.json"
    monkeypatch.setattr(config, "LEADS_FILE", leads_file)

    lead1 = Lead(domain="site1.com", url="https://site1.com", emails=["test@site1.com"])
    lead2 = Lead(domain="site2.com", url="https://site2.com", emails=[])
    save_leads([lead1, lead2])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res_leads = await ac.get("/api/leads")
        assert res_leads.status_code == 200
        assert len(res_leads.json()) == 2

        # Test has_email=true filter
        res_email = await ac.get("/api/leads?has_email=true")
        assert res_email.status_code == 200
        assert len(res_email.json()) == 1
        assert res_email.json()[0]["domain"] == "site1.com"

        # Test has_email=false filter
        res_no_email = await ac.get("/api/leads?has_email=false")
        assert res_no_email.status_code == 200
        assert len(res_no_email.json()) == 1
        assert res_no_email.json()[0]["domain"] == "site2.com"

        res_stats = await ac.get("/api/stats")
        assert res_stats.status_code == 200
        stats = res_stats.json()
        assert stats["total"] == 2
        assert stats["with_email"] == 1
        assert stats["no_email"] == 1

@pytest.mark.asyncio
async def test_api_discover(monkeypatch, tmp_path):
    leads_file = tmp_path / "leads.json"
    monkeypatch.setattr(config, "LEADS_FILE", leads_file)

    # Mock discovery & extractor
    monkeypatch.setattr("api.discover_by_niche", lambda kw, limit=20, start_page=2: ["https://nicheblog.com/top-gadgets"])
    monkeypatch.setattr("api.extract_lead", lambda url, source_keyword=None, mode=None: Lead(
        domain="nicheblog.com",
        url=url,
        business_name="Niche Blog",
        emails=["editor@nicheblog.com"],
        source_keyword=source_keyword
    ))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Empty keyword should fail
        res_empty = await ac.post("/api/discover", json={"keyword": "   "})
        assert res_empty.status_code == 400

        # Valid keyword
        res = await ac.post("/api/discover", json={"keyword": "kitchen"})
        assert res.status_code == 200
        data = res.json()
        assert data["keyword"] == "kitchen"
        assert data["discovered_urls_count"] == 1
        assert data["scraped_count"] == 1
        assert data["with_email_count"] == 1
        assert len(data["leads"]) == 1
        assert data["leads"][0]["domain"] == "nicheblog.com"


@pytest.mark.asyncio
async def test_api_discover_stream(monkeypatch, tmp_path):
    import json
    leads_file = tmp_path / "leads.json"
    monkeypatch.setattr(config, "LEADS_FILE", leads_file)

    monkeypatch.setattr("api.discover_by_niche", lambda kw, limit=20, start_page=3: ["https://smallblog.com/gadgets"])
    monkeypatch.setattr("api.extract_lead", lambda url, source_keyword=None, mode=None: Lead(
        domain="smallblog.com",
        url=url,
        business_name="Small Blog",
        emails=["contact@smallblog.com"],
        source_keyword=source_keyword
    ))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/discover/stream?keyword=kitchen&limit=5&start_page=3")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]

        events = []
        for line in res.text.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        types = [e["type"] for e in events]
        assert "searching" in types
        assert "discovery_done" in types
        assert "start_scraping" in types
        assert "scraping" in types
        assert "lead_saved" in types
        assert "done" in types

        done_event = next(e for e in events if e["type"] == "done")
        assert done_event["scraped"] == 1
        assert done_event["with_email"] == 1


@pytest.mark.asyncio
async def test_api_bulk_discover(monkeypatch, tmp_path):
    leads_file = tmp_path / "leads.json"
    monkeypatch.setattr(config, "LEADS_FILE", leads_file)

    def mock_discover(kw, limit=20, start_page=3):
        return [f"https://{kw}-site.com/gadgets"]

    def mock_extract(url, source_keyword=None, mode=None):
        return Lead(
            domain=url.replace("https://", "").replace("/gadgets", ""),
            url=url,
            business_name=f"{source_keyword} Blog",
            emails=[f"contact@{source_keyword}.com"],
            source_keyword=source_keyword,
        )

    monkeypatch.setattr("api.discover_by_niche", mock_discover)
    monkeypatch.setattr("api.extract_lead", mock_extract)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Empty keywords should fail
        res_empty = await ac.post("/api/discover/bulk", json={"keywords": []})
        assert res_empty.status_code == 422 or res_empty.status_code == 400

        # Valid bulk discovery
        res = await ac.post("/api/discover/bulk", json={"keywords": ["coffee", "kitchen"], "max_workers": 8})
        assert res.status_code == 200
        data = res.json()
        assert data["total_niches"] == 2
        assert data["total_scraped"] == 2
        assert data["total_with_email"] == 2
        assert len(data["leads"]) == 2


@pytest.mark.asyncio
async def test_api_bulk_discover_stream(monkeypatch, tmp_path):
    import json
    leads_file = tmp_path / "leads.json"
    monkeypatch.setattr(config, "LEADS_FILE", leads_file)

    def mock_discover(kw, limit=20, start_page=3):
        return [f"https://{kw}-blog.com/review"]

    def mock_extract(url, source_keyword=None, mode=None):
        return Lead(
            domain=url.replace("https://", "").replace("/review", ""),
            url=url,
            business_name=f"{source_keyword} Site",
            emails=[f"info@{source_keyword}.com"],
            source_keyword=source_keyword,
        )

    monkeypatch.setattr("api.discover_by_niche", mock_discover)
    monkeypatch.setattr("api.extract_lead", mock_extract)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/discover/bulk/stream?keywords=coffee,tea&max_workers=8")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]

        events = []
        for line in res.text.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        types = [e["type"] for e in events]
        assert "bulk_start" in types
        assert "niche_start" in types
        assert "bulk_done" in types

        bulk_done = next(e for e in events if e["type"] == "bulk_done")
        assert bulk_done["total_niches"] == 2
        assert bulk_done["total_scraped"] == 2
        assert bulk_done["total_with_email"] == 2


@pytest.mark.asyncio
async def test_api_delete_leads(tmp_path, monkeypatch):
    leads_file = tmp_path / "leads.json"
    monkeypatch.setattr(config, "LEADS_FILE", leads_file)

    lead1 = Lead(domain="site1.com", url="https://site1.com", source_keyword="coffee")
    lead2 = Lead(domain="site2.com", url="https://site2.com", source_keyword="kitchen")
    save_leads([lead1, lead2])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Bad request when neither niche nor delete_all is specified
        res_bad = await ac.delete("/api/leads")
        assert res_bad.status_code == 400

        # Delete single niche
        res_niche = await ac.delete("/api/leads?niche=coffee")
        assert res_niche.status_code == 200
        data = res_niche.json()
        assert data["status"] == "ok"
        assert data["deleted_count"] == 1
        assert data["remaining_count"] == 1
        assert len(data["leads"]) == 1
        assert data["leads"][0]["domain"] == "site2.com"

        # Delete all leads
        res_all = await ac.delete("/api/leads?delete_all=true")
        assert res_all.status_code == 200
        data_all = res_all.json()
        assert data_all["deleted_count"] == 1
        assert data_all["remaining_count"] == 0
        assert len(data_all["leads"]) == 0



