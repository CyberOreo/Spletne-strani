"""Sledenje statusov leadov — IMAP monitoring odgovorov in follow-up."""
import email as email_lib
import imaplib
import logging
from datetime import datetime

from src.config import IMAP_HOST, IMAP_USER, IMAP_PASSWORD
from src.database import (
    get_followup_candidates, update_lead_status,
    mark_email_replied, get_conn
)
from src.email_generator import generate_email
from src.database import save_email_draft

logger = logging.getLogger(__name__)

UNSUBSCRIBE_WORDS = {
    "odjava", "abmelden", "cancella", "odhlásit", "leiratkozás",
    "rezygnacja", "dezabonare", "unsubscribe", "odhlasit",
}


def check_replies() -> dict:
    """
    Preveri IMAP inbox za odgovore na poslane emaile.
    Vrne statistiko: replied, unsubscribed.
    """
    if not IMAP_USER or not IMAP_PASSWORD:
        logger.warning("IMAP ni konfiguriran — preskakujem preverjanje odgovorov")
        return {"replied": 0, "unsubscribed": 0}

    stats = {"replied": 0, "unsubscribed": 0}

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST)
        mail.login(IMAP_USER, IMAP_PASSWORD)
        mail.select("inbox")

        # Išči neprebrana sporočila
        _, msg_ids = mail.search(None, "UNSEEN")
        if not msg_ids or not msg_ids[0]:
            mail.logout()
            return stats

        for msg_id in msg_ids[0].split():
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)

            from_addr = email_lib.utils.parseaddr(msg.get("From", ""))[1].lower().strip()
            body = _get_body(msg).lower().strip()

            # Preveri odjavo
            if any(word in body for word in UNSUBSCRIBE_WORDS):
                from src.database import add_unsubscribe
                add_unsubscribe(from_addr)
                logger.info("Odjava: %s", from_addr)
                stats["unsubscribed"] += 1
            else:
                # Označi odgovor na leadu
                lead_id = _find_lead_by_email(from_addr)
                if lead_id:
                    mark_email_replied(lead_id)
                    logger.info("Odgovor od %s → lead %s", from_addr, lead_id)
                    stats["replied"] += 1

        mail.logout()
    except imaplib.IMAP4.error as exc:
        logger.error("IMAP napaka: %s", exc)
    except Exception as exc:
        logger.error("Napaka pri preverjanju odgovorov: %s", exc)

    return stats


def _get_body(msg) -> str:
    """Izvleče besedilo iz email sporočila."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            pass
    return ""


def _find_lead_by_email(email_addr: str) -> str | None:
    """Poišče lead_id glede na email naslov."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT lead_id FROM leads WHERE LOWER(email) = ?",
            (email_addr,),
        ).fetchone()
    return row["lead_id"] if row else None


def generate_followups(followup_days: int = 5) -> dict:
    """
    Za leade brez odgovora po `followup_days` dneh generira Template C email.
    Vrne statistiko.
    """
    candidates = get_followup_candidates(days=followup_days)
    stats = {"generated": 0, "skipped": 0}

    for lead in candidates:
        # Preveri, da že nima follow-up emaila
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM emails WHERE lead_id = ? AND template_type = 'C'",
                (lead["lead_id"],),
            ).fetchone()

        if existing:
            stats["skipped"] += 1
            continue

        result = generate_email(lead, template_type="C")
        if not result:
            stats["skipped"] += 1
            continue

        save_email_draft(
            lead_id=lead["lead_id"],
            template_type="C",
            subject=result["subject"],
            body=result["body"],
        )
        stats["generated"] += 1
        logger.info("Follow-up generiran za %s", lead["lead_id"])

    logger.info(
        "Follow-up: %d generiranih, %d preskočenih",
        stats["generated"], stats["skipped"],
    )
    return stats


def update_status_manual(lead_id: str, status: str) -> bool:
    """Ročno posodobi status leada."""
    valid = {"ČAKA", "POSLANO", "ODPRT", "ODGOVORIL", "ZAVRNIL", "KONVERTIRAN"}
    if status.upper() not in valid:
        logger.error("Neveljaven status: %s", status)
        return False
    update_lead_status(lead_id, status.upper())
    return True
