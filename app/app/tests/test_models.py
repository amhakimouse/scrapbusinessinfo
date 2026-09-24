import pytest
from scraper.models import Lead

def test_lead_model_defaults():
    lead = Lead(
        domain="affiliatetest.com",
        url="https://affiliatetest.com",
        emails=["contact@affiliatetest.com", "info@affiliatetest.com"],
    )
    assert lead.domain == "affiliatetest.com"
    assert lead.primary_email() == "contact@affiliatetest.com"
    assert lead.status == "scraped"
    assert lead.scraped_at is not None
    assert lead.about_snippet is None
    assert lead.contact_url is None

def test_lead_model_no_email():
    lead = Lead(
        domain="noemail.com",
        url="https://noemail.com",
        status="no_email",
    )
    assert lead.primary_email() == ""
    assert lead.emails == []

def test_lead_model_new_fields():
    lead = Lead(
        domain="reviewblog.com",
        url="https://reviewblog.com",
        about_snippet="We review the best smart home gadgets.",
        contact_url="https://reviewblog.com/contact-us",
    )
    assert lead.about_snippet == "We review the best smart home gadgets."
    assert lead.contact_url == "https://reviewblog.com/contact-us"
