import pytest
from pathlib import Path
import config
from scraper.discovery import (
    load_seed_urls,
    discover_by_niche,
    search_candidate_urls,
    _is_program_page,
    _is_large_publisher,
)
from scraper.models import Lead

def test_load_seed_urls(tmp_path, monkeypatch):
    seeds_file = tmp_path / "seeds.txt"
    seeds_file.write_text("""
    # Header comment
    https://seed1.com
    # inline comment
    https://seed2.com/page

    https://seed3.org
    """)
    monkeypatch.setattr(config, "SEEDS_FILE", seeds_file)

    urls = load_seed_urls()
    assert urls == ["https://seed1.com", "https://seed2.com/page", "https://seed3.org"]

def test_discover_by_niche_empty():
    assert discover_by_niche("") == []
    assert discover_by_niche("   ") == []

def test_is_program_page():
    assert _is_program_page("https://brand.com/pages/affiliate-program") is True
    assert _is_program_page("https://brand.com/pages/affiliate") is True
    assert _is_program_page("https://brand.com/partnership-program") is True
    assert _is_program_page("https://reviewblog.com/best-coffee-makers/") is False
    assert _is_program_page("https://reviewblog.com/affiliate-disclosure/") is False

def test_is_large_publisher():
    assert _is_large_publisher("futureplc.com") is True
    assert _is_large_publisher("tech.future.net.uk") is True
    assert _is_large_publisher("brands.hearstmags.com") is True
    assert _is_large_publisher("mysmallblog.com") is False
    assert _is_large_publisher("coffeeguyreviews.net") is False

def test_discover_by_niche_dedup_and_filter(monkeypatch):
    # Mock search_candidate_urls to return test candidates
    fake_results = {
        "best coffee review": [
            "https://coffeesite1.com/best-beans",
            "https://coffeesite1.com/other-page",            # duplicate domain
            "https://google.com/search",                      # excluded domain
            "https://healthline.com/nutrition/coffee",       # large publisher
            "https://sub.future.net.uk/coffee-reviews",       # media network parent
        ],
        "top coffee buying guide 2026": [
            "https://coffeesite2.com/reviews",
            "https://existing.com/page",                      # already known lead
        ],
        '"coffee" review "as an amazon associate"': [
            "https://coffeesite3.com/blog",
            "https://somebrand.com/pages/affiliate-program",  # program page filtered
        ],
        "best coffee tested recommended blog": [
            "https://coffeesite4.com/tested",
        ],
    }

    def fake_search(query, limit=None, start_page=None, max_pages=4):
        return fake_results.get(query, [])

    monkeypatch.setattr("scraper.discovery.search_candidate_urls", fake_search)
    monkeypatch.setattr("scraper.store.load_leads", lambda: [
        Lead(domain="existing.com", url="https://existing.com")
    ])

    results = discover_by_niche("coffee")
    assert "https://coffeesite1.com/best-beans" in results
    assert "https://coffeesite2.com/reviews" in results
    assert "https://coffeesite3.com/blog" in results
    assert "https://coffeesite4.com/tested" in results
    # Duplicate, program signup, large publishers, and excluded domains must not be in results
    assert "https://coffeesite1.com/other-page" not in results
    assert "https://somebrand.com/pages/affiliate-program" not in results
    assert not any("google.com" in r for r in results)
    assert not any("existing.com" in r for r in results)
    assert not any("healthline.com" in r for r in results)
    assert not any("future.net.uk" in r for r in results)

