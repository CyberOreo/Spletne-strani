"""SQLite baza podatkov — shema, inicializacija in CRUD funkcije."""
import json
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.config import DATABASE_PATH

logger = logging.getLogger(__name__)


# ─── Inicializacija ───────────────────────────────────────────────────────────

def init_db() -> None:
    """Ustvari tabele, če še ne obstajajo."""
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id             TEXT UNIQUE NOT NULL,
                company_name        TEXT NOT NULL,
                contact_person      TEXT,
                activity            TEXT,
                skd_code            TEXT,
                email               TEXT,
                phone               TEXT,
                address             TEXT,
                city                TEXT,
                region              TEXT,
                website_url         TEXT,
                website_status      TEXT DEFAULT 'none',
                website_year        INTEGER,
                facebook_url        TEXT,
                instagram_url       TEXT,
                data_source         TEXT,
                qualification_score INTEGER DEFAULT 0,
                criteria_matched    TEXT DEFAULT '[]',
                priority            TEXT DEFAULT 'NIZKA',
                recommended_template TEXT DEFAULT 'A',
                status              TEXT DEFAULT 'ČAKA',
                notes               TEXT,
                created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_contact_at     DATETIME,
                disqualified        INTEGER DEFAULT 0,
                disqualify_reason   TEXT
            );

            CREATE TABLE IF NOT EXISTS emails (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id       TEXT NOT NULL REFERENCES leads(lead_id),
                template_type TEXT NOT NULL,
                subject       TEXT,
                body          TEXT,
                sent_at       DATETIME,
                opened_at     DATETIME,
                replied_at    DATETIME,
                status        TEXT DEFAULT 'DRAFT'
            );

            CREATE TABLE IF NOT EXISTS unsubscribes (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                email            TEXT UNIQUE NOT NULL,
                unsubscribed_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_leads_status    ON leads(status);
            CREATE INDEX IF NOT EXISTS idx_leads_priority  ON leads(priority);
            CREATE INDEX IF NOT EXISTS idx_leads_email     ON leads(email);
            CREATE INDEX IF NOT EXISTS idx_emails_lead_id  ON emails(lead_id);
        """)
    logger.info("Baza podatkov inicializirana: %s", DATABASE_PATH)


@contextmanager
def get_conn():
    """Context manager za SQLite povezavo."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── Generiranje ID-jev ───────────────────────────────────────────────────────

def next_lead_id() -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM leads").fetchone()
        n = row["cnt"] + 1
    return f"LEAD-{n:03d}"


# ─── Leads CRUD ───────────────────────────────────────────────────────────────

def insert_lead(data: dict) -> Optional[str]:
    """
    Vstavi novega leada. Vrne lead_id ali None, če email že obstaja.
    """
    lead_id = data.get("lead_id") or next_lead_id()

    # Prepreči podvajanje po emailu ali imenu podjetja
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT lead_id FROM leads WHERE email = ? OR company_name = ?",
            (data.get("email"), data.get("company_name")),
        ).fetchone()
        if existing:
            logger.debug("Lead že obstaja: %s", existing["lead_id"])
            return None

        conn.execute(
            """INSERT INTO leads (
                lead_id, company_name, contact_person, activity, skd_code,
                email, phone, address, city, region,
                website_url, website_status, website_year,
                facebook_url, instagram_url, data_source,
                qualification_score, criteria_matched, priority,
                recommended_template, status, notes
            ) VALUES (
                :lead_id, :company_name, :contact_person, :activity, :skd_code,
                :email, :phone, :address, :city, :region,
                :website_url, :website_status, :website_year,
                :facebook_url, :instagram_url, :data_source,
                :qualification_score, :criteria_matched, :priority,
                :recommended_template, :status, :notes
            )""",
            {
                "lead_id": lead_id,
                "company_name": data.get("company_name", ""),
                "contact_person": data.get("contact_person"),
                "activity": data.get("activity"),
                "skd_code": data.get("skd_code"),
                "email": data.get("email"),
                "phone": data.get("phone"),
                "address": data.get("address"),
                "city": data.get("city"),
                "region": data.get("region"),
                "website_url": data.get("website_url"),
                "website_status": data.get("website_status", "none"),
                "website_year": data.get("website_year"),
                "facebook_url": data.get("facebook_url"),
                "instagram_url": data.get("instagram_url"),
                "data_source": data.get("data_source"),
                "qualification_score": data.get("qualification_score", 0),
                "criteria_matched": json.dumps(data.get("criteria_matched", [])),
                "priority": data.get("priority", "NIZKA"),
                "recommended_template": data.get("recommended_template", "A"),
                "status": data.get("status", "ČAKA"),
                "notes": data.get("notes"),
            },
        )
    logger.info("Lead dodan: %s — %s", lead_id, data.get("company_name"))
    return lead_id


def get_lead(lead_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM leads WHERE lead_id = ?", (lead_id,)
        ).fetchone()
    return dict(row) if row else None


def get_leads(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    disqualified: int = 0,
    limit: Optional[int] = None,
) -> list[dict]:
    query = "SELECT * FROM leads WHERE disqualified = ?"
    params: list = [disqualified]
    if status:
        query += " AND status = ?"
        params.append(status)
    if priority:
        query += " AND priority = ?"
        params.append(priority)
    query += " ORDER BY qualification_score DESC, created_at ASC"
    if limit:
        query += f" LIMIT {int(limit)}"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_lead_status(lead_id: str, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE leads SET status = ?, last_contact_at = ? WHERE lead_id = ?",
            (status, datetime.utcnow().isoformat(), lead_id),
        )
    logger.info("Status leada %s posodobljen → %s", lead_id, status)


def update_lead_qualification(
    lead_id: str,
    score: int,
    criteria_matched: list,
    priority: str,
    template: str,
    disqualified: bool = False,
    disqualify_reason: str = "",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE leads SET
                qualification_score = ?,
                criteria_matched = ?,
                priority = ?,
                recommended_template = ?,
                disqualified = ?,
                disqualify_reason = ?
            WHERE lead_id = ?""",
            (
                score,
                json.dumps(criteria_matched),
                priority,
                template,
                1 if disqualified else 0,
                disqualify_reason,
                lead_id,
            ),
        )


def disqualify_lead(lead_id: str, reason: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE leads SET disqualified = 1, disqualify_reason = ? WHERE lead_id = ?",
            (reason, lead_id),
        )
    logger.info("Lead %s diskvalificiran: %s", lead_id, reason)


# ─── Emails CRUD ──────────────────────────────────────────────────────────────

def save_email_draft(lead_id: str, template_type: str, subject: str, body: str) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO emails (lead_id, template_type, subject, body)
               VALUES (?, ?, ?, ?)""",
            (lead_id, template_type, subject, body),
        )
        return cursor.lastrowid


def mark_email_sent(email_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE emails SET status = 'SENT', sent_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), email_id),
        )


def mark_email_opened(lead_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE emails SET status = 'OPENED', opened_at = ?
               WHERE lead_id = ? AND status = 'SENT'""",
            (datetime.utcnow().isoformat(), lead_id),
        )
    update_lead_status(lead_id, "ODPRT")


def mark_email_replied(lead_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE emails SET status = 'REPLIED', replied_at = ?
               WHERE lead_id = ? AND status IN ('SENT','OPENED')""",
            (datetime.utcnow().isoformat(), lead_id),
        )
    update_lead_status(lead_id, "ODGOVORIL")


def get_pending_emails(limit: int = 50) -> list[dict]:
    """Vrni emaile z statusom DRAFT, razvrščene po prioriteti leada."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT e.*, l.email AS recipient_email, l.priority, l.company_name
               FROM emails e
               JOIN leads l ON e.lead_id = l.lead_id
               WHERE e.status = 'DRAFT'
                 AND l.disqualified = 0
                 AND l.email IS NOT NULL
               ORDER BY
                 CASE l.priority WHEN 'VISOKA' THEN 1 WHEN 'SREDNJA' THEN 2 ELSE 3 END,
                 e.id ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_followup_candidates(days: int = 5) -> list[dict]:
    """Vrni leade, ki so bili kontaktirani pred vsaj `days` dnevi in niso odgovorili."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT l.* FROM leads l
               JOIN emails e ON l.lead_id = e.lead_id
               WHERE l.status = 'POSLANO'
                 AND e.sent_at < ?
                 AND e.template_type != 'C'
                 AND l.disqualified = 0
               GROUP BY l.lead_id""",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Odjave ───────────────────────────────────────────────────────────────────

def add_unsubscribe(email: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO unsubscribes (email) VALUES (?)",
            (email.lower().strip(),),
        )
    logger.info("Odjava zabeležena: %s", email)


def is_unsubscribed(email: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM unsubscribes WHERE email = ?",
            (email.lower().strip(),),
        ).fetchone()
    return row is not None


# ─── GDPR čiščenje ────────────────────────────────────────────────────────────

def gdpr_cleanup(months: int = 12) -> int:
    """Zbriše leade brez kontakta v zadnjih `months` mesecih. Vrne število izbrisanih."""
    cutoff = (datetime.utcnow() - timedelta(days=months * 30)).isoformat()
    with get_conn() as conn:
        # Zbriši emaile za stare leade
        conn.execute(
            """DELETE FROM emails WHERE lead_id IN (
               SELECT lead_id FROM leads
               WHERE (last_contact_at IS NULL AND created_at < ?)
                  OR last_contact_at < ?
            )""",
            (cutoff, cutoff),
        )
        cursor = conn.execute(
            """DELETE FROM leads
               WHERE (last_contact_at IS NULL AND created_at < ?)
                  OR last_contact_at < ?""",
            (cutoff, cutoff),
        )
        deleted = cursor.rowcount
    logger.info("GDPR čiščenje: %d leadov izbrisanih (starejši od %d mesecev)", deleted, months)
    return deleted


# ─── Statistika ───────────────────────────────────────────────────────────────

def get_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM leads WHERE disqualified = 0").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM leads WHERE disqualified = 0 GROUP BY status"
        ).fetchall()
        sent = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE status IN ('SENT','OPENED','REPLIED')"
        ).fetchone()[0]
        opened = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE status IN ('OPENED','REPLIED')"
        ).fetchone()[0]
        replied = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE status = 'REPLIED'"
        ).fetchone()[0]
        converted = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE status = 'KONVERTIRAN'"
        ).fetchone()[0]

    return {
        "total_leads": total,
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "emails_sent": sent,
        "emails_opened": opened,
        "emails_replied": replied,
        "converted": converted,
        "open_rate": round(opened / sent * 100, 1) if sent else 0.0,
        "reply_rate": round(replied / sent * 100, 1) if sent else 0.0,
        "conversion_rate": round(converted / sent * 100, 1) if sent else 0.0,
    }
