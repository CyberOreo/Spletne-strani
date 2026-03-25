"""Generacija personaliziranih emailov iz predlog (multi-jezik)."""
import logging
from pathlib import Path

from src.config import (
    COUNTRIES, SMTP_ACCOUNTS, INDUSTRIJSKO_DEJSTVO, SKD_DEJAVNOSTI
)
from src.database import (
    get_leads, save_email_draft, get_conn
)

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# Jezik → unsubscribe beseda
UNSUBSCRIBE_WORD = {
    "sl": "ODJAVA", "hr": "ODJAVA", "de": "ABMELDEN",
    "it": "CANCELLA", "cs": "ODHLÁSIT", "hu": "LEIRATKOZÁS",
    "pl": "REZYGNACJA", "ro": "DEZABONARE", "sk": "ODHLÁSIT",
}


def _get_language(lead: dict) -> str:
    """Določi jezik glede na državo leada."""
    country = lead.get("country", "si")
    country_cfg = COUNTRIES.get(country, {})
    return country_cfg.get("lang", "sl")


def _get_greeting(lead: dict) -> str:
    """Vrne pozdrav — ime osebe ali generični."""
    person = lead.get("contact_person") or ""
    if person.strip():
        return person.strip()
    lang = _get_language(lead)
    defaults = {
        "sl": "Spoštovani", "hr": "Poštovani", "de": "Sehr geehrte Damen und Herren",
        "it": "Gentile", "cs": "Vážený zákazníku", "hu": "Tisztelt",
        "pl": "Szanowni Państwo", "ro": "Stimate client", "sk": "Vážený/á",
    }
    return defaults.get(lang, "Spoštovani")


def _get_industry_hook(lead: dict) -> str:
    """Vrne industrijsko-specifični hook v ustreznem jeziku."""
    skd = lead.get("skd_code") or ""
    lang = _get_language(lead)

    hooks = INDUSTRIJSKO_DEJSTVO.get(skd) or INDUSTRIJSKO_DEJSTVO.get("default", {})
    return hooks.get(lang) or hooks.get("sl") or hooks.get("de") or ""


def _load_template(lang: str, template_type: str) -> str | None:
    """Naloži predlogo iz datoteke."""
    path = TEMPLATES_DIR / lang / f"email_{template_type.lower()}.txt"
    if not path.exists():
        # Fallback na slovenščino
        path = TEMPLATES_DIR / "sl" / f"email_{template_type.lower()}.txt"
    if not path.exists():
        logger.error("Predloga ne obstaja: %s", path)
        return None
    return path.read_text(encoding="utf-8")


def _get_sender(smtp_index: int = 0) -> dict:
    """Vrne podatke pošiljatelja."""
    accounts = SMTP_ACCOUNTS
    if not accounts:
        return {"name": "", "phone": ""}
    acc = accounts[smtp_index % len(accounts)]
    return {"name": acc.get("name", ""), "phone": acc.get("phone", "")}


def generate_email(lead: dict, template_type: str = None, smtp_index: int = 0) -> dict | None:
    """
    Generira email za lead. Vrne dict z: subject, body, template_type.
    """
    if template_type is None:
        template_type = lead.get("recommended_template", "A")

    lang = _get_language(lead)
    template_raw = _load_template(lang, template_type)
    if not template_raw:
        return None

    sender = _get_sender(smtp_index)
    greeting = _get_greeting(lead)
    industry_hook = _get_industry_hook(lead)

    company_name = lead.get("company_name") or ""
    activity = lead.get("activity") or SKD_DEJAVNOSTI.get(lead.get("skd_code", ""), "")
    city = lead.get("city") or lead.get("region") or ""

    # Zamenjaj vse spremenljivke
    body = template_raw
    replacements = {
        "{company_name}": company_name,
        "{greeting}": greeting,
        "{activity}": activity,
        "{city}": city,
        "{industry_hook}": industry_hook,
        "{sender_name}": sender["name"],
        "{sender_phone}": sender["phone"],
        # Aliasi za različne jezike (de, it itd.)
        "{firmenname}": company_name,
        "{kontaktperson}": greeting,
        "{branche}": activity,
        "{ort}": city,
        "{branchenspezifisch}": industry_hook,
    }
    for key, val in replacements.items():
        body = body.replace(key, val or "")

    # Pridobi zadevo iz prve vrstice
    lines = body.strip().split("\n")
    subject = ""
    body_lines = lines
    for i, line in enumerate(lines):
        lower = line.lower()
        if lower.startswith("zadeva:") or lower.startswith("betreff:") or \
           lower.startswith("predmet:") or lower.startswith("oggetto:") or \
           lower.startswith("przedmiot:") or lower.startswith("tárgy:") or \
           lower.startswith("subiect:") or lower.startswith("předmět:") or \
           lower.startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            body_lines = lines[i + 1:]
            break

    body_text = "\n".join(body_lines).strip()

    return {
        "subject": subject,
        "body": body_text,
        "template_type": template_type,
        "lang": lang,
    }


def generate_all_emails(lang_filter: str = None) -> dict:
    """
    Generira emaile za vse kvalificirane leade brez obstoječega drafta.
    Vrne statistiko.
    """
    # Pridobi leade z vsaj minimalno oceno, ki nimajo emaila
    leads = get_leads(disqualified=0)
    qualified = [
        l for l in leads
        if l.get("qualification_score", 0) >= 3
        and l.get("email")
    ]

    # Filtriraj že generirane (imajo DRAFT email)
    with get_conn() as conn:
        existing = {
            r[0] for r in conn.execute(
                "SELECT DISTINCT lead_id FROM emails WHERE status = 'DRAFT'"
            ).fetchall()
        }

    to_generate = [l for l in qualified if l["lead_id"] not in existing]

    if lang_filter:
        to_generate = [
            l for l in to_generate
            if _get_language(l) == lang_filter
        ]

    stats = {"generated": 0, "skipped": 0, "errors": 0}
    smtp_idx = 0

    for lead in to_generate:
        result = generate_email(lead, smtp_index=smtp_idx % len(SMTP_ACCOUNTS) if SMTP_ACCOUNTS else 0)
        if not result:
            stats["errors"] += 1
            continue

        save_email_draft(
            lead_id=lead["lead_id"],
            template_type=result["template_type"],
            subject=result["subject"],
            body=result["body"],
        )
        stats["generated"] += 1
        smtp_idx += 1
        logger.debug("Email generiran za %s (predloga %s)", lead["lead_id"], result["template_type"])

    logger.info(
        "Emaili generirani: %d novih, %d napak",
        stats["generated"], stats["errors"],
    )
    return stats
