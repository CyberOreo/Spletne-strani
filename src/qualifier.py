"""Kvalifikacija leadov — 7-kriterijev točkovalni sistem."""
import json
import logging
import re

from src.config import COUNTRIES
from src.database import (
    get_leads, update_lead_qualification, disqualify_lead
)

logger = logging.getLogger(__name__)

# ─── Diskvalifikacijski vzorci ────────────────────────────────────────────────
CHAIN_KEYWORDS = [
    "mcdonald", "subway", "lidl", "hofer", "spar", "mercator", "konzum",
    "ikea", "h&m", "zara", "dm ", "müller", "billa", "penny",
    "interspar", "eurospin", "kaufland",
]
STATE_KEYWORDS = [
    "občina", "ministrstvo", "vlada", "republika", "uprava", "javni zavod",
    "javna agencija", "državni", "община", "ministerstvo", "gemeinde",
    "amt ", "bundesamt", "staatsamt", "comune di", "municipio",
]
MODERN_CMS_SIGNALS = [
    "wix.com", "squarespace.com", "wordpress.com", "weebly.com",
    "webnode.com", "jimdo.com", "strikingly.com",
]

# ─── Kriteriji (7) ───────────────────────────────────────────────────────────

def _criterion_1_no_website(lead: dict) -> bool:
    """Ni spletne strani ALI je zastarela (pred 2018)."""
    status = lead.get("website_status", "none")
    year = lead.get("website_year")
    if status == "none":
        return True
    if status == "outdated" or (year and year < 2018):
        return True
    return False


def _criterion_2_active(lead: dict) -> bool:
    """Aktivno posluje — ni v stečaju, ni izbrisano."""
    notes = (lead.get("notes") or "").lower()
    name = (lead.get("company_name") or "").lower()
    bad = ["stečaj", "likvidacija", "izbrisano", "zaprt", "insolvent",
           "insolvenz", "konkurs", "fallito", "úpadek", "felszámolás"]
    return not any(kw in notes or kw in name for kw in bad)


def _criterion_3_has_contact(lead: dict) -> bool:
    """Ima javno dostopen email ali telefon."""
    email = lead.get("email") or ""
    phone = lead.get("phone") or ""
    if email.strip() and "@" in email:
        return True
    if phone.strip() and len(re.sub(r"[^\d]", "", phone)) >= 7:
        return True
    return False


def _criterion_4_small_business(lead: dict) -> bool:
    """1–20 zaposlenih (malo podjetje / s.p.)."""
    name = (lead.get("company_name") or "").lower()
    # s.p. in d.o.o. so tipično mala podjetja
    if " s.p." in name or ", s.p" in name:
        return True
    if " d.o.o." in name or ", d.o.o" in name:
        return True
    # Brez "d.d." (delniška) ali "holding" = verjetno malo
    if "d.d." in name or "holding" in name or " ag " in name or " plc" in name:
        return False
    return True  # Privzeto predpostavimo mala podjetja


def _criterion_5_social_media(lead: dict) -> bool:
    """Aktiven na socialnih omrežjih."""
    return bool(
        (lead.get("facebook_url") or "").strip()
        or (lead.get("instagram_url") or "").strip()
    )


def _criterion_6_service_sector(lead: dict) -> bool:
    """Storitveni ali rokodelski sektor."""
    skd = lead.get("skd_code") or ""
    activity = (lead.get("activity") or "").lower()
    # SKD kode storitvenega sektorja
    service_skd_prefixes = ["43", "45", "47", "49", "55", "56", "68",
                             "69", "81", "86", "93", "96"]
    for prefix in service_skd_prefixes:
        if skd.startswith(prefix):
            return True
    # Brez SKD — preveri ključne besede
    service_keywords = [
        "servis", "popravilo", "instalac", "čiščen", "frizer",
        "zobozdrav", "restavraci", "prenočišč", "računovodst",
        "plumber", "electric", "painter", "cleaner", "restaurant",
        "salon", "fitness", "florist", "immobil", "real estate",
    ]
    return any(kw in activity for kw in service_keywords)


def _criterion_7_local_regional(lead: dict) -> bool:
    """Deluje lokalno ali regionalno."""
    name = (lead.get("company_name") or "").lower()
    city = (lead.get("city") or "").lower()
    # Lokalni indikatorji
    local_keywords = ["lokalni", "lokal", "local", "regional", "domači"]
    if any(kw in name for kw in local_keywords):
        return True
    if city:
        return True
    # Ni veriga in ima naslov
    return bool(lead.get("address"))


# ─── Diskvalifikacija ─────────────────────────────────────────────────────────

def should_disqualify(lead: dict) -> tuple[bool, str]:
    """Vrne (True, razlog) če lead ni primeren."""
    name = (lead.get("company_name") or "").lower()
    website = (lead.get("website_url") or "").lower()
    website_status = lead.get("website_status", "none")

    # Moderna spletna stran
    if website_status == "modern":
        return True, "Moderna spletna stran"

    # CMS, ki kaže moderno stran
    for signal in MODERN_CMS_SIGNALS:
        if signal in website:
            return True, f"Moderna platforma: {signal}"

    # Verige in franšize
    for kw in CHAIN_KEYWORDS:
        if kw in name:
            return True, f"Verižno podjetje: {kw}"

    # Državne institucije
    for kw in STATE_KEYWORDS:
        if kw in name:
            return True, f"Državna institucija: {kw}"

    # Zahtevaj email — brez emaila ne moremo poslati cold email
    email = str(lead.get("email") or "").strip()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return True, "Ni veljavnega email naslova"

    return False, ""


# ─── Točkovanje ───────────────────────────────────────────────────────────────

CRITERIA_FUNCTIONS = [
    ("no_website_or_outdated", _criterion_1_no_website),
    ("actively_operating",     _criterion_2_active),
    ("has_contact",            _criterion_3_has_contact),
    ("small_business",         _criterion_4_small_business),
    ("social_media_active",    _criterion_5_social_media),
    ("service_sector",         _criterion_6_service_sector),
    ("local_regional",         _criterion_7_local_regional),
]


def score_lead(lead: dict) -> tuple[int, list[str]]:
    """Izračuna točke (1–10) in seznam ujemajočih kriterijev."""
    matched = []
    for name, fn in CRITERIA_FUNCTIONS:
        if fn(lead):
            matched.append(name)
    raw = len(matched)
    score = round(raw / 7 * 10)
    return score, matched


def determine_priority(score: int) -> str:
    if score >= 7:
        return "VISOKA"
    elif score >= 4:
        return "SREDNJA"
    return "NIZKA"


def determine_template(lead: dict) -> str:
    status = lead.get("website_status", "none")
    if status == "none":
        return "A"
    elif status == "outdated":
        return "B"
    return "A"


# ─── Glavna funkcija ──────────────────────────────────────────────────────────

def qualify_all(min_score: int = 3) -> dict:
    """
    Kvalificira vse nekvalificirane leade (score == 0).
    Vrne statistiko.
    """
    leads = get_leads(disqualified=0)
    unscored = [l for l in leads if l.get("qualification_score", 0) == 0]

    stats = {"processed": 0, "qualified": 0, "disqualified": 0}

    for lead in unscored:
        lead_id = lead["lead_id"]
        stats["processed"] += 1

        # Preveri diskvalifikacijo
        dq, reason = should_disqualify(lead)
        if dq:
            disqualify_lead(lead_id, reason)
            stats["disqualified"] += 1
            logger.info("Diskvalificiran %s: %s", lead_id, reason)
            continue

        score, matched = score_lead(lead)
        priority = determine_priority(score)
        template = determine_template(lead)

        if score < min_score:
            disqualify_lead(lead_id, f"Prenizek score: {score}/{min_score}")
            stats["disqualified"] += 1
        else:
            update_lead_qualification(
                lead_id=lead_id,
                score=score,
                criteria_matched=matched,
                priority=priority,
                template=template,
            )
            stats["qualified"] += 1
            logger.debug("Kvalificiran %s: score=%d, prioriteta=%s", lead_id, score, priority)

    logger.info(
        "Kvalifikacija končana: %d obdelanih, %d kvalificiranih, %d diskvalificiranih",
        stats["processed"], stats["qualified"], stats["disqualified"],
    )
    return stats
