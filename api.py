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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.database import (
    init_db, get_stats, get_leads, get_lead,
    update_lead_status, gdpr_cleanup, get_pending_emails, get_conn,
)
from src.config import DAILY_EMAIL_LIMIT

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
    yield

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
    country: str = "si"
    industry: str = "vodovodarska dela"
    limit: int = 100

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


@app.get("/api/emails/pending", summary="Emaili za pošiljanje")
async def api_get_pending_emails(limit: int = Query(50, le=500)):
    emails = get_pending_emails(limit=limit)
    return {"emails": emails, "total": len(emails)}


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
    return _pipeline_status


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


@app.delete("/api/cleanup", summary="GDPR brisanje starih zapisov")
async def api_cleanup(months: int = Query(12)):
    deleted = gdpr_cleanup(months=months)
    return {"deleted": deleted}


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
    try:
        from src.scheduler import run_daily_pipeline
        _pipeline_status["stage"] = "scraping"
        await _broadcast(_pipeline_status)

        stats = await run_daily_pipeline(dry_run=dry_run)
        _pipeline_status.update({
            "status": "done",
            "stage": "complete",
            "scraped": stats.get("scraped", 0),
            "qualified": stats.get("qualified", 0),
            "emails_generated": stats.get("emails_generated", 0),
            "emails_sent": stats.get("emails_sent", 0),
            "message": "Pipeline uspešno zaključen",
        })
    except Exception as exc:
        _pipeline_status.update({"status": "error", "message": str(exc)})
    await _broadcast(_pipeline_status)


async def _scrape_bg(country: str, industry: str, limit: int) -> None:
    from src.scheduler import _scrape_bulk
    from src.database import insert_lead
    leads = await _scrape_bulk([{"country": country, "industry": industry, "limit": limit}])
    inserted = sum(1 for l in leads if insert_lead(l))
    await _broadcast({"type": "scrape_done", "inserted": inserted, "total": len(leads)})


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
