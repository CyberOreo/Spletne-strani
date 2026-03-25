"""Generacija brezplačnih preview strani za zainteresirane leade."""
import logging
from pathlib import Path

from src.config import PREVIEW_BASE_URL, SMTP_ACCOUNTS
from src.database import get_lead, save_email_draft, get_conn
from src.email_generator import _get_language

logger = logging.getLogger(__name__)

PREVIEWS_DIR = Path(__file__).resolve().parent.parent / "previews"
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "preview"


def generate_preview(lead_id: str) -> str | None:
    """
    Generira HTML preview stran za podjetje.
    Vrne URL do preview strani ali None pri napaki.
    """
    lead = get_lead(lead_id)
    if not lead:
        logger.error("Lead ne obstaja: %s", lead_id)
        return None

    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)

    html = _render_preview_html(lead)
    filename = f"{lead_id.lower()}.html"
    filepath = PREVIEWS_DIR / filename
    filepath.write_text(html, encoding="utf-8")

    url = f"{PREVIEW_BASE_URL}/{filename}"
    logger.info("Preview generiran za %s: %s", lead_id, url)
    return url


def _render_preview_html(lead: dict) -> str:
    """Generira HTML za preview stran podjetja."""
    company = lead.get("company_name") or "Vaše podjetje"
    activity = lead.get("activity") or ""
    address = lead.get("address") or ""
    phone = lead.get("phone") or ""
    email = lead.get("email") or ""
    city = lead.get("city") or ""
    lang = _get_language(lead)

    # Barve glede na dejavnost
    color_map = {
        "vodovodar": "#0066cc", "elektrikar": "#ffaa00",
        "frizer": "#cc0066", "restavracija": "#cc3300",
        "zobozdravnik": "#00aacc", "fitnes": "#00cc66",
        "default": "#2c5f8a",
    }
    skd = lead.get("skd_code", "")
    primary_color = color_map.get(activity.lower()[:10], color_map["default"])

    # Teksti glede na jezik
    labels = {
        "sl": {"about": "O nas", "services": "Naše storitve", "contact": "Kontakt",
               "call": "Pokličite nas", "note": "To je BREZPLAČNI DEMO vaše prihodnje strani"},
        "hr": {"about": "O nama", "services": "Naše usluge", "contact": "Kontakt",
               "call": "Nazovite nas", "note": "Ovo je BESPLATNI DEMO vaše buduće stranice"},
        "de": {"about": "Über uns", "services": "Unsere Leistungen", "contact": "Kontakt",
               "call": "Rufen Sie uns an", "note": "Dies ist eine KOSTENLOSE DEMO Ihrer zukünftigen Webseite"},
        "it": {"about": "Chi siamo", "services": "I nostri servizi", "contact": "Contatti",
               "call": "Chiamateci", "note": "Questa è una DEMO GRATUITA del vostro futuro sito"},
        "cs": {"about": "O nás", "services": "Naše služby", "contact": "Kontakt",
               "call": "Zavolejte nám", "note": "Toto je BEZPLATNÁ UKÁZKA vašeho budoucího webu"},
        "hu": {"about": "Rólunk", "services": "Szolgáltatásaink", "contact": "Kapcsolat",
               "call": "Hívjon minket", "note": "Ez az Ön jövőbeli weboldalának INGYENES DEMÓJA"},
        "pl": {"about": "O nas", "services": "Nasze usługi", "contact": "Kontakt",
               "call": "Zadzwoń do nas", "note": "To jest BEZPŁATNE DEMO Twojej przyszłej strony"},
        "ro": {"about": "Despre noi", "services": "Serviciile noastre", "contact": "Contact",
               "call": "Sunați-ne", "note": "Acesta este un DEMO GRATUIT al viitorului dvs. site"},
    }
    lbl = labels.get(lang, labels["sl"])

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{company}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #333; }}
  .demo-banner {{
    background: #ff6600; color: white; text-align: center;
    padding: 10px; font-weight: bold; font-size: 14px; position: sticky; top: 0; z-index: 999;
  }}
  header {{
    background: {primary_color}; color: white; padding: 60px 20px; text-align: center;
  }}
  header h1 {{ font-size: 2.5rem; margin-bottom: 10px; }}
  header p {{ font-size: 1.2rem; opacity: 0.9; }}
  .cta-btn {{
    display: inline-block; margin-top: 25px; padding: 15px 35px;
    background: white; color: {primary_color}; border-radius: 5px;
    text-decoration: none; font-weight: bold; font-size: 1rem;
  }}
  section {{ padding: 60px 20px; max-width: 900px; margin: 0 auto; }}
  section h2 {{ font-size: 1.8rem; color: {primary_color}; margin-bottom: 20px; }}
  section p {{ line-height: 1.7; font-size: 1rem; color: #555; }}
  .services-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px; margin-top: 20px;
  }}
  .service-card {{
    background: #f8f9fa; border-left: 4px solid {primary_color};
    padding: 20px; border-radius: 4px;
  }}
  .contact-block {{
    background: {primary_color}; color: white; padding: 40px; border-radius: 8px;
    text-align: center;
  }}
  .contact-block a {{ color: white; font-size: 1.3rem; font-weight: bold; text-decoration: none; }}
  footer {{
    background: #222; color: #aaa; text-align: center; padding: 20px; font-size: 0.85rem;
  }}
  @media (max-width: 600px) {{
    header h1 {{ font-size: 1.8rem; }}
  }}
</style>
</head>
<body>
<div class="demo-banner">⚠️ {lbl["note"]} — powered by WebStudio</div>
<header>
  <h1>{company}</h1>
  <p>{activity} · {city}</p>
  {'<a href="tel:' + phone + '" class="cta-btn">' + lbl["call"] + '</a>' if phone else ''}
</header>
<section>
  <h2>{lbl["about"]}</h2>
  <p>
    {company} je {activity.lower()} podjetje s sedežem v {city or "vaši regiji"}.
    Nudimo kakovostne storitve za naše stranke in se trudimo za najvišje standarde dela.
    {"Kontaktirajte nas za brezplačen pregled ali ponudbo." if lang=="sl" else ""}
  </p>
</section>
<section style="background:#f8f9fa; max-width:100%">
<div style="max-width:900px; margin:0 auto; padding: 40px 20px;">
  <h2>{lbl["services"]}</h2>
  <div class="services-grid">
    <div class="service-card"><strong>✓ Storitev 1</strong><p>Opis vaše glavne storitve</p></div>
    <div class="service-card"><strong>✓ Storitev 2</strong><p>Opis druge storitve</p></div>
    <div class="service-card"><strong>✓ Storitev 3</strong><p>Opis tretje storitve</p></div>
  </div>
</div>
</section>
<section>
  <h2>{lbl["contact"]}</h2>
  <div class="contact-block">
    {'<p><a href="tel:' + phone + '">📞 ' + phone + '</a></p>' if phone else ''}
    {'<p><a href="mailto:' + email + '">✉️ ' + email + '</a></p>' if email else ''}
    {'<p>📍 ' + address + '</p>' if address else ''}
  </div>
</section>
<footer>
  © {company} · Spletna stran ustvarjena z WebStudio
</footer>
</body>
</html>"""


def send_preview_email(lead_id: str, preview_url: str) -> bool:
    """Pošlje email z linkom na preview stran zainteresiranemu leadu."""
    lead = get_lead(lead_id)
    if not lead or not lead.get("email"):
        return False

    lang = _get_language(lead)
    company = lead.get("company_name", "")
    sender = SMTP_ACCOUNTS[0] if SMTP_ACCOUNTS else {}

    subjects = {
        "sl": f"Vaša demo spletna stran je pripravljena — {company}",
        "hr": f"Vaša demo web stranica je spremna — {company}",
        "de": f"Ihre Demo-Webseite ist fertig — {company}",
        "it": f"La vostra demo del sito web è pronta — {company}",
        "cs": f"Vaše demo webové stránky jsou hotové — {company}",
        "hu": f"Az Ön demó weboldala elkészült — {company}",
        "pl": f"Twoja demo strona internetowa jest gotowa — {company}",
        "ro": f"Demo-ul site-ului dvs. este gata — {company}",
    }

    bodies = {
        "sl": f"""Pozdravljeni,

hvala za vaš odgovor! Kot sem obljubil, sem pripravil brezplačen demo vaše spletne strani.

Oglejte si jo tukaj: {preview_url}

To je le primer — prava stran bi bila popolnoma prilagojena vašemu podjetju.

Kdaj bi vam ustrezal kratek klic, da se pogovorimo o naslednjih korakih?

Lep pozdrav,
{sender.get('name', '')}
{sender.get('phone', '')}

---
Če ne želite prejemati sporočil, odgovorite z besedo ODJAVA.""",
        "de": f"""Guten Tag,

vielen Dank für Ihre Antwort! Wie versprochen habe ich eine kostenlose Demo Ihrer Webseite erstellt.

Sehen Sie sie hier an: {preview_url}

Dies ist nur ein Beispiel — die echte Seite würde vollständig an Ihr Unternehmen angepasst.

Wann würde Ihnen ein kurzes Gespräch passen, um die nächsten Schritte zu besprechen?

Mit freundlichen Grüßen,
{sender.get('name', '')}
{sender.get('phone', '')}

---
Wenn Sie keine weiteren Nachrichten erhalten möchten, antworten Sie mit ABMELDEN.""",
    }

    subject = subjects.get(lang, subjects["sl"])
    body = bodies.get(lang, bodies["sl"])

    email_id = save_email_draft(
        lead_id=lead_id,
        template_type="PREVIEW",
        subject=subject,
        body=body,
    )
    logger.info("Preview email ustvarjen za %s: %s", lead_id, preview_url)
    return True
