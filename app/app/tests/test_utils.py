import pytest
from scraper.utils import (
    extract_emails,
    extract_phones,
    detect_affiliate_signal,
    detect_amazon_affiliate_signal,
    classify_social_link,
    get_domain,
)

def test_extract_emails():
    text = """
    Contact our team at hello@example-affiliate.com or support@nichegadgets.io.
    Do not match invalid sentry@sentry.io or image@example.com/pic.png or test@wixpress.com.
    """
    emails = extract_emails(text)
    assert "hello@example-affiliate.com" in emails
    assert "support@nichegadgets.io" in emails
    assert not any("sentry.io" in e for e in emails)
    assert not any("wixpress.com" in e for e in emails)
    assert not any("example.com" in e for e in emails)

def test_extract_emails_obfuscated():
    text = "Write to us at editor [at] reviewzone [dot] com or outreach (at) coffeegear.org."
    emails = extract_emails(text)
    assert "editor@reviewzone.com" in emails
    assert "outreach@coffeegear.org" in emails

def test_extract_phones():
    text = "Call us at +1 (555) 234-5678 or 555-876-5432. Year 2026 is not a phone."
    phones = extract_phones(text)
    assert len(phones) >= 1
    assert any("555" in p for p in phones)

def test_detect_affiliate_signal_amazon():
    text = "Welcome to our blog. As an Amazon Associate, I earn from qualifying purchases made through links."
    signal = detect_affiliate_signal(text)
    assert signal is not None
    assert "Amazon Associate" in signal

def test_detect_affiliate_signal_generic():
    text = "Welcome to our blog! This post contains affiliate links. If you buy something we may earn a commission."
    signal = detect_affiliate_signal(text)
    assert signal is not None
    assert "affiliate link" in signal.lower() or "commission" in signal.lower()

def test_detect_affiliate_signal_html_amazon_tag():
    signal = detect_affiliate_signal("", page_html='<a href="https://amazon.com/dp/B09XYZ?tag=myblog-20">Buy now</a>')
    assert signal is not None
    assert "affiliate link found" in signal.lower()

def test_detect_affiliate_signal_amzn_short_link():
    signal = detect_affiliate_signal("", page_html='<a href="https://amzn.to/3abc123">Check price</a>')
    assert signal is not None
    assert "affiliate link found" in signal.lower()

def test_detect_affiliate_signal_none():
    assert detect_affiliate_signal("Just a personal blog about cooking without any affiliate links.") is None

def test_detect_amazon_affiliate_signal_alias():
    text = "As an Amazon Associate I earn from qualifying purchases."
    assert detect_amazon_affiliate_signal(text) is not None

def test_classify_social_link():
    assert classify_social_link("https://www.instagram.com/mybrand") == ("instagram", "https://www.instagram.com/mybrand")
    assert classify_social_link("https://twitter.com/mybrand") == ("twitter", "https://twitter.com/mybrand")
    assert classify_social_link("https://x.com/mybrand") == ("twitter", "https://x.com/mybrand")
    assert classify_social_link("https://unknownsite.com/foo") is None

def test_get_domain():
    assert get_domain("https://sub.blog.example.co.uk/page?x=1") == "example.co.uk"
    assert get_domain("https://thesommerhome.com/kitchen-gadgets/") == "thesommerhome.com"
