"""Fetches one URL with Scrapling and turns the page into a Lead.

Two fetch modes, picked via config.DEFAULT_FETCH_MODE or per-call:
  - "fast":     plain HTTP via Fetcher — quick, works on most blogs.
  - "stealthy": real headless browser via StealthyFetcher — slower,
                but gets past JS-rendered pages and basic anti-bot checks.
"""
from urllib.parse import urljoin, urlparse

from scrapling.fetchers import Fetcher, StealthyFetcher

import config
from scraper.models import Lead
from scraper.utils import (
    extract_emails,
    extract_phones,
    detect_affiliate_signal,
    classify_social_link,
    get_domain,
)


class ExtractionError(Exception):
    pass


def _fetch(url: str, mode: str):
    if mode == "stealthy":
        page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
    else:
        page = Fetcher.get(url, stealthy_headers=True)

    if page is None or getattr(page, "status", 200) >= 400:
        raise ExtractionError(f"Bad response for {url} (status={getattr(page, 'status', 'n/a')})")
    return page


def _business_name(page) -> str | None:
    og_sites = page.css('meta[property="og:site_name"]')
    if og_sites:
        content = og_sites[0].attrib.get("content")
        if content and content.strip():
            return content.strip()
    titles = page.css("title")
    if titles:
        text = titles[0].get_all_text() if hasattr(titles[0], "get_all_text") else str(getattr(titles[0], "text", "") or "")
        text = text.strip()
        if text:
            parts = [p.strip() for p in text.split("|")]
            return parts[-1] if len(parts) > 1 else text
    return None


def _social_links(page) -> dict[str, str]:
    links = {}
    for a in page.css("a"):
        href = a.attrib.get("href") if hasattr(a, "attrib") else str(a)
        if not href or not isinstance(href, str):
            href = str(href or "")
        result = classify_social_link(href)
        if result:
            label, link = result
            links.setdefault(label, link)
    return links


CONTACT_PATH_HINTS = (
    "contact", "contact-us", "contact-me",
    "get-in-touch", "reach-out", "work-with-us", "work-with-me",
    "write-for-us", "advertise", "media-kit", "privacy-policy", "imprint",
)

CONTACT_TEXT_HINTS = (
    "contact", "contact us", "get in touch",
    "work with me", "work with us", "write for us", "advertise", "reach out",
)

ABOUT_PATH_HINTS = (
    "about", "about-us", "about-me", "our-story", "who-we-are",
    "about-the-blog", "about-the-site", "about-author", "meet-the-team",
)

ABOUT_TEXT_HINTS = (
    "about", "about us", "about me", "our story", "who we are",
    "about the blog", "about the site", "about the author", "meet the team",
)


def _find_contact_link(page, base_url: str) -> str | None:
    base_domain = get_domain(base_url).lower()
    for a in page.css("a"):
        href = a.attrib.get("href") if hasattr(a, "attrib") else str(a)
        if not href or not isinstance(href, str) or href.startswith("mailto:"):
            continue
        full_url = urljoin(base_url, href)
        if base_domain and get_domain(full_url).lower() != base_domain:
            continue
        href_lower = href.lower().split("?")[0]
        if any(hint in href_lower for hint in CONTACT_PATH_HINTS):
            return full_url
        anchor_text = a.get_all_text().strip().lower() if hasattr(a, "get_all_text") else str(getattr(a, "text", "") or "").strip().lower()
        if any(hint == anchor_text or hint in anchor_text for hint in CONTACT_TEXT_HINTS):
            return full_url
    return None


def _find_about_link(page, base_url: str) -> str | None:
    base_domain = get_domain(base_url).lower()
    for a in page.css("a"):
        href = a.attrib.get("href") if hasattr(a, "attrib") else str(a)
        if not href or not isinstance(href, str) or href.startswith("mailto:"):
            continue
        full_url = urljoin(base_url, href)
        if base_domain and get_domain(full_url).lower() != base_domain:
            continue
        href_lower = href.lower().split("?")[0]
        if any(hint in href_lower for hint in ABOUT_PATH_HINTS):
            return full_url
        anchor_text = a.get_all_text().strip().lower() if hasattr(a, "get_all_text") else str(getattr(a, "text", "") or "").strip().lower()
        if any(hint == anchor_text or hint in anchor_text for hint in ABOUT_TEXT_HINTS):
            return full_url
    return None


def _parse_llms_txt(raw: str | bytes | None) -> str | None:
    """Parse a site's llms.txt or .well-known/llms.txt content to extract its description."""
    if not raw:
        return None
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="ignore")
    else:
        text = str(raw)

    text_lower = text.strip().lower()
    # Reject HTML soft-404 error responses
    if text_lower.startswith("<!doctype") or "<html" in text_lower or "<body" in text_lower:
        return None

    lines = text.strip().splitlines()
    # 1. Look for blockquote description right after title (e.g. '> Brief description')
    for line in lines:
        s = line.strip()
        if s.startswith(">"):
            desc = s.lstrip(">").strip()
            if len(desc) >= 15:
                return desc[:300]

    # 2. Look for the first meaningful non-heading, non-bullet text paragraph
    for line in lines:
        s = line.strip()
        if (
            s
            and not s.startswith("#")
            and not s.startswith("-")
            and not s.startswith("*")
            and not s.startswith("http")
            and len(s) >= 20
        ):
            return s[:300]

    return None


def _extract_about_from_page(page) -> str | None:
    """Extract an informative site summary from an About page or Homepage."""
    if not page:
        return None

    # 1. Try og:description
    og_desc = page.css('meta[property="og:description"]')
    if og_desc:
        content = og_desc[0].attrib.get("content", "").strip()
        if content and len(content) > 20:
            return content[:300]

    # 2. Try standard meta description
    meta_desc = page.css('meta[name="description"]')
    if meta_desc:
        content = meta_desc[0].attrib.get("content", "").strip()
        if content and len(content) > 20:
            return content[:300]

    # 3. Look for site tagline / bio elements
    for selector in (".site-description", ".site-tagline", ".site-bio", ".about-me", ".widget_about", ".author-bio"):
        elements = page.css(selector)
        if elements:
            text = (
                elements[0].get_all_text().strip()
                if hasattr(elements[0], "get_all_text")
                else str(getattr(elements[0], "text", "") or "").strip()
            )
            if text and len(text) > 20:
                return text[:300]

    # 4. Search paragraphs in main content for informative intro sentences
    intro_keywords = (
        "welcome to", "i started", "we started", "our mission", "is a blog",
        "created this", "focuses on", "helps you", "all about", "passionate about",
        "dedicated to", "founded in", "about us", "about me", "my name is", "we are a",
        "our goal", "here at", "reviews and guides",
    )
    for p in page.css("main p, article p, .entry-content p, .about p, #about p, p"):
        p_text = (
            p.get_all_text().strip()
            if hasattr(p, "get_all_text")
            else str(getattr(p, "text", "") or "").strip()
        )
        p_lower = p_text.lower()
        if len(p_text) >= 25 and any(kw in p_lower for kw in intro_keywords):
            return p_text[:300]

    # 5. First substantial paragraph
    for p in page.css("main p, article p, .entry-content p, p"):
        p_text = (
            p.get_all_text().strip()
            if hasattr(p, "get_all_text")
            else str(getattr(p, "text", "") or "").strip()
        )
        if 35 <= len(p_text) <= 500 and not any(bad in p_text.lower() for bad in ("cookie", "privacy policy", "all rights reserved", "terms of")):
            return p_text[:300]

    return None


def _extract_site_about(url: str, page, mode: str, preloaded_about_page=None) -> str | None:
    """Extract a website-level description ("About the site/business").

    Checks in priority:
    1. /llms.txt on the root domain
    2. The dedicated /about page (preloaded or fetched)
    3. The root homepage (if url is a subpath article)
    4. Current page fallback
    """
    parsed = urlparse(url)
    root_url = f"{parsed.scheme}://{parsed.netloc}/"

    # Case 1: Check llms.txt on the root domain
    try:
        llms_url = urljoin(root_url, "/llms.txt")
        llms_page = _fetch(llms_url, mode)
        if llms_page:
            raw_text = getattr(llms_page, "body", None) or llms_page.get_all_text()
            llms_about = _parse_llms_txt(raw_text)
            if llms_about:
                return llms_about
    except Exception:
        pass

    # Case 2: Use preloaded About page if already fetched during contact check
    if preloaded_about_page:
        about = _extract_about_from_page(preloaded_about_page)
        if about:
            return about

    # Case 3: Find and fetch About page
    about_link = _find_about_link(page, url)
    about_candidates = [about_link] if about_link else [urljoin(root_url, "/about/"), urljoin(root_url, "/about-us/")]
    for cand in about_candidates:
        if not cand:
            continue
        try:
            about_page = _fetch(cand, mode)
            about = _extract_about_from_page(about_page)
            if about:
                return about
        except Exception:
            pass

    # Case 4: If original URL was a subpath (e.g. /best-review-2026/), check homepage
    if parsed.path and parsed.path not in ("/", ""):
        try:
            home_page = _fetch(root_url, mode)
            home_about = _extract_about_from_page(home_page)
            if home_about:
                return home_about
        except Exception:
            pass

    # Case 5: Fallback to current page
    return _extract_about_from_page(page)


def _page_emails(page) -> list[str]:
    mailto_emails = []
    for a in page.css('a[href^="mailto:"]'):
        href = a.attrib.get("href") if hasattr(a, "attrib") else str(a)
        if not href or not isinstance(href, str):
            href = str(href or "")
        cleaned = href.replace("mailto:", "").split("?")[0].strip().lower()
        if cleaned and "@" in cleaned:
            mailto_emails.append(cleaned)
    body_emails = extract_emails(page.get_all_text(ignore_tags=("script", "style")))
    return sorted(set(mailto_emails) | set(body_emails))


def extract_lead(url: str, source_keyword: str | None = None, mode: str | None = None) -> Lead:
    """Fetch `url` and return a populated Lead. Raises ExtractionError on failure.

    Extracts contact info, affiliate signals, and a website-level description
    (from /llms.txt, dedicated /about pages, or the root domain).
    """
    mode = mode or config.DEFAULT_FETCH_MODE
    page = _fetch(url, mode)

    full_text = page.get_all_text(ignore_tags=("script", "style"))
    page_html = str(page.html) if hasattr(page, "html") else ""

    emails = _page_emails(page)
    contact_url = None
    preloaded_about_page = None

    # Find contact / about pages if emails or site description needed
    contact_link = _find_contact_link(page, url)
    about_link = _find_about_link(page, url)

    candidates = [
        c for c in [
            contact_link,
            about_link,
            urljoin(url, "/contact/"),
            urljoin(url, "/about/"),
            urljoin(url, "/about-us/"),
        ] if c
    ]

    for cand in candidates:
        if emails and preloaded_about_page:
            break
        try:
            sub_page = _fetch(cand, mode)
            if not emails:
                found_emails = _page_emails(sub_page)
                if found_emails:
                    emails = found_emails
                    contact_url = cand

            if not preloaded_about_page and any(hint in cand.lower() for hint in ABOUT_PATH_HINTS):
                preloaded_about_page = sub_page
        except ExtractionError:
            pass

    about_snippet = _extract_site_about(url, page, mode, preloaded_about_page=preloaded_about_page)

    lead = Lead(
        domain=get_domain(url),
        url=url,
        business_name=_business_name(page),
        emails=emails,
        phones=extract_phones(full_text),
        social_links=_social_links(page),
        niche_signal=detect_affiliate_signal(full_text, page_html),
        about_snippet=about_snippet,
        contact_url=contact_url,
        source_keyword=source_keyword,
        status="scraped" if emails else "no_email",
    )
    return lead

