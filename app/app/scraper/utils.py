"""Small, dependency-free helpers: pulling emails/phones out of raw text,
detecting affiliate signals (Amazon Associates + generic FTC disclosures +
affiliate link patterns in HTML), and basic cleanup.
"""
import re
import tldextract

# Use the bundled public-suffix snapshot instead of fetching it over the
# network on first run — one less thing that can fail mid-scrape.
_tld_extractor = tldextract.TLDExtract(suffix_list_urls=())

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Detect common anti-scraper email obfuscations such as "name [at] domain [dot] com"
OBFUSCATED_EMAIL_RE = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s*(?:\[at\]|\(at\))\s*([a-zA-Z0-9.\-]+)\s*(?:\[dot\]|\(dot\)|\.)\s*([a-zA-Z]{2,})",
    re.IGNORECASE,
)

# Very common junk that matches the email regex but is never a real contact
EMAIL_BLOCKLIST_SUBSTRINGS = (
    "sentry.io", "wixpress.com", "example.com", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".webp", "godaddy.com", "schema.org", "fontawesome",
    "bootstrap", "yourdomain.com", "domain.com", "mywebsite.com",
)

PHONE_RE = re.compile(
    r"(?:(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4})"
)

# The boilerplate every legit Amazon affiliate site is legally required to show.
# Its presence is a strong, near-certain signal this is an Amazon affiliate.
AMAZON_DISCLOSURE_PATTERNS = [
    re.compile(r"as an amazon associate", re.I),
    re.compile(r"earns? (from|commission from) qualifying purchases", re.I),
    re.compile(r"amazon associates program", re.I),
    re.compile(r"participant in the amazon services", re.I),
]

# Generic affiliate / FTC disclosure patterns — many non-Amazon affiliates
# use these phrases to comply with FTC endorsement guidelines.
GENERIC_AFFILIATE_PATTERNS = [
    re.compile(r"this (post|page|article|site) (may )?contains? affiliate links?", re.I),
    re.compile(r"we (may )?earn (a )?commission", re.I),
    re.compile(r"affiliate disclosure", re.I),
    re.compile(r"compensation (from|through|via) (affiliate )?links", re.I),
    re.compile(r"I (may )?receive (a )?commission", re.I),
]

# Affiliate link URL patterns to look for in href attributes in raw HTML.
# These catch affiliate links even when there's no visible text disclosure.
AFFILIATE_LINK_PATTERNS = [
    re.compile(r"amazon\.[a-z.]+/.*[?&]tag=", re.I),        # Amazon tag parameter
    re.compile(r"amzn\.to/", re.I),                           # Amazon short links
    re.compile(r"[?&](aff|ref|hop|affid|affiliate)=", re.I),  # Generic affiliate params
    re.compile(r"shareasale\.com/", re.I),
    re.compile(r"linksynergy\.com/", re.I),
    re.compile(r"click\.linksynergy\.com/", re.I),
    re.compile(r"jdoqocy\.com/", re.I),
    re.compile(r"dpbolvw\.net/", re.I),
    re.compile(r"anrdoezrs\.net/", re.I),
    re.compile(r"commission-junction\.com/", re.I),
]

SOCIAL_DOMAINS = {
    "instagram.com": "instagram",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "tiktok.com": "tiktok",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "facebook.com": "facebook",
    "pinterest.com": "pinterest",
    "linkedin.com": "linkedin",
}


def extract_emails(text: str) -> list[str]:
    raw_text = text or ""
    # Standard email regex extraction
    found = {m.lower() for m in EMAIL_RE.findall(raw_text)}
    
    # Check for obfuscated emails (e.g. "contact [at] blog [dot] com")
    for match in OBFUSCATED_EMAIL_RE.finditer(raw_text):
        user, domain_name, tld = match.groups()
        found.add(f"{user}@{domain_name}.{tld}".lower())

    cleaned = [
        e for e in found
        if not any(bad in e for bad in EMAIL_BLOCKLIST_SUBSTRINGS)
        and not e.endswith((".js", ".css"))
    ]
    return sorted(cleaned)


def extract_phones(text: str) -> list[str]:
    candidates = PHONE_RE.findall(text or "")
    # keep only plausible phone-length matches, drop things like dates/years
    return sorted({c.strip() for c in candidates if 7 <= len(re.sub(r"\D", "", c)) <= 15})


def detect_affiliate_signal(text: str, page_html: str | None = None) -> str | None:
    """Detect affiliate presence in page text and optionally raw HTML.

    Checks three layers:
    1. Amazon Associates disclosure in visible text
    2. Generic FTC affiliate disclosures in visible text
    3. Affiliate link URL patterns in raw HTML (href attributes)

    Returns a short snippet showing the first matched signal, or None.
    """
    # Layer 1: Amazon-specific disclosures
    for pattern in AMAZON_DISCLOSURE_PATTERNS:
        m = pattern.search(text or "")
        if m:
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            return text[start:end].strip().replace("\n", " ")

    # Layer 2: Generic affiliate disclosures
    for pattern in GENERIC_AFFILIATE_PATTERNS:
        m = pattern.search(text or "")
        if m:
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            return text[start:end].strip().replace("\n", " ")

    # Layer 3: Affiliate link patterns in HTML source
    html = page_html or ""
    for pattern in AFFILIATE_LINK_PATTERNS:
        m = pattern.search(html)
        if m:
            return f"[affiliate link found: {m.group()[:80]}]"

    return None


def detect_amazon_affiliate_signal(text: str) -> str | None:
    """Legacy alias — delegates to detect_affiliate_signal()."""
    return detect_affiliate_signal(text)


def get_domain(url: str) -> str:
    ext = _tld_extractor(url)
    return ".".join(part for part in (ext.domain, ext.suffix) if part)


def classify_social_link(href: str) -> tuple[str, str] | None:
    for domain, label in SOCIAL_DOMAINS.items():
        if domain in href:
            return label, href
    return None
