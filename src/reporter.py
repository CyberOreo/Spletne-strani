"""KPI poročila — statistike, rich tabela, CSV izvoz."""
import csv
import logging
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

from src.database import get_stats, get_leads, get_conn

logger = logging.getLogger(__name__)
console = Console()

EXPORTS_DIR = Path(__file__).resolve().parent.parent / "exports"


def print_report(country: str = None) -> dict:
    """Izpiše KPI poročilo v terminal (rich tabela)."""
    stats = get_stats()

    # ── Naslov ────────────────────────────────────────────────────────────────
    console.rule("[bold blue]B2B Lead Generation — KPI Poročilo[/]")
    console.print(f"[dim]Datum: {date.today().isoformat()}[/]")
    if country:
        console.print(f"[dim]Država: {country.upper()}[/]")
    console.print()

    # ── Povzetek ──────────────────────────────────────────────────────────────
    summary = Table(box=box.ROUNDED, show_header=False, padding=(0, 2))
    summary.add_column("Metrika", style="bold")
    summary.add_column("Vrednost", justify="right")

    summary.add_row("Skupaj leadov", str(stats["total_leads"]))
    summary.add_row("Emailov poslanih", str(stats["emails_sent"]))
    summary.add_row("Emailov odprtih", str(stats["emails_opened"]))
    summary.add_row("Odgovorov", str(stats["emails_replied"]))
    summary.add_row("Konverzij", str(stats["converted"]))

    open_rate = stats["open_rate"]
    reply_rate = stats["reply_rate"]
    conv_rate = stats["conversion_rate"]

    color_open = "green" if open_rate >= 30 else "yellow" if open_rate >= 15 else "red"
    color_reply = "green" if reply_rate >= 5 else "yellow" if reply_rate >= 2 else "red"
    color_conv = "green" if conv_rate >= 1 else "yellow" if conv_rate >= 0.5 else "red"

    summary.add_row("Open rate", f"[{color_open}]{open_rate:.1f}%[/] (cilj: >30%)")
    summary.add_row("Reply rate", f"[{color_reply}]{reply_rate:.1f}%[/] (cilj: >5%)")
    summary.add_row("Conversion rate", f"[{color_conv}]{conv_rate:.1f}%[/] (cilj: >1%)")

    console.print(summary)
    console.print()

    # ── Statusi leadov ────────────────────────────────────────────────────────
    status_table = Table(title="Statusi leadov", box=box.SIMPLE)
    status_table.add_column("Status", style="bold")
    status_table.add_column("Število", justify="right")

    status_colors = {
        "ČAKA": "white", "POSLANO": "cyan", "ODPRT": "yellow",
        "ODGOVORIL": "green", "ZAVRNIL": "red", "KONVERTIRAN": "bold green",
    }
    for status, count in sorted(stats["by_status"].items()):
        color = status_colors.get(status, "white")
        status_table.add_row(f"[{color}]{status}[/]", str(count))

    console.print(status_table)

    # ── Poročilo po prioritetah ───────────────────────────────────────────────
    with get_conn() as conn:
        prio_rows = conn.execute(
            "SELECT priority, COUNT(*) FROM leads WHERE disqualified=0 GROUP BY priority"
        ).fetchall()

    prio_table = Table(title="Leadi po prioriteti", box=box.SIMPLE)
    prio_table.add_column("Prioriteta")
    prio_table.add_column("Število", justify="right")
    prio_colors = {"VISOKA": "green", "SREDNJA": "yellow", "NIZKA": "dim"}
    for row in prio_rows:
        color = prio_colors.get(row[0], "white")
        prio_table.add_row(f"[{color}]{row[0]}[/]", str(row[1]))
    console.print(prio_table)

    return stats


def export_csv(country: str = None) -> Path:
    """Izvozi leade v CSV datoteko."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"leads_{date.today().isoformat()}"
    if country:
        filename += f"_{country}"
    filepath = EXPORTS_DIR / f"{filename}.csv"

    leads = get_leads(disqualified=0)
    if country:
        leads = [l for l in leads if l.get("country") == country]

    fieldnames = [
        "lead_id", "company_name", "contact_person", "activity", "skd_code",
        "email", "phone", "address", "city", "region", "country",
        "website_url", "website_status", "website_year",
        "facebook_url", "instagram_url", "data_source",
        "qualification_score", "priority", "recommended_template",
        "status", "notes", "created_at", "last_contact_at",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            writer.writerow(lead)

    console.print(f"[green]Izvoženo {len(leads)} leadov → {filepath}[/]")
    logger.info("CSV izvoz: %d leadov → %s", len(leads), filepath)
    return filepath


def print_lead_list(
    status: str = None,
    priority: str = None,
    limit: int = 50,
) -> None:
    """Izpiše seznam leadov v terminal."""
    leads = get_leads(status=status, priority=priority, limit=limit)

    table = Table(title=f"Leadi (status={status or 'vsi'}, prioriteta={priority or 'vse'})",
                  box=box.SIMPLE, show_lines=False)
    table.add_column("ID", style="dim", width=10)
    table.add_column("Podjetje", width=28)
    table.add_column("Email", width=28)
    table.add_column("Kraj", width=14)
    table.add_column("Score", justify="center", width=6)
    table.add_column("Prioriteta", width=10)
    table.add_column("Status", width=12)

    prio_colors = {"VISOKA": "green", "SREDNJA": "yellow", "NIZKA": "dim"}
    for l in leads:
        color = prio_colors.get(l.get("priority"), "white")
        table.add_row(
            l["lead_id"],
            l["company_name"][:28],
            (l.get("email") or "—")[:28],
            (l.get("city") or "—")[:14],
            str(l.get("qualification_score") or 0),
            f"[{color}]{l.get('priority') or '—'}[/]",
            l.get("status") or "—",
        )

    console.print(table)
