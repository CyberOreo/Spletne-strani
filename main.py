#!/usr/bin/env python3
"""
B2B Lead Generation System — EU
Zagon: python main.py --help
En klik:  python main.py run --daily
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        RichHandler(rich_tracebacks=True, show_path=False),
        logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")
console = Console()

# ─── Inicializacija baze pri zagonu ───────────────────────────────────────────
from src.database import init_db
init_db()


# ══════════════════════════════════════════════════════════════════════════════
# CLI SKUPINA
# ══════════════════════════════════════════════════════════════════════════════

@click.group()
@click.version_option("1.0.0", prog_name="B2B Lead Gen EU")
def cli():
    """B2B Lead Generation System za EU — prodaja spletnih strani."""


# ──────────────────────────────────────────────────────────────────────────────
# RUN --daily  (en klik — celoten pipeline)
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("run")
@click.option("--daily", is_flag=True, help="Zaženi celoten dnevni pipeline")
@click.option("--daily-limit", default=3000, show_default=True, help="Max emailov na dan")
@click.option("--dry-run", is_flag=True, help="Simulacija brez dejanskega pošiljanja")
@click.option("--skip-scrape", is_flag=True, help="Preskoči scraping")
@click.option("--skip-send", is_flag=True, help="Preskoči pošiljanje")
def cmd_run(daily, daily_limit, dry_run, skip_scrape, skip_send):
    """[GLAVNI UKAZ] Celoten avtomatski pipeline — 3.000 leadov + 3.000 emailov."""
    if not daily:
        console.print("[yellow]Namig: uporabi --daily za celoten pipeline[/]")
        console.print("  python main.py run --daily")
        return

    console.rule("[bold green]B2B Lead Generation — DNEVNI PIPELINE[/]")
    if dry_run:
        console.print("[yellow]⚠️  DRY-RUN način — emaili se ne bodo dejansko poslali[/]")

    from src.scheduler import run_daily_pipeline
    stats = asyncio.run(
        run_daily_pipeline(
            daily_limit=daily_limit,
            dry_run=dry_run,
            skip_scrape=skip_scrape,
            skip_send=skip_send,
        )
    )

    console.print()
    console.rule("[bold]Rezultati[/]")
    for k, v in stats.items():
        if k != "date":
            console.print(f"  {k}: [bold]{v}[/]")


# ──────────────────────────────────────────────────────────────────────────────
# SCRAPE
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("scrape")
@click.option("--country", default="si", show_default=True,
              help="Država (si/hr/at/de/it/cz/hu/pl/ro/all)")
@click.option("--industry", default="plumber", show_default=True,
              help="Industrija (plumber/electrician/hair_salon/...)")
@click.option("--source", default="", help="Vir (bizi/euro_pages/maps/...)")
@click.option("--limit", default=100, show_default=True, help="Max leadov")
@click.option("--skd-code", default="", help="SKD koda (npr. 43.22)")
@click.option("--region", default="", help="Regija/mesto")
@click.option("--dry-run", is_flag=True, help="Izpiši rezultate, ne shrani")
def cmd_scrape(country, industry, source, limit, skd_code, region, dry_run):
    """Zberi leade iz enega vira."""
    from src.config import COUNTRIES, ALL_COUNTRY_CODES, REGIJE_PO_DRZAVAH
    from src.database import insert_lead
    from src.scheduler import _scrape_bulk

    countries_to_scrape = ALL_COUNTRY_CODES if country == "all" else [country]
    total_inserted = 0

    for c in countries_to_scrape:
        regions = [region] if region else (REGIJE_PO_DRZAVAH.get(c, [""])[:3])
        for reg in regions:
            cfg = [{"country": c, "industry": industry, "source": source,
                    "limit": limit // len(regions), "skd_code": skd_code, "region": reg}]
            leads = asyncio.run(_scrape_bulk(cfg))
            for lead in leads:
                if dry_run:
                    console.print(f"  [dim]{lead.get('company_name')}[/] | {lead.get('email')} | {lead.get('city')}")
                else:
                    if insert_lead(lead):
                        total_inserted += 1

    if not dry_run:
        console.print(f"[green]Shranjeno {total_inserted} novih leadov[/]")
    else:
        console.print(f"[dim]DRY-RUN: {len(leads)} najdenih[/]")


@cli.command("scrape-bulk")
@click.option("--config", default="", help="Pot do JSON config datoteke")
@click.option("--dry-run", is_flag=True)
def cmd_scrape_bulk(config, dry_run):
    """Vzporedno scrapanje iz vseh virov (bulk mode)."""
    from src.config import DAILY_BULK_CONFIG
    from src.database import insert_lead
    from src.scheduler import _scrape_bulk

    if config:
        with open(config) as f:
            bulk_cfg = json.load(f)
    else:
        bulk_cfg = DAILY_BULK_CONFIG

    console.print(f"[cyan]Scrapanje iz {len(bulk_cfg)} konfiguracij...[/]")
    leads = asyncio.run(_scrape_bulk(bulk_cfg))

    inserted = 0
    for lead in leads:
        if not dry_run and insert_lead(lead):
            inserted += 1

    console.print(f"[green]Najdeno: {len(leads)} | Shranjeno: {inserted}[/]")


# ──────────────────────────────────────────────────────────────────────────────
# QUALIFY
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("qualify")
@click.option("--min-score", default=3, show_default=True, help="Minimalni score (1–10)")
def cmd_qualify(min_score):
    """Kvalificiraj vse nove leade (7-kriterijev točkovanje)."""
    from src.qualifier import qualify_all
    console.print("[cyan]Kvalifikacija leadov...[/]")
    stats = qualify_all(min_score=min_score)
    console.print(f"Obdelani: [bold]{stats['processed']}[/]  |  "
                  f"Kvalificirani: [green]{stats['qualified']}[/]  |  "
                  f"Diskvalificirani: [red]{stats['disqualified']}[/]")


# ──────────────────────────────────────────────────────────────────────────────
# GENERATE-EMAILS
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("generate-emails")
@click.option("--lang", default="", help="Filtriraj po jeziku (sl/de/hr/it/...)")
@click.option("--lead", default="", help="Generiraj samo za specifičen lead ID")
def cmd_generate_emails(lang, lead):
    """Generiraj personalizirane emaile za kvalificirane leade."""
    from src.email_generator import generate_all_emails, generate_email
    from src.database import get_lead, save_email_draft

    if lead:
        lead_data = get_lead(lead)
        if not lead_data:
            console.print(f"[red]Lead {lead} ne obstaja[/]")
            return
        result = generate_email(lead_data)
        if result:
            save_email_draft(lead, result["template_type"], result["subject"], result["body"])
            console.print(f"[green]Email generiran za {lead}[/]")
            console.print(f"  Zadeva: {result['subject']}")
        return

    console.print("[cyan]Generacija emailov...[/]")
    stats = generate_all_emails(lang_filter=lang or None)
    console.print(f"Generirano: [green]{stats['generated']}[/]  |  Napak: [red]{stats['errors']}[/]")


# ──────────────────────────────────────────────────────────────────────────────
# REVIEW
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("review")
@click.option("--limit", default=20, show_default=True)
@click.option("--priority", default="VISOKA", show_default=True)
def cmd_review(limit, priority):
    """Interaktivni pregled leadov pred pošiljanjem."""
    from src.reporter import print_lead_list
    from src.database import get_pending_emails

    console.rule("[bold]Pregled pred pošiljanjem[/]")
    print_lead_list(priority=priority, limit=limit)

    pending = get_pending_emails(limit=5)
    if pending:
        console.print(f"\n[cyan]Prvih 5 emailov v vrsti:[/]")
        for e in pending:
            console.print(f"  [{e['priority']}] {e['company_name']} → {e['recipient_email']}")
            console.print(f"    Zadeva: {e['subject']}")


# ──────────────────────────────────────────────────────────────────────────────
# SEND
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("send")
@click.option("--daily-limit", default=3000, show_default=True)
@click.option("--dry-run", is_flag=True)
@click.option("--smtp-account", default="", help="Uporabi specifičen SMTP račun (email)")
@click.option("--workers", default=3, show_default=True, help="Št. vzporednih pošiljateljev")
def cmd_send(daily_limit, dry_run, smtp_account, workers):
    """Pošlji emaile z rotacijo SMTP računov."""
    from src.email_sender import send_batch_threaded, send_batch, _is_send_window

    if not dry_run and not _is_send_window():
        console.print("[yellow]⚠️  Zunaj časa pošiljanja (pon–pet, 8:00–17:00)[/]")
        console.print("     Uporabi --dry-run za testiranje ali počakaj na delovni čas.")
        return

    console.print(f"[cyan]Pošiljanje do {daily_limit} emailov "
                  f"({'DRY-RUN' if dry_run else 'PRODUKCIJA'})...[/]")

    if smtp_account:
        stats = send_batch(daily_limit=daily_limit, dry_run=dry_run,
                           smtp_account_user=smtp_account)
    else:
        stats = send_batch_threaded(daily_limit=daily_limit, dry_run=dry_run, workers=workers)

    console.print(f"Poslano: [green]{stats['sent']}[/]  |  "
                  f"Preskočeno: [yellow]{stats['skipped']}[/]  |  "
                  f"Napak: [red]{stats['failed']}[/]")


# ──────────────────────────────────────────────────────────────────────────────
# FOLLOWUP
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("followup")
@click.option("--days", default=5, show_default=True, help="Dni brez odgovora")
def cmd_followup(days):
    """Generiraj follow-up emaile (Template C) za neodgovorjene leade."""
    from src.tracker import generate_followups, check_replies

    console.print("[cyan]Preverjam odgovore (IMAP)...[/]")
    reply_stats = check_replies()
    console.print(f"  Odgovori: {reply_stats['replied']} | Odjave: {reply_stats['unsubscribed']}")

    console.print(f"[cyan]Generacija follow-up emailov (>{days} dni brez odgovora)...[/]")
    stats = generate_followups(followup_days=days)
    console.print(f"Generirano: [green]{stats['generated']}[/]  |  "
                  f"Preskočeno: [dim]{stats['skipped']}[/]")


# ──────────────────────────────────────────────────────────────────────────────
# STATUS / UPDATE
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("status")
@click.option("--status-filter", default="", help="Filtriraj po statusu")
@click.option("--priority", default="", help="Filtriraj po prioriteti")
@click.option("--limit", default=50, show_default=True)
def cmd_status(status_filter, priority, limit):
    """Pregled statusov leadov."""
    from src.reporter import print_lead_list
    print_lead_list(
        status=status_filter or None,
        priority=priority or None,
        limit=limit,
    )


@cli.command("update")
@click.option("--lead", required=True, help="Lead ID (npr. LEAD-001)")
@click.option("--status", required=True,
              type=click.Choice(["ČAKA", "POSLANO", "ODPRT", "ODGOVORIL", "ZAVRNIL", "KONVERTIRAN"],
                                case_sensitive=False))
def cmd_update(lead, status):
    """Ročno posodobi status leada."""
    from src.tracker import update_status_manual
    if update_status_manual(lead, status.upper()):
        console.print(f"[green]{lead} → {status.upper()}[/]")
    else:
        console.print(f"[red]Napaka pri posodobitvi {lead}[/]")


# ──────────────────────────────────────────────────────────────────────────────
# REPORT
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("report")
@click.option("--country", default="", help="Filtriraj po državi")
@click.option("--export", "do_export", is_flag=True, help="Izvozi v CSV")
def cmd_report(country, do_export):
    """Prikaži KPI poročilo."""
    from src.reporter import print_report, export_csv
    print_report(country=country or None)
    if do_export:
        export_csv(country=country or None)


# ──────────────────────────────────────────────────────────────────────────────
# SCHEDULER
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("scheduler")
@click.option("--start", "action", flag_value="start")
@click.option("--stop", "action", flag_value="stop")
@click.option("--status-check", "action", flag_value="status")
@click.option("--daily-limit", default=3000, show_default=True)
@click.option("--dry-run", is_flag=True)
def cmd_scheduler(action, daily_limit, dry_run):
    """Upravljaj avtomatski dnevni scheduler."""
    from src.scheduler import start_scheduler, stop_scheduler, scheduler_status
    from src.config import DAILY_RUN_TIME

    if action == "start":
        start_scheduler(daily_limit=daily_limit, dry_run=dry_run)
        console.print(f"[green]Scheduler zagnan. Dnevni zagon ob {DAILY_RUN_TIME} (pon–pet)[/]")
        console.print("[dim]Ctrl+C za izhod[/]")
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            stop_scheduler()
    elif action == "stop":
        stop_scheduler()
        console.print("[yellow]Scheduler ustavljen[/]")
    elif action == "status":
        s = scheduler_status()
        for k, v in s.items():
            console.print(f"  {k}: {v}")
    else:
        console.print("Uporabi --start / --stop / --status-check")


# ──────────────────────────────────────────────────────────────────────────────
# GDPR
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("cleanup")
@click.option("--months", default=12, show_default=True, help="Starost podatkov v mesecih")
@click.confirmation_option(prompt="Brisanje starih leadov. Nadaljuješ?")
def cmd_cleanup(months):
    """GDPR čiščenje — zbriši zapise starejše od N mesecev."""
    from src.database import gdpr_cleanup
    deleted = gdpr_cleanup(months=months)
    console.print(f"[green]Izbrisano {deleted} leadov (starejši od {months} mesecev)[/]")


@cli.command("unsubscribe")
@click.option("--email", required=True, help="Email naslov za odjavo")
def cmd_unsubscribe(email):
    """Ročno dodaj email na listo odjavljenih."""
    from src.database import add_unsubscribe
    add_unsubscribe(email)
    console.print(f"[green]{email} dodan na listo odjavljenih[/]")


# ──────────────────────────────────────────────────────────────────────────────
# PREVIEW
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("preview")
@click.option("--lead", required=True, help="Lead ID (npr. LEAD-001)")
@click.option("--send-email", is_flag=True, help="Pošlji preview email leadu")
def cmd_preview(lead, send_email):
    """Generiraj preview spletne strani za lead."""
    from src.preview_generator import generate_preview, send_preview_email
    url = generate_preview(lead)
    if url:
        console.print(f"[green]Preview: {url}[/]")
        if send_email:
            send_preview_email(lead, url)
            console.print(f"[cyan]Preview email generiran za {lead}[/]")
    else:
        console.print(f"[red]Napaka pri generiranju preview za {lead}[/]")


# ──────────────────────────────────────────────────────────────────────────────
# EXPORT
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("export")
@click.option("--format", "fmt", default="csv", type=click.Choice(["csv"]), show_default=True)
@click.option("--country", default="", help="Filtriraj po državi")
def cmd_export(fmt, country):
    """Izvozi leade v datoteko."""
    from src.reporter import export_csv
    if fmt == "csv":
        export_csv(country=country or None)


# ══════════════════════════════════════════════════════════════════════════════
# VSTOPNA TOČKA
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    cli()
