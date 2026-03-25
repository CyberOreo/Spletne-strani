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

logger = logging.getLogger(__name__)

_running = False
_scheduler_thread: threading.Thread | None = None


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

    # Importi scraperjev (lazy da ne upočasnimo zagona)
    from src.scrapers.bizi_scraper import BiziScraper
    from src.scrapers.euro_pages_scraper import EuroPagesScraper
    from src.scrapers.maps_scraper import MapsScraper
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

    logger.info("=" * 60)
    logger.info("DNEVNI PIPELINE STARTED: %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    logger.info("=" * 60)

    # ── 1. SCRAPING ────────────────────────────────────────────────────────────
    if not skip_scrape:
        logger.info("FAZA 1: Scraping...")
        try:
            leads_raw = await _scrape_bulk(DAILY_BULK_CONFIG, concurrency=SCRAPE_CONCURRENCY)
            for lead in leads_raw:
                if insert_lead(lead):
                    stats["scraped"] += 1
            logger.info("Scraping: %d novih leadov", stats["scraped"])
        except Exception as exc:
            logger.error("FAZA 1 napaka (scraping) — nadaljujem: %s", exc, exc_info=True)
            stats["errors"] = stats.get("errors", [])
            stats["errors"].append(f"scraping: {exc}")

    # ── 2. KVALIFIKACIJA ───────────────────────────────────────────────────────
    logger.info("FAZA 2: Kvalifikacija...")
    try:
        q_stats = qualify_all(min_score=3)
        stats["qualified"] = q_stats.get("qualified", 0)
        stats["disqualified"] = q_stats.get("disqualified", 0)
    except Exception as exc:
        logger.error("FAZA 2 napaka (kvalifikacija) — nadaljujem: %s", exc, exc_info=True)

    # ── 3. GENERACIJA EMAILOV ──────────────────────────────────────────────────
    logger.info("FAZA 3: Generacija emailov...")
    try:
        eg_stats = generate_all_emails()
        stats["emails_generated"] = eg_stats.get("generated", 0)
    except Exception as exc:
        logger.error("FAZA 3 napaka (generacija) — nadaljujem: %s", exc, exc_info=True)

    # ── 4. PREVERJANJE ODGOVOROV (IMAP) ───────────────────────────────────────
    logger.info("FAZA 4: Preverjanje odgovorov...")
    try:
        reply_stats = check_replies()
        stats["replies_detected"] = reply_stats.get("replied", 0)
        if reply_stats.get("replied", 0) > 0:
            await _generate_previews_for_replies()
    except Exception as exc:
        logger.warning("FAZA 4 napaka (IMAP) — nadaljujem: %s", exc)

    # ── 5. FOLLOW-UP ──────────────────────────────────────────────────────────
    logger.info("FAZA 5: Follow-up...")
    try:
        fu_stats = generate_followups(followup_days=5)
        stats["followups_generated"] = fu_stats.get("generated", 0)
    except Exception as exc:
        logger.error("FAZA 5 napaka (follow-up) — nadaljujem: %s", exc, exc_info=True)

    # ── 6. POŠILJANJE ─────────────────────────────────────────────────────────
    if not skip_send:
        logger.info("FAZA 6: Pošiljanje %d emailov...", daily_limit)
        try:
            workers = min(len(__import__('src.config', fromlist=['SMTP_ACCOUNTS']).SMTP_ACCOUNTS), 5) or 1
            send_stats = send_batch_threaded(
                daily_limit=daily_limit,
                dry_run=dry_run,
                workers=workers,
            )
            stats["emails_sent"] = send_stats.get("sent", 0)
        except Exception as exc:
            logger.error("FAZA 6 napaka (pošiljanje) — nadaljujem: %s", exc, exc_info=True)

    # ── 7. GDPR ČIŠČENJE ──────────────────────────────────────────────────────
    logger.info("FAZA 7: GDPR čiščenje...")
    try:
        stats["gdpr_deleted"] = gdpr_cleanup(months=12)
    except Exception as exc:
        logger.warning("FAZA 7 napaka (GDPR) — nadaljujem: %s", exc)

    # ── 8. POROČILO ───────────────────────────────────────────────────────────
    logger.info("FAZA 8: Poročilo...")
    print_report()
    export_csv()

    logger.info("=" * 60)
    logger.info(
        "PIPELINE KONČAN | Scraping: %d | Poslano: %d | Konverzije: —",
        stats["scraped"], stats["emails_sent"],
    )
    logger.info("=" * 60)

    return stats


async def _scrape_bulk(configs: list[dict], concurrency: int = 10) -> list[dict]:
    """Vzporedno scrapanje iz vseh virov."""
    from src.scrapers.bizi_scraper import BiziScraper
    from src.scrapers.euro_pages_scraper import EuroPagesScraper
    from src.scrapers.maps_scraper import MapsScraper
    from src.scrapers.zlate_strani_scraper import ZlateStraniScraper
    from src.scrapers.ajpes_scraper import AjpesScraper
    import importlib

    SCRAPER_MAP = {
        "bizi": BiziScraper,
        "zlate_strani": ZlateStraniScraper,
        "ajpes": AjpesScraper,
        "euro_pages": EuroPagesScraper,
        "maps": MapsScraper,
    }

    COUNTRY_SCRAPERS = {
        "de": "src.scrapers.country_scrapers.de_scraper.DeScraper",
        "at": "src.scrapers.country_scrapers.at_scraper.AtScraper",
        "hr": "src.scrapers.country_scrapers.hr_scraper.HrScraper",
        "it": "src.scrapers.country_scrapers.it_scraper.ItScraper",
        "cz": "src.scrapers.country_scrapers.cz_scraper.CzScraper",
        "hu": "src.scrapers.country_scrapers.hu_scraper.HuScraper",
        "pl": "src.scrapers.country_scrapers.pl_scraper.PlScraper",
        "ro": "src.scrapers.country_scrapers.ro_scraper.RoScraper",
    }

    semaphore = asyncio.Semaphore(concurrency)
    all_results: list[dict] = []

    async def scrape_one(cfg: dict) -> list[dict]:
        async with semaphore:
            country = cfg.get("country", "si")
            source = cfg.get("source", "")
            industry = cfg.get("industry", "")
            limit = cfg.get("limit", 100)

            # Določi scraper razred
            scraper_cls = None
            if source and source in SCRAPER_MAP:
                scraper_cls = SCRAPER_MAP[source]
            elif country in COUNTRY_SCRAPERS:
                mod_path, cls_name = COUNTRY_SCRAPERS[country].rsplit(".", 1)
                try:
                    mod = importlib.import_module(mod_path)
                    scraper_cls = getattr(mod, cls_name)
                except (ImportError, AttributeError) as e:
                    logger.warning("Scraper za %s ni dostopen: %s", country, e)
                    return []
            elif country == "si":
                scraper_cls = BiziScraper
            else:
                scraper_cls = EuroPagesScraper

            try:
                async with scraper_cls() as scraper:
                    return await scraper.scrape(
                        industry=industry,
                        country=country,
                        limit=limit,
                    )
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
