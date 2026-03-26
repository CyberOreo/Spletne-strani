"""Avtomatski dnevni scheduler — zažene celoten pipeline ob nastavljenem času."""
import asyncio
import logging
import signal
import sys
import threading
import time
from datetime import datetime

import schedule

from src.config import (
    DAILY_RUN_TIME, DAILY_EMAIL_LIMIT, DAILY_BULK_CONFIG, SCRAPE_CONCURRENCY,
    OVERNIGHT_SCRAPE_TIME, OVERNIGHT_SEND_TIME,
)
from src.database import init_db, gdpr_cleanup
from src import events

logger = logging.getLogger(__name__)

_running = False
_scheduler_thread: threading.Thread | None = None

STAGE_LABELS = {
    "start":     "Zaganjam...",
    "scraping":  "Scraping leadov",
    "qualify":   "Kvalifikacija",
    "generate":  "Generacija emailov",
    "replies":   "Preverjam odgovore",
    "followup":  "Follow-up emaili",
    "sending":   "Pošiljanje emailov",
    "cleanup":   "GDPR čiščenje",
    "complete":  "Končano",
}

def _set_stage(stage: str, msg: str = "", pct: int = None) -> None:
    label = STAGE_LABELS.get(stage, stage)
    events.update_pipeline({"stage": stage, "stage_label": label, "message": msg,
                             "progress_pct": pct if pct is not None else _stage_pct(stage)})
    events.add_event(f"{label}{': ' + msg if msg else ''}", "info")
    logger.info("[%s] %s", stage.upper(), msg or label)

def _stage_pct(stage: str) -> int:
    order = list(STAGE_LABELS.keys())
    try:
        return round(order.index(stage) / (len(order) - 1) * 100)
    except ValueError:
        return 0


# ─── Celoten dnevni pipeline ──────────────────────────────────────────────────

async def run_daily_pipeline(
    daily_limit: int = DAILY_EMAIL_LIMIT,
    dry_run: bool = False,
    skip_scrape: bool = False,
    skip_send: bool = False,
) -> dict:
    """
    Celoten avtomatski pipeline (en klik):
    1. Scraping → 3.000 leadov
    2. Kvalifikacija
    3. Generacija emailov
    4. Preverjanje odgovorov (IMAP)
    5. Follow-up
    6. Pošiljanje (3.000/dan)
    7. GDPR čiščenje
    8. Poročilo
    """
    from src.qualifier import qualify_all
    from src.email_generator import generate_all_emails
    from src.email_sender import send_batch_threaded
    from src.tracker import check_replies, generate_followups
    from src.reporter import print_report, export_csv

    from src.database import insert_lead

    stats = {
        "date": datetime.now().isoformat(),
        "scraped": 0,
        "qualified": 0,
        "disqualified": 0,
        "emails_generated": 0,
        "replies_detected": 0,
        "followups_generated": 0,
        "emails_sent": 0,
        "gdpr_deleted": 0,
    }

    events.update_pipeline({"status": "running", "started_at": datetime.now().isoformat(),
                             "scraped": 0, "qualified": 0, "emails_generated": 0,
                             "emails_sent": 0, "errors": 0})
    events.add_event("Pipeline zagnan", "success")
    logger.info("=" * 60)
    logger.info("DNEVNI PIPELINE STARTED: %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    logger.info("=" * 60)

    # ── 1. SCRAPING ────────────────────────────────────────────────────────────
    if not skip_scrape:
        _set_stage("scraping", "", 5)
        try:
            leads_raw = await _scrape_bulk(DAILY_BULK_CONFIG, concurrency=SCRAPE_CONCURRENCY)
            for lead in leads_raw:
                if insert_lead(lead):
                    stats["scraped"] += 1
                    if stats["scraped"] % 100 == 0:
                        events.update_pipeline({"scraped": stats["scraped"]})
                        events.add_event(f"Scrapano {stats['scraped']} leadov...", "info")
            events.update_pipeline({"scraped": stats["scraped"]})
            events.add_event(f"Scraping končan: {stats['scraped']} novih leadov", "success")
        except Exception as exc:
            logger.error("FAZA 1 napaka (scraping) — nadaljujem: %s", exc, exc_info=True)
            events.add_event(f"Scraping napaka: {exc}", "error")
            events.update_pipeline({"errors": events.get_state().get("errors", 0) + 1})

    # ── 2. KVALIFIKACIJA ───────────────────────────────────────────────────────
    _set_stage("qualify", "", 30)
    try:
        q_stats = qualify_all(min_score=3)
        stats["qualified"] = q_stats.get("qualified", 0)
        stats["disqualified"] = q_stats.get("disqualified", 0)
        events.update_pipeline({"qualified": stats["qualified"]})
        events.add_event(f"Kvalificirano: {stats['qualified']} leadov ({stats['disqualified']} izločenih)", "success")
    except Exception as exc:
        logger.error("FAZA 2 napaka (kvalifikacija) — nadaljujem: %s", exc, exc_info=True)
        events.add_event(f"Kvalifikacija napaka: {exc}", "error")

    # ── 3. GENERACIJA EMAILOV ──────────────────────────────────────────────────
    _set_stage("generate", "", 45)
    try:
        eg_stats = generate_all_emails()
        stats["emails_generated"] = eg_stats.get("generated", 0)
        events.update_pipeline({"emails_generated": stats["emails_generated"]})
        events.add_event(f"Emaili generirani: {stats['emails_generated']}", "success")
    except Exception as exc:
        logger.error("FAZA 3 napaka (generacija) — nadaljujem: %s", exc, exc_info=True)
        events.add_event(f"Generacija napaka: {exc}", "error")

    # ── 4. PREVERJANJE ODGOVOROV (IMAP) ───────────────────────────────────────
    _set_stage("replies", "", 55)
    try:
        reply_stats = check_replies()
        stats["replies_detected"] = reply_stats.get("replied", 0)
        if stats["replies_detected"] > 0:
            events.add_event(f"Novih odgovorov: {stats['replies_detected']}", "success")
            await _generate_previews_for_replies()
    except Exception as exc:
        logger.warning("FAZA 4 napaka (IMAP) — nadaljujem: %s", exc)
        events.add_event("IMAP ni konfiguriran — preskakujem", "warning")

    # ── 5. FOLLOW-UP ──────────────────────────────────────────────────────────
    _set_stage("followup", "", 65)
    try:
        fu_stats = generate_followups(followup_days=5)
        stats["followups_generated"] = fu_stats.get("generated", 0)
        if stats["followups_generated"] > 0:
            events.add_event(f"Follow-up emaili: {stats['followups_generated']}", "success")
    except Exception as exc:
        logger.error("FAZA 5 napaka (follow-up) — nadaljujem: %s", exc, exc_info=True)
        events.add_event(f"Follow-up napaka: {exc}", "error")

    # ── 6. POŠILJANJE ─────────────────────────────────────────────────────────
    if not skip_send:
        _set_stage("sending", f"Pošiljam do {daily_limit} emailov...", 75)
        try:
            workers = min(len(__import__('src.config', fromlist=['SMTP_ACCOUNTS']).SMTP_ACCOUNTS), 5) or 1
            send_stats = send_batch_threaded(daily_limit=daily_limit, dry_run=dry_run, workers=workers)
            stats["emails_sent"] = send_stats.get("sent", 0)
            events.update_pipeline({"emails_sent": stats["emails_sent"]})
            events.add_event(f"Poslano: {stats['emails_sent']} emailov", "success")
        except Exception as exc:
            logger.error("FAZA 6 napaka (pošiljanje) — nadaljujem: %s", exc, exc_info=True)
            events.add_event(f"Pošiljanje napaka: {exc}", "error")

    # ── 7. GDPR ČIŠČENJE ──────────────────────────────────────────────────────
    _set_stage("cleanup", "", 95)
    try:
        stats["gdpr_deleted"] = gdpr_cleanup(months=12)
    except Exception as exc:
        logger.warning("FAZA 7 napaka (GDPR) — nadaljujem: %s", exc)

    # ── 8. POROČILO ───────────────────────────────────────────────────────────
    _set_stage("complete", "Generiram poročilo...", 98)
    logger.info("FAZA 8: Poročilo...")
    try:
        print_report()
        export_csv()
    except Exception as exc:
        logger.warning("FAZA 8 napaka (poročilo) — nadaljujem: %s", exc)

    logger.info("=" * 60)
    logger.info(
        "PIPELINE KONČAN | Scraping: %d | Poslano: %d | Konverzije: —",
        stats["scraped"], stats["emails_sent"],
    )
    logger.info("=" * 60)

    events.update_pipeline({
        "status": "done",
        "stage": "complete",
        "stage_label": "Končano",
        "message": f"Pipeline končan ✓ — Scrapano: {stats['scraped']}, Poslano: {stats['emails_sent']}",
        "progress_pct": 100,
    })
    events.add_event(
        f"Pipeline končan ✓  Scraped: {stats['scraped']} · Qualified: {stats['qualified']} · Sent: {stats['emails_sent']}",
        "success",
    )

    return stats


async def _scrape_bulk(configs: list[dict], concurrency: int = 1) -> list[dict]:
    """Vzporedno scrapanje — primarno OpenStreetMap Overpass API."""
    from src.scrapers.overpass_scraper import OverpassScraper
    from src.scrapers.maps_scraper import MapsScraper

    # Manjša concurrency za Overpass da ne preobremenimo API-ja
    semaphore = asyncio.Semaphore(concurrency)
    all_results: list[dict] = []

    async def scrape_one(cfg: dict) -> list[dict]:
        async with semaphore:
            country  = cfg.get("country", "si")
            source   = cfg.get("source", "overpass")
            industry = cfg.get("industry", "")
            limit    = cfg.get("limit", 100)

            if source == "maps":
                scraper_cls = MapsScraper
            else:
                # Privzeto: Overpass (OpenStreetMap) — brezplačen, brez ključev
                scraper_cls = OverpassScraper

            try:
                async with scraper_cls() as scraper:
                    results = await scraper.scrape(
                        industry=industry,
                        country=country,
                        limit=limit,
                    )
                    logger.info("Overpass %s/%s: %d leadov", country, industry or "*", len(results))
                    return results
            except Exception as exc:
                logger.error("Napaka pri scraping (%s/%s): %s", country, industry, exc)
                return []

    tasks = [scrape_one(cfg) for cfg in configs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, list):
            all_results.extend(r)
        elif isinstance(r, Exception):
            logger.error("Scraping task napaka: %s", r)

    return all_results


async def _generate_previews_for_replies() -> None:
    """Za vse leade z odgovori generira preview stran."""
    from src.database import get_leads
    from src.preview_generator import generate_preview, send_preview_email

    replied = get_leads(status="ODGOVORIL")
    for lead in replied:
        url = generate_preview(lead["lead_id"])
        if url:
            send_preview_email(lead["lead_id"], url)


# ─── Scheduler daemon ─────────────────────────────────────────────────────────

def _scheduler_loop(daily_limit: int, dry_run: bool):
    """Tek schedulerja v ozadju."""
    global _running
    logger.info("Scheduler zagnan. Dnevni čas: %s (pon–pet)", DAILY_RUN_TIME)

    def job():
        logger.info("Scheduler: zaganjam dnevni pipeline...")
        asyncio.run(run_daily_pipeline(daily_limit=daily_limit, dry_run=dry_run))

    schedule.every().monday.at(DAILY_RUN_TIME).do(job)
    schedule.every().tuesday.at(DAILY_RUN_TIME).do(job)
    schedule.every().wednesday.at(DAILY_RUN_TIME).do(job)
    schedule.every().thursday.at(DAILY_RUN_TIME).do(job)
    schedule.every().friday.at(DAILY_RUN_TIME).do(job)

    while _running:
        schedule.run_pending()
        time.sleep(30)


def start_scheduler(daily_limit: int = DAILY_EMAIL_LIMIT, dry_run: bool = False) -> None:
    global _running, _scheduler_thread
    if _running:
        logger.warning("Scheduler že teče")
        return
    _running = True
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        args=(daily_limit, dry_run),
        daemon=True,
        name="daily-scheduler",
    )
    _scheduler_thread.start()
    logger.info("Scheduler zagnan v ozadju")


def stop_scheduler() -> None:
    global _running
    _running = False
    schedule.clear()
    logger.info("Scheduler ustavljen")


def scheduler_status() -> dict:
    return {
        "running": _running,
        "next_run": str(schedule.next_run()) if schedule.jobs else "—",
        "jobs": len(schedule.jobs),
        "daily_time": DAILY_RUN_TIME,
    }


# ─── Overnight scheduler ──────────────────────────────────────────────────────

def start_overnight_scheduler(daily_limit: int = DAILY_EMAIL_LIMIT, dry_run: bool = False) -> None:
    """
    Overnight način:
    - Ob OVERNIGHT_SCRAPE_TIME (privzeto 22:00): scraping + kvalifikacija + generacija emailov
    - Ob OVERNIGHT_SEND_TIME (privzeto 08:00): pošiljanje emailov
    Idealno za pustiti PC čez noč.
    """
    global _running, _scheduler_thread
    if _running:
        logger.warning("Scheduler že teče")
        return

    _running = True

    def _run_with_retry(name: str, coro_fn, max_retries: int = 3, retry_delay: int = 300):
        """Zažene async funkcijo z avtomatskim ponovnim zagonom ob napaki."""
        for attempt in range(1, max_retries + 1):
            try:
                logger.info("OVERNIGHT [%s] — zagon (poskus %d/%d)", name, attempt, max_retries)
                asyncio.run(coro_fn())
                logger.info("OVERNIGHT [%s] — uspešno končano", name)
                return
            except Exception as exc:
                logger.error(
                    "OVERNIGHT [%s] napaka (poskus %d/%d): %s",
                    name, attempt, max_retries, exc, exc_info=True,
                )
                if attempt < max_retries:
                    logger.info("OVERNIGHT [%s] — čakam %ds pred ponovnim zagonom...", name, retry_delay)
                    time.sleep(retry_delay)
                else:
                    logger.critical(
                        "OVERNIGHT [%s] — vse %d ponovitve neuspešne. "
                        "Preveri logs/ mapo zjutraj.", name, max_retries,
                    )

    def scrape_job():
        logger.info("OVERNIGHT: Začenjam nočni scraping ob %s", datetime.now().strftime("%H:%M"))
        _run_with_retry(
            "scraping",
            lambda: run_daily_pipeline(daily_limit=daily_limit, dry_run=dry_run, skip_send=True),
            max_retries=3,
            retry_delay=300,  # 5 minut med ponovnimi poskusi
        )
        logger.info("OVERNIGHT: Nočni scraping končan. Emaili bodo poslani ob %s", OVERNIGHT_SEND_TIME)

    def send_job():
        logger.info("OVERNIGHT: Začenjam jutranje pošiljanje ob %s", datetime.now().strftime("%H:%M"))
        _run_with_retry(
            "posiljanje",
            lambda: run_daily_pipeline(daily_limit=daily_limit, dry_run=dry_run, skip_scrape=True),
            max_retries=3,
            retry_delay=120,  # 2 minuti med ponovnimi poskusi
        )
        logger.info("OVERNIGHT: Pošiljanje končano.")

    def loop():
        logger.info(
            "Overnight scheduler zagnan:\n"
            "  Scraping ob: %s (vsak dan)\n"
            "  Pošiljanje ob: %s (pon–pet)\n",
            OVERNIGHT_SCRAPE_TIME, OVERNIGHT_SEND_TIME,
        )
        schedule.every().day.at(OVERNIGHT_SCRAPE_TIME).do(scrape_job)
        schedule.every().monday.at(OVERNIGHT_SEND_TIME).do(send_job)
        schedule.every().tuesday.at(OVERNIGHT_SEND_TIME).do(send_job)
        schedule.every().wednesday.at(OVERNIGHT_SEND_TIME).do(send_job)
        schedule.every().thursday.at(OVERNIGHT_SEND_TIME).do(send_job)
        schedule.every().friday.at(OVERNIGHT_SEND_TIME).do(send_job)
        while _running:
            schedule.run_pending()
            time.sleep(30)

    _scheduler_thread = threading.Thread(target=loop, daemon=True, name="overnight-scheduler")
    _scheduler_thread.start()
    logger.info("Overnight scheduler zagnan")
