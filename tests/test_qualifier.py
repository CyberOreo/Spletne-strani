"""Unit testi za qualifier modul."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.qualifier import (
    score_lead, should_disqualify,
    _criterion_1_no_website, _criterion_2_active,
    _criterion_3_has_contact, _criterion_4_small_business,
    _criterion_5_social_media, _criterion_6_service_sector,
    _criterion_7_local_regional,
)

# ── Fixture leadov ─────────────────────────────────────────────────────────────

def make_lead(**kwargs):
    defaults = {
        "lead_id": "TEST-001",
        "company_name": "Vodovodar Novak d.o.o.",
        "activity": "vodovodarska dela",
        "skd_code": "43",
        "email": "novak@example.com",
        "phone": "040123456",
        "city": "Ljubljana",
        "region": "Osrednjeslovenska",
        "website_status": "none",
        "website_url": None,
        "website_year": None,
        "facebook_url": "https://facebook.com/novak",
        "instagram_url": None,
        "data_source": "bizi",
        "notes": None,
        "country": "si",
    }
    defaults.update(kwargs)
    return defaults


# ── Kriterij 1: ni spletne strani ─────────────────────────────────────────────

def test_criterion1_no_website():
    lead = make_lead(website_status="none")
    assert _criterion_1_no_website(lead) is True

def test_criterion1_outdated_website():
    lead = make_lead(website_status="outdated")
    assert _criterion_1_no_website(lead) is True

def test_criterion1_old_year():
    lead = make_lead(website_status="has", website_year=2015)
    assert _criterion_1_no_website(lead) is True

def test_criterion1_modern_website_fails():
    lead = make_lead(website_status="modern", website_year=2022)
    assert _criterion_1_no_website(lead) is False


# ── Kriterij 2: aktivno podjetje ──────────────────────────────────────────────

def test_criterion2_active_business():
    lead = make_lead()
    assert _criterion_2_active(lead) is True

def test_criterion2_bankrupt():
    lead = make_lead(notes="podjetje v stečaju")
    assert _criterion_2_active(lead) is False

def test_criterion2_liquidated_name():
    # "stečaj" je točno besedilo v CHAIN_KEYWORDS — mora biti v imenu
    lead = make_lead(company_name="Stečaj podjetje d.o.o.")
    assert _criterion_2_active(lead) is False


# ── Kriterij 3: ima kontakt ────────────────────────────────────────────────────

def test_criterion3_has_email():
    lead = make_lead(email="test@example.com", phone=None)
    assert _criterion_3_has_contact(lead) is True

def test_criterion3_has_phone():
    lead = make_lead(email=None, phone="040123456")
    assert _criterion_3_has_contact(lead) is True

def test_criterion3_no_contact():
    lead = make_lead(email=None, phone=None)
    assert _criterion_3_has_contact(lead) is False

def test_criterion3_invalid_email():
    lead = make_lead(email="notanemail", phone=None)
    assert _criterion_3_has_contact(lead) is False

def test_criterion3_short_phone():
    lead = make_lead(email=None, phone="123")
    assert _criterion_3_has_contact(lead) is False


# ── Kriterij 4: malo podjetje ─────────────────────────────────────────────────

def test_criterion4_sp():
    lead = make_lead(company_name="Janez Novak s.p.")
    assert _criterion_4_small_business(lead) is True

def test_criterion4_doo():
    lead = make_lead(company_name="Novak d.o.o.")
    assert _criterion_4_small_business(lead) is True

def test_criterion4_dd_fails():
    lead = make_lead(company_name="Velika Firma d.d.")
    assert _criterion_4_small_business(lead) is False

def test_criterion4_holding_fails():
    # Brez d.o.o. — "holding" ustavimo pred True returnov
    lead = make_lead(company_name="Korporacija holding AG")
    assert _criterion_4_small_business(lead) is False


# ── Kriterij 5: socialna omrežja ──────────────────────────────────────────────

def test_criterion5_has_facebook():
    lead = make_lead(facebook_url="https://facebook.com/test", instagram_url=None)
    assert _criterion_5_social_media(lead) is True

def test_criterion5_has_instagram():
    lead = make_lead(facebook_url=None, instagram_url="https://instagram.com/test")
    assert _criterion_5_social_media(lead) is True

def test_criterion5_no_social():
    lead = make_lead(facebook_url=None, instagram_url=None)
    assert _criterion_5_social_media(lead) is False


# ── Kriterij 6: storitveni sektor ─────────────────────────────────────────────

def test_criterion6_service_sector():
    lead = make_lead(skd_code="43")  # Gradbena dela
    assert _criterion_6_service_sector(lead) is True

def test_criterion6_restaurant():
    lead = make_lead(skd_code="56")  # Gostinstvo
    assert _criterion_6_service_sector(lead) is True

def test_criterion6_manufacturing_fails():
    lead = make_lead(skd_code="10")  # Predelovalna industrija
    assert _criterion_6_service_sector(lead) is False


# ── Kriterij 7: lokalno/regionalno ────────────────────────────────────────────

def test_criterion7_has_city():
    lead = make_lead(city="Ljubljana", address=None)
    assert _criterion_7_local_regional(lead) is True

def test_criterion7_has_address():
    lead = make_lead(city=None, address="Dunajska 5, Ljubljana")
    assert _criterion_7_local_regional(lead) is True

def test_criterion7_no_city_no_address_fails():
    # Brez mesta in naslova → ni lokalni
    lead = make_lead(city=None, address=None, company_name="Podjetje brez lokacije d.o.o.")
    assert _criterion_7_local_regional(lead) is False


# ── score_lead ─────────────────────────────────────────────────────────────────

def test_score_lead_ideal():
    """Lead brez spletne strani z vsemi kriteriji → visok score."""
    lead = make_lead(
        website_status="none",
        email="test@example.com",
        phone="040123456",
        city="Ljubljana",
        facebook_url="https://facebook.com/test",
        skd_code="43",
        company_name="Novak d.o.o.",
    )
    score, criteria = score_lead(lead)
    assert score >= 7
    assert isinstance(criteria, list)
    assert len(criteria) >= 3

def test_score_lead_no_contact_disqualifies():
    # Brez kontakta → should_disqualify vrne True
    lead = make_lead(email=None, phone=None)
    disq, reason = should_disqualify(lead)
    assert disq is True
    assert "kontakt" in reason.lower()

def test_score_lead_returns_tuple():
    lead = make_lead()
    result = score_lead(lead)
    assert isinstance(result, tuple)
    assert len(result) == 2


# ── should_disqualify ─────────────────────────────────────────────────────────

def test_should_disqualify_modern_website():
    lead = make_lead(website_status="modern", website_year=2023)
    disq, reason = should_disqualify(lead)
    assert disq is True
    assert reason

def test_should_disqualify_chain():
    lead = make_lead(company_name="McDonald's Ljubljana")
    disq, reason = should_disqualify(lead)
    assert disq is True

def test_should_disqualify_state_institution():
    lead = make_lead(company_name="Občina Celje")
    disq, reason = should_disqualify(lead)
    assert disq is True

def test_should_not_disqualify_normal():
    lead = make_lead(website_status="none")
    disq, reason = should_disqualify(lead)
    assert disq is False


# ── Prioritete ────────────────────────────────────────────────────────────────

def test_determine_priority_visoka():
    """Score >= 7 → VISOKA prioriteta."""
    from src.qualifier import determine_priority
    assert determine_priority(7) == "VISOKA"
    assert determine_priority(10) == "VISOKA"
    assert determine_priority(8) == "VISOKA"

def test_determine_priority_srednja():
    from src.qualifier import determine_priority
    assert determine_priority(4) == "SREDNJA"
    assert determine_priority(5) == "SREDNJA"
    assert determine_priority(6) == "SREDNJA"

def test_determine_priority_nizka():
    from src.qualifier import determine_priority
    assert determine_priority(0) == "NIZKA"
    assert determine_priority(1) == "NIZKA"
    assert determine_priority(3) == "NIZKA"
