"""SMTP pošiljanje z rotacijo računov, rate limitingom in GDPR pravili."""
import itertools
import logging
import random
import smtplib
import threading
import time
import uuid
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from src.config import (
    SMTP_ACCOUNTS, MIN_DELAY_SECONDS, MAX_DELAY_SECONDS, DAILY_EMAIL_LIMIT,
    TRACKING_BASE_URL, SEND_WINDOW_START, SEND_WINDOW_END, SEND_WEEKEND,
    UNSUBSCRIBE_BASE_URL,
)
from src.database import (
    get_pending_emails, mark_email_sent, update_lead_status, is_unsubscribed,
    get_conn
)

logger = logging.getLogger(__name__)

# ─── Dnevni števec pošiljanja ────────────────────────────────────────────────
_sent_today: dict[str, int] = {}   # {datum_str: count}
_sent_lock = threading.Lock()


def _today_str() -> str:
    return date.today().isoformat()


def _get_sent_today() -> int:
    today = _today_str()
    with _sent_lock:
        return _sent_today.get(today, 0)


def _increment_sent() -> None:
    today = _today_str()
    with _sent_lock:
        _sent_today[today] = _sent_today.get(today, 0) + 1


# ─── Čas pošiljanja ───────────────────────────────────────────────────────────

def _is_send_window() -> bool:
    """Preveri čas pošiljanja glede na konfiguracijo."""
    now = datetime.now()
    if not SEND_WEEKEND and now.weekday() >= 5:
        return False
    start_h, start_m = map(int, SEND_WINDOW_START.split(":"))
    end_h, end_m = map(int, SEND_WINDOW_END.split(":"))
    now_minutes = now.hour * 60 + now.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    return start_minutes <= now_minutes < end_minutes


# ─── Rotacija SMTP računov ────────────────────────────────────────────────────

class SmtpAccountManager:
    """Round-robin rotacija SMTP računov z individualnimi dnevnimi limiti."""

    def __init__(self):
        self._accounts = SMTP_ACCOUNTS or []
        self._cycle = itertools.cycle(self._accounts) if self._accounts else None
        self._daily_counts: dict[str, dict[str, int]] = {}  # {datum: {user: count}}
        self._lock = threading.Lock()

    def _today_counts(self) -> dict[str, int]:
        today = _today_str()
        with self._lock:
            if today not in self._daily_counts:
                self._daily_counts[today] = {}
            return self._daily_counts[today]

    def get_available_account(self) -> dict | None:
        """Vrni naslednji razpoložljiv SMTP račun (ki ni dosegel dnevnega limita)."""
        if not self._accounts:
            return None

        counts = self._today_counts()
        tried = 0
        while tried < len(self._accounts):
            acc = next(self._cycle)
            user = acc.get("user", "")
            limit = acc.get("daily_limit", 1000)
            sent = counts.get(user, 0)
            if sent < limit:
                return acc
            tried += 1
        return None  # Vsi računi so dosegli limit

    def mark_sent(self, account: dict) -> None:
        user = account.get("user", "")
        counts = self._today_counts()
        with self._lock:
            counts[user] = counts.get(user, 0) + 1


_smtp_manager = SmtpAccountManager()


# ─── Pošiljanje posameznega emaila ───────────────────────────────────────────

def _build_message(
    to_email: str,
    subject: str,
    body: str,
    from_name: str,
    from_email: str,
    lead_id: str = "",
    email_id: int = 0,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")

    # ── Obvezni headers ────────────────────────────────────────────────────────
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_email.split("@")[-1])
    msg["Reply-To"] = f"{from_name} <{from_email}>"
    msg["MIME-Version"] = "1.0"

    # ── List-Unsubscribe (KRITIČNO za deliverability) ─────────────────────────
    # Gmail/Yahoo/Outlook zahtevajo to za bulk senderje od feb 2024
    unsubscribe_mailto = f"mailto:{from_email}?subject=ODJAVA%20{to_email}"
    if UNSUBSCRIBE_BASE_URL:
        unsubscribe_url = f"{UNSUBSCRIBE_BASE_URL}/unsubscribe?email={to_email}"
        msg["List-Unsubscribe"] = f"<{unsubscribe_mailto}>, <{unsubscribe_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    else:
        msg["List-Unsubscribe"] = f"<{unsubscribe_mailto}>"

    # ── HTML email ─────────────────────────────────────────────────────────────
    html_paragraphs = "".join(
        f"<p>{line}</p>" if line.strip() else "<br>"
        for line in body.split("\n")
    )

    # Tracking pixel (opcijsko)
    pixel = ""
    if TRACKING_BASE_URL and email_id:
        pixel = f'<img src="{TRACKING_BASE_URL}/open/{email_id}" width="1" height="1" alt="" style="display:none!important;visibility:hidden;opacity:0">'

    html_body = f"""<!DOCTYPE html>
<html lang="sl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:Arial,sans-serif;font-size:15px;line-height:1.6;color:#222;max-width:600px;margin:0 auto;padding:20px}}
p{{margin:0 0 12px}}
</style></head>
<body>
{html_paragraphs}
{pixel}
</body></html>"""

    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def send_single_email(
    to_email: str,
    subject: str,
    body: str,
    account: dict,
    lead_id: str = "",
    email_id: int = 0,
    dry_run: bool = False,
) -> bool:
    """Pošlje en email. Vrne True pri uspehu."""
    if dry_run:
        logger.info("[DRY-RUN] Pošiljam na %s: %s", to_email, subject)
        return True

    msg = _build_message(
        to_email=to_email,
        subject=subject,
        body=body,
        from_name=account.get("name", ""),
        from_email=account.get("user", ""),
        lead_id=lead_id,
        email_id=email_id,
    )

    try:
        with smtplib.SMTP(account["host"], account["port"], timeout=30) as smtp:
            smtp.starttls()
            smtp.login(account["user"], account["password"])
            smtp.sendmail(account["user"], to_email, msg.as_string())
        logger.info("Poslano → %s (%s)", to_email, lead_id)
        return True
    except smtplib.SMTPRecipientsRefused:
        logger.warning("Email zavrnjen: %s", to_email)
        return False
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP avtentikacija napaka za %s", account.get("user"))
        return False
    except Exception as exc:
        logger.error("SMTP napaka pri pošiljanju na %s: %s", to_email, exc)
        return False


# ─── Množično pošiljanje ─────────────────────────────────────────────────────

def send_batch(
    daily_limit: int = None,
    dry_run: bool = False,
    smtp_account_user: str = None,
) -> dict:
    """
    Pošlje paket emailov (do daily_limit). Spoštuje:
    - Čas pošiljanja (pon–pet, 8–17)
    - Dnevni limit (skupni + per-account)
    - Odjave
    - Naključni zamik med emaili
    Vrne statistiko.
    """
    if not dry_run and not _is_send_window():
        logger.info("Zunaj časa pošiljanja (pon–pet 8:00–17:00)")
        return {"sent": 0, "skipped": 0, "reason": "outside_window"}

    effective_limit = daily_limit or DAILY_EMAIL_LIMIT
    already_sent = _get_sent_today()
    remaining = effective_limit - already_sent

    if remaining <= 0 and not dry_run:
        logger.info("Dnevni limit dosežen: %d/%d", already_sent, effective_limit)
        return {"sent": 0, "skipped": 0, "reason": "daily_limit_reached"}

    pending = get_pending_emails(limit=remaining)
    stats = {"sent": 0, "skipped": 0, "failed": 0}

    for email_rec in pending:
        if _get_sent_today() >= effective_limit and not dry_run:
            break

        to_email = email_rec.get("recipient_email") or ""
        if not to_email or "@" not in to_email:
            stats["skipped"] += 1
            continue

        # Preveri odjavo
        if is_unsubscribed(to_email):
            logger.info("Odjavljen: %s", to_email)
            stats["skipped"] += 1
            continue

        # Pridobi SMTP račun
        if smtp_account_user:
            account = next(
                (a for a in SMTP_ACCOUNTS if a.get("user") == smtp_account_user), None
            )
        else:
            account = _smtp_manager.get_available_account()

        if not account:
            logger.warning("Ni razpoložljivih SMTP računov")
            break

        ok = send_single_email(
            to_email=to_email,
            subject=email_rec["subject"],
            body=email_rec["body"],
            account=account,
            lead_id=email_rec["lead_id"],
            email_id=email_rec["id"],
            dry_run=dry_run,
        )

        if ok:
            if not dry_run:
                mark_email_sent(email_rec["id"])
                update_lead_status(email_rec["lead_id"], "POSLANO")
                _smtp_manager.mark_sent(account)
                _increment_sent()
            stats["sent"] += 1
        else:
            stats["failed"] += 1

        # Naključni zamik
        if not dry_run:
            delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
            time.sleep(delay)

    logger.info(
        "Pošiljanje končano: %d poslanih, %d preskočenih, %d napak",
        stats["sent"], stats["skipped"], stats["failed"],
    )
    return stats


# ─── Vzporedno pošiljanje (threaded za večje obsege) ─────────────────────────

def send_batch_threaded(daily_limit: int = 3000, dry_run: bool = False, workers: int = 3) -> dict:
    """
    Razdeli pošiljanje med `workers` niti (po ena na SMTP račun).
    Koristno za > 1000 emailov/dan.
    """
    total_stats = {"sent": 0, "skipped": 0, "failed": 0}
    per_worker = daily_limit // workers
    threads = []
    results = []

    for i in range(min(workers, len(SMTP_ACCOUNTS))):
        acc = SMTP_ACCOUNTS[i]

        def worker(account=acc, limit=per_worker, res=results):
            s = send_batch(daily_limit=limit, dry_run=dry_run, smtp_account_user=account["user"])
            res.append(s)

        t = threading.Thread(target=worker, daemon=True)
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for r in results:
        total_stats["sent"] += r.get("sent", 0)
        total_stats["skipped"] += r.get("skipped", 0)
        total_stats["failed"] += r.get("failed", 0)

    return total_stats
