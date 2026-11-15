import pytest
from scraper.extractor import (
    _parse_llms_txt,
    _find_about_link,
    _extract_about_from_page,
    _extract_site_about,
    extract_lead,
)

class MockElement:
    def __init__(self, tag="div", text="", attrib=None):
        self.tag = tag
        self._text = text
        self.attrib = attrib or {}

    def get_all_text(self, ignore_tags=None):
        return self._text


class MockPage:
    def __init__(self, css_map=None, text="", status=200, body=None, html=""):
        self.css_map = css_map or {}
        self._text = text
        self.status = status
        self.body = body or text.encode("utf-8")
        self.html = html

    def css(self, selector):
        for k, v in self.css_map.items():
            if selector in k or k in selector:
                return v
        return []

    def get_all_text(self, ignore_tags=None):
        return self._text


def test_parse_llms_txt_blockquote():
    content = """# Smart Living Blog
> Smart Living is an independent review site dedicated to helping homeowners automate their spaces with smart tech.

## Guides
- [Thermostats](/thermostats)
"""
    result = _parse_llms_txt(content)
    assert result is not None
    assert "Smart Living is an independent review site" in result


def test_parse_llms_txt_paragraph():
    content = """# Coffee Gear Lab

Coffee Gear Lab provides in-depth espresso machine reviews, brewing tutorials, and gear recommendations for home baristas.

## Latest Posts
- [Top Grinders 2026](/grinders)
"""
    result = _parse_llms_txt(content)
    assert result is not None
    assert "Coffee Gear Lab provides in-depth espresso machine reviews" in result


def test_parse_llms_txt_reject_html_error():
    html_error = """<!DOCTYPE html>
<html>
<head><title>404 Not Found</title></head>
<body><h1>Page Not Found</h1></body>
</html>"""
    assert _parse_llms_txt(html_error) is None


def test_find_about_link():
    mock_page = MockPage(css_map={
        "a": [
            MockElement("a", "Home", {"href": "/"}),
            MockElement("a", "Blog", {"href": "/blog/"}),
            MockElement("a", "Our Story", {"href": "/about-us/"}),
            MockElement("a", "External", {"href": "https://other.com/about"}),
        ]
    })
    link = _find_about_link(mock_page, "https://myblog.com/post-1")
    assert link == "https://myblog.com/about-us/"


def test_extract_about_from_page_og_desc():
    mock_page = MockPage(css_map={
        'meta[property="og:description"]': [
            MockElement("meta", attrib={"content": "Eco Home Guide is a sustainable living blog focusing on zero-waste living and green tech."})
        ]
    })
    about = _extract_about_from_page(mock_page)
    assert about is not None
    assert "Eco Home Guide is a sustainable living blog" in about


def test_extract_about_from_page_intro_paragraph():
    mock_page = MockPage(css_map={
        "main p, article p, .entry-content p, .about p, #about p, p": [
            MockElement("p", "Welcome to TechCraft, a blog I started in 2024 to share DIY automation tips and gadget reviews for everyday makers.")
        ]
    })
    about = _extract_about_from_page(mock_page)
    assert about is not None
    assert "Welcome to TechCraft, a blog I started" in about


def test_extract_site_about_llms_txt_priority(monkeypatch):
    # Mock _fetch to return llms.txt when requested
    def mock_fetch(url, mode):
        if url.endswith("/llms.txt"):
            return MockPage(body=b"# AutoBlog\n> AutoBlog is a website helping small creators automate content.")
        return MockPage()

    monkeypatch.setattr("scraper.extractor._fetch", mock_fetch)
    about = _extract_site_about("https://autoblog.io/reviews/gadgets-2026", MockPage(), "fast")
    assert about is not None
    assert "AutoBlog is a website helping small creators" in about
