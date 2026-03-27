"""FastAPI REST API + PWA strežnik za B2B Lead Generation System."""
import asyncio
import logging
import struct
import zlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.database import (
    init_db, get_stats, get_leads, get_lead,
    update_lead_status, gdpr_cleanup, get_pending_emails, get_conn,
)
from src.config import DAILY_EMAIL_LIMIT
from src import events as _events

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).parent / "web"

# ── WebSocket broadcast ────────────────────────────────────────────────────────

_ws_clients: list[WebSocket] = []

async def _broadcast(msg: dict) -> None:
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)

# ── Pipeline state ─────────────────────────────────────────────────────────────

_pipeline_status: dict = {
    "status": "idle",
    "stage": "",
    "scraped": 0,
    "qualified": 0,
    "emails_generated": 0,
    "emails_sent": 0,
    "message": "",
}

# ── App lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _add_country_column()
    _ensure_icons()
    task = asyncio.create_task(_ws_heartbeat())
    yield
    task.cancel()


async def _ws_heartbeat() -> None:
    """Broadcast pipeline state every 3 seconds so dashboard stays live."""
    while True:
        await asyncio.sleep(3)
        if _ws_clients:
            state = _events.get_state()
            activity = _events.get_activity(20)
            await _broadcast({"type": "heartbeat", "pipeline": state, "activity": activity})

def _add_country_column() -> None:
    """Doda country stolpec, če še ne obstaja."""
    with get_conn() as conn:
        try:
            conn.execute("ALTER TABLE leads ADD COLUMN country TEXT")
        except Exception:
            pass  # Stolpec že obstaja

app = FastAPI(title="B2B Lead Gen EU", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Statične datoteke PWA
if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

# ── PWA root ───────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "B2B Lead Gen EU API", "docs": "/docs"}

@app.get("/manifest.json", include_in_schema=False)
async def pwa_manifest():
    return FileResponse(WEB_DIR / "manifest.json", media_type="application/manifest+json")

@app.get("/service-worker.js", include_in_schema=False)
async def pwa_sw():
    return FileResponse(WEB_DIR / "service-worker.js", media_type="application/javascript")

# ── Pydantic sheme ─────────────────────────────────────────────────────────────

class LeadUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None

class ScrapeRequest(BaseModel):
    country: str = "all"   # "all" = vse EU države (DAILY_BULK_CONFIG)
    industry: str = ""
    limit: int = 3000

class SendRequest(BaseModel):
    daily_limit: int = DAILY_EMAIL_LIMIT
    dry_run: bool = False

class UnsubscribeRequest(BaseModel):
    email: str

class FollowupRequest(BaseModel):
    days: int = 5

# ── API endpoints ──────────────────────────────────────────────────────────────

VALID_STATUSES = {"ČAKA", "POSLANO", "ODPRT", "ODGOVORIL", "ZAVRNIL", "KONVERTIRAN"}

@app.get("/api/stats", summary="KPI statistike")
async def api_get_stats():
    return get_stats()


@app.get("/api/leads", summary="Lista leadov")
async def api_get_leads(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    leads = get_leads(status=status, priority=priority, limit=None)
    if country:
        leads = [l for l in leads if l.get("country") == country]
    total = len(leads)
    page_leads = leads[offset: offset + limit]
    return {"leads": page_leads, "total": total, "page": offset // limit + 1}


@app.get("/api/leads/{lead_id}", summary="Detajl leada")
async def api_get_lead(lead_id: str):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead ne obstaja")
    return lead


@app.patch("/api/leads/{lead_id}", summary="Posodobi status leada")
async def api_update_lead(lead_id: str, body: LeadUpdate):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead ne obstaja")
    if body.status and body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Neveljaven status: {body.status}")
    if body.status:
        update_lead_status(lead_id, body.status)
    if body.notes is not None:
        with get_conn() as conn:
            conn.execute("UPDATE leads SET notes = ? WHERE lead_id = ?", (body.notes, lead_id))
    return {"ok": True}


@app.get("/api/emails/pending", summary="Emaili za pošiljanje (APPROVED)")
async def api_get_pending_emails(limit: int = Query(50, le=500)):
    emails = get_pending_emails(limit=limit)
    return {"emails": emails, "total": len(emails)}


@app.get("/api/emails/drafts", summary="Emaili za pregled (DRAFT)")
async def api_get_draft_emails(limit: int = Query(500, le=2000)):
    from src.database import get_draft_emails
    drafts = get_draft_emails(limit=limit)
    return {"emails": drafts, "total": len(drafts)}


@app.post("/api/emails/approve-all", summary="Odobri vse DRAFT emaile")
async def api_approve_all_emails():
    from src.database import get_conn
    with get_conn() as conn:
        result = conn.execute(
            "UPDATE emails SET status='APPROVED' WHERE status='DRAFT'"
        )
        approved = result.rowcount
    return {"ok": True, "approved": approved}


@app.post("/api/emails/{email_id}/approve", summary="Odobri email")
async def api_approve_email(email_id: int):
    from src.database import approve_email
    approve_email(email_id)
    return {"ok": True}


@app.post("/api/emails/{email_id}/reject", summary="Zavrni email")
async def api_reject_email(email_id: int):
    from src.database import reject_email
    reject_email(email_id)
    return {"ok": True}


@app.get("/api/emails/{lead_id}", summary="Emaili za lead")
async def api_get_lead_emails(lead_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM emails WHERE lead_id = ? ORDER BY id DESC",
            (lead_id,),
        ).fetchall()
    return {"emails": [dict(r) for r in rows]}


@app.post("/api/run/daily", summary="Zaženi celoten pipeline")
async def api_run_daily(background_tasks: BackgroundTasks, dry_run: bool = False):
    global _pipeline_status
    if _pipeline_status["status"] == "running":
        return _pipeline_status
    _pipeline_status = {
        "status": "running", "stage": "start",
        "scraped": 0, "qualified": 0,
        "emails_generated": 0, "emails_sent": 0,
        "message": "Pipeline zagnan",
    }
    background_tasks.add_task(_run_pipeline_bg, dry_run)
    return _pipeline_status


@app.get("/api/run/status", summary="Status pipeline-a")
async def api_pipeline_status():
    """Vrne kombiniran status: events bus + legacy _pipeline_status."""
    ev = _events.get_state()
    # Merge: events bus has richer data; fall back to local dict if idle
    if ev.get("status") not in (None, "idle") or _pipeline_status["status"] == "idle":
        return ev
    return _pipeline_status


@app.get("/api/activity", summary="Real-time activity log")
async def api_activity(limit: int = Query(50, le=150)):
    return {"activity": _events.get_activity(limit), "pipeline": _events.get_state()}


@app.post("/api/scrape", summary="Sproži scraping")
async def api_scrape(body: ScrapeRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(_scrape_bg, body.country, body.industry, body.limit)
    return {"ok": True, "message": f"Scraping zagnan: {body.country}/{body.industry}"}


@app.post("/api/qualify", summary="Kvalifikacija leadov")
async def api_qualify():
    from src.qualifier import qualify_all
    return qualify_all(min_score=3)


@app.post("/api/generate-emails", summary="Generacija email draftov")
async def api_generate_emails():
    from src.email_generator import generate_all_emails
    return generate_all_emails()


@app.post("/api/send", summary="Pošlji emaile")
async def api_send(body: SendRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(_send_bg, body.daily_limit, body.dry_run)
    return {"ok": True, "message": f"Pošiljanje (limit={body.daily_limit}, dry_run={body.dry_run})"}


@app.post("/api/followup", summary="Generiraj follow-up emaile")
async def api_followup(body: FollowupRequest):
    from src.tracker import generate_followups
    return generate_followups(followup_days=body.days)


@app.post("/api/preview/{lead_id}", summary="Generiraj preview stran")
async def api_preview(lead_id: str):
    from src.preview_generator import generate_preview, send_preview_email
    url = generate_preview(lead_id)
    if not url:
        raise HTTPException(status_code=404, detail="Lead ne obstaja ali napaka pri generaciji")
    send_preview_email(lead_id, url)
    return {"url": url}


@app.post("/api/unsubscribe", summary="Dodaj na unsubscribe listo")
async def api_unsubscribe(body: UnsubscribeRequest):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO unsubscribes (email, unsubscribed_at) VALUES (?, datetime('now'))",
            (body.email.lower().strip(),),
        )
    return {"ok": True}


@app.get("/unsubscribe", summary="One-click odjava (za email List-Unsubscribe header)", include_in_schema=False)
async def one_click_unsubscribe(email: str = Query(...)):
    """GET endpoint za one-click unsubscribe iz email klientov (Gmail, Outlook)."""
    clean = email.lower().strip()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO unsubscribes (email, unsubscribed_at) VALUES (?, datetime('now'))",
            (clean,),
        )
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="sl"><head><meta charset="UTF-8">
<title>Odjava uspešna</title>
<style>body{{font-family:Arial,sans-serif;text-align:center;padding:60px;background:#f5f5f5}}
.box{{background:white;border-radius:12px;padding:40px;max-width:400px;margin:0 auto;box-shadow:0 2px 12px rgba(0,0,0,.08)}}
h2{{color:#22c55e}}p{{color:#666}}</style></head>
<body><div class="box">
<h2>✓ Odjava uspešna</h2>
<p>Naslov <strong>{clean}</strong> je bil odjavljen.<br>Ne boste več prejemali naših sporočil.</p>
</div></body></html>""")


@app.post("/unsubscribe", summary="One-click POST odjava (RFC 8058)", include_in_schema=False)
async def one_click_unsubscribe_post(email: str = Query(...)):
    """POST endpoint za RFC 8058 List-Unsubscribe-Post one-click."""
    clean = email.lower().strip()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO unsubscribes (email, unsubscribed_at) VALUES (?, datetime('now'))",
            (clean,),
        )
    return {"ok": True}


@app.get("/api/settings", summary="Preberi SMTP nastavitve")
async def api_get_settings():
    """Vrne trenutne SMTP nastavitve (geslo je maskirano)."""
    import os
    pw = os.environ.get("SMTP_PASSWORD", "")
    return {
        "smtp_host":     os.environ.get("SMTP_HOST", ""),
        "smtp_port":     os.environ.get("SMTP_PORT", "587"),
        "smtp_user":     os.environ.get("SMTP_USER", ""),
        "smtp_password": "••••••••" if pw else "",
        "sender_name":   os.environ.get("SENDER_NAME", ""),
        "reply_to":      os.environ.get("REPLY_TO", ""),
        "daily_limit":   os.environ.get("DAILY_EMAIL_LIMIT", "3000"),
        "send_window_start": os.environ.get("SEND_WINDOW_START", "07:00"),
        "send_window_end":   os.environ.get("SEND_WINDOW_END", "18:00"),
        "overnight_scrape_time": os.environ.get("OVERNIGHT_SCRAPE_TIME", "22:00"),
        "overnight_send_time":   os.environ.get("OVERNIGHT_SEND_TIME", "08:00"),
        "serpapi_key":   "••••••••" if os.environ.get("SERPAPI_KEY", "") else "",
    }


class SettingsUpdate(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None   # prazno = ne menjaj
    sender_name: Optional[str] = None
    reply_to: Optional[str] = None
    daily_limit: Optional[str] = None
    send_window_start: Optional[str] = None
    send_window_end: Optional[str] = None
    overnight_scrape_time: Optional[str] = None
    overnight_send_time: Optional[str] = None
    serpapi_key: Optional[str] = None


@app.post("/api/settings", summary="Shrani SMTP nastavitve v .env")
async def api_save_settings(body: SettingsUpdate):
    """Zapiše nastavitve v .env in takoj posodobi os.environ (brez restarta)."""
    import os
    env_path = Path(__file__).parent / ".env"

    # Mapping: pydantic field -> env key
    FIELD_MAP = {
        "smtp_host":             "SMTP_HOST",
        "smtp_port":             "SMTP_PORT",
        "smtp_user":             "SMTP_USER",
        "smtp_password":         "SMTP_PASSWORD",
        "sender_name":           "SENDER_NAME",
        "reply_to":              "REPLY_TO",
        "daily_limit":           "DAILY_EMAIL_LIMIT",
        "send_window_start":     "SEND_WINDOW_START",
        "send_window_end":       "SEND_WINDOW_END",
        "overnight_scrape_time": "OVERNIGHT_SCRAPE_TIME",
        "overnight_send_time":   "OVERNIGHT_SEND_TIME",
        "serpapi_key":           "SERPAPI_KEY",
    }

    updates: dict[str, str] = {}
    for field, env_key in FIELD_MAP.items():
        val = getattr(body, field, None)
        if val is None:
            continue
        # Maskirano geslo — preskoči
        if set(val) <= {"•"} and len(val) > 0:
            continue
        updates[env_key] = val

    if not updates:
        return {"ok": True, "updated": []}

    # Preberi obstoječ .env
    existing: dict[str, str] = {}
    lines: list[str] = []
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, v = stripped.partition("=")
                existing[k.strip()] = v.strip()
            lines.append(line)

    # Posodobi vrednosti v vrsticah
    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.partition("=")[0].strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                updated_keys.add(k)
                continue
        new_lines.append(line)

    # Dodaj nove ključe, ki jih še ni bilo
    for k, v in updates.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Takoj posodobi os.environ (brez restarta)
    for k, v in updates.items():
        os.environ[k] = v

    return {"ok": True, "updated": list(updates.keys())}


@app.post("/api/settings/test-smtp", summary="Testiraj SMTP povezavo")
async def api_test_smtp():
    """Pošlje testni email na SMTP_USER naslov."""
    import os, smtplib, ssl
    from email.mime.text import MIMEText
    host = os.environ.get("SMTP_HOST", "")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER", "")
    pw   = os.environ.get("SMTP_PASSWORD", "")
    if not host or not user or not pw:
        raise HTTPException(400, "SMTP ni nastavljen — najprej shrani nastavitve.")
    try:
        msg = MIMEText("LeadGen EU SMTP test — vse deluje ✓")
        msg["Subject"] = "LeadGen EU — SMTP test"
        msg["From"] = user
        msg["To"] = user
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.login(user, pw)
            s.sendmail(user, user, msg.as_string())
        return {"ok": True, "message": f"Testni email poslan na {user}"}
    except Exception as exc:
        raise HTTPException(400, f"SMTP napaka: {exc}")


@app.delete("/api/cleanup", summary="GDPR brisanje starih zapisov")
async def api_cleanup(months: int = Query(12)):
    deleted = gdpr_cleanup(months=months)
    return {"deleted": deleted}


@app.get("/api/server-info", summary="Lokalni IP in dostopni naslovi")
async def api_server_info():
    """Vrne lokalni IP naslov za dostop iz telefona na istem WiFi omrežju."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    return {
        "local_ip": local_ip,
        "local_url": f"http://{local_ip}:8000",
        "localhost_url": "http://localhost:8000",
    }


@app.post("/api/update", summary="Git pull + restart strežnika")
async def api_update(background_tasks: BackgroundTasks):
    """Potegne najnovejše spremembe z GitHuba in restarta strežnik."""
    import subprocess, threading, os
    cwd = str(Path(__file__).parent)
    result = subprocess.run(
        ["git", "pull"],
        capture_output=True, text=True, cwd=cwd, timeout=60,
    )
    output = (result.stdout + result.stderr).strip()
    already_latest = "Already up to date" in output or "že posodobljeno" in output.lower()

    if result.returncode != 0:
        raise HTTPException(500, f"Git pull napaka: {output}")

    def _restart():
        import time; time.sleep(1)
        os._exit(0)  # watchdog v start.bat bo samodejno zagnal nov proces

    threading.Thread(target=_restart, daemon=True).start()
    return {
        "ok": True,
        "output": output,
        "already_latest": already_latest,
        "message": "Posodobljeno — strežnik se zaganja (" + ("ni sprememb" if already_latest else "nova verzija") + ")",
    }


@app.get("/api/export/csv", summary="Izvozi leade v CSV", include_in_schema=True)
async def api_export_csv():
    from src.reporter import export_csv
    path = export_csv()
    return FileResponse(str(path), media_type="text/csv", filename=path.name)

# ── WebSocket ──────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)

# ── Background tasks ───────────────────────────────────────────────────────────

async def _run_pipeline_bg(dry_run: bool) -> None:
    global _pipeline_status
    _events.reset_pipeline()
    _events.update_pipeline({"status": "running", "stage": "start", "stage_label": "Zaganjam...", "started_at": __import__('datetime').datetime.now().isoformat()})
    _events.add_event("Pipeline zagnan" + (" (dry run)" if dry_run else ""), "info")
    try:
        from src.scheduler import run_daily_pipeline
        stats = await run_daily_pipeline(dry_run=dry_run)
        _pipeline_status.update({
            "status": "done", "stage": "complete",
            "scraped": stats.get("scraped", 0),
            "qualified": stats.get("qualified", 0),
            "emails_generated": stats.get("emails_generated", 0),
            "emails_sent": stats.get("emails_sent", 0),
            "message": "Pipeline uspešno zaključen",
        })
    except Exception as exc:
        _pipeline_status.update({"status": "error", "message": str(exc)})
        _events.update_pipeline({"status": "error", "message": str(exc)})
        _events.add_event(f"Pipeline napaka: {exc}", "error")
    state = _events.get_state()
    await _broadcast({"type": "pipeline_done", "pipeline": state})


async def _scrape_bg(country: str, industry: str, limit: int) -> None:
    from src.scheduler import _scrape_bulk
    from src.config import DAILY_BULK_CONFIG

    # "all" = scraping vseh EU držav po DAILY_BULK_CONFIG
    if country == "all":
        configs = DAILY_BULK_CONFIG
    else:
        configs = [{"source": "overpass", "country": country, "industry": industry, "limit": limit}]

    _events.update_pipeline({"status": "running", "stage": "scraping", "stage_label": "Scraping leadov",
                              "scraped": 0, "started_at": __import__('datetime').datetime.now().isoformat()})
    inserted = await _scrape_bulk(configs)
    _events.update_pipeline({"status": "done", "scraped": inserted})
    _events.add_event(f"Scraping končan: {inserted} novih leadov", "success")
    await _broadcast({"type": "scrape_done", "inserted": inserted})


async def _send_bg(daily_limit: int, dry_run: bool) -> None:
    import importlib
    from src.email_sender import send_batch_threaded
    smtp_accounts = importlib.import_module("src.config").SMTP_ACCOUNTS
    workers = min(len(smtp_accounts), 5) or 1
    stats = send_batch_threaded(daily_limit=daily_limit, dry_run=dry_run, workers=workers)
    await _broadcast({"type": "send_done", **stats})

# ── PNG icon generator (brez zunanjih odvisnosti) ─────────────────────────────

def _ensure_icons() -> None:
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        icon = WEB_DIR / f"icon-{size}.png"
        if not icon.exists():
            icon.write_bytes(_make_png(size, (44, 95, 138)))


def _make_png(size: int, color: tuple) -> bytes:
    r, g, b = color

    def chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    rows = []
    for y in range(size):
        row = bytearray(b'\x00')  # filter byte
        for x in range(size):
            # Rounded corners mask
            m = size // 5
            corner = False
            for cx, cy in [(m, m), (size - m, m), (m, size - m), (size - m, size - m)]:
                dx, dy = x - cx, y - cy
                if (abs(x - cx) < m and abs(y - cy) < m) and (dx * dx + dy * dy > m * m):
                    corner = True
                    break
            row += bytes([26, 26, 46] if corner else [r, g, b])
        rows.append(bytes(row))

    raw = b''.join(rows)
    ihdr = chunk(b'IHDR', struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    idat = chunk(b'IDAT', zlib.compress(raw, 6))
    iend = chunk(b'IEND', b'')
    return b'\x89PNG\r\n\x1a\n' + ihdr + idat + iend


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
