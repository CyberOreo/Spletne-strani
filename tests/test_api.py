"""pytest testi za FastAPI REST API."""
import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Uporabi začasno bazo za teste
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.environ.setdefault("DATABASE_PATH", _db_path)

from api import app
from src.database import init_db, insert_lead, get_conn


@pytest_asyncio.fixture
async def client():
    init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def client_with_leads(client):
    """Client z vzorčnimi leadi v bazi."""
    leads = [
        {
            "company_name": "Vodovodar Novak d.o.o.",
            "email": "novak@example.com",
            "phone": "040111222",
            "city": "Ljubljana",
            "activity": "vodovodarska dela",
            "skd_code": "43",
            "website_status": "none",
            "facebook_url": "https://facebook.com/novak",
            "data_source": "bizi",
            "country": "si",
        },
        {
            "company_name": "Elektrikar Kovač s.p.",
            "email": "kovac@example.com",
            "phone": "031555666",
            "city": "Maribor",
            "activity": "elektroinštalacije",
            "skd_code": "43",
            "website_status": "outdated",
            "website_year": 2015,
            "data_source": "bizi",
            "country": "si",
        },
        {
            "company_name": "Frizer Zupan s.p.",
            "email": "zupan@example.com",
            "city": "Celje",
            "activity": "frizerski salon",
            "skd_code": "96",
            "website_status": "none",
            "data_source": "bizi",
            "country": "si",
            "status": "POSLANO",
        },
    ]
    for l in leads:
        insert_lead(l)
    yield client


# ── /api/stats ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_stats_returns_200(client):
    res = await client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()
    assert "total_leads" in data
    assert "emails_sent" in data
    assert "open_rate" in data
    assert "reply_rate" in data
    assert "conversion_rate" in data

@pytest.mark.asyncio
async def test_get_stats_contains_by_status(client):
    res = await client.get("/api/stats")
    assert res.status_code == 200
    assert "by_status" in res.json()


# ── /api/leads ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_leads_returns_list(client_with_leads):
    res = await client_with_leads.get("/api/leads")
    assert res.status_code == 200
    data = res.json()
    assert "leads" in data
    assert isinstance(data["leads"], list)
    assert "total" in data

@pytest.mark.asyncio
async def test_get_leads_has_results(client_with_leads):
    res = await client_with_leads.get("/api/leads")
    data = res.json()
    assert data["total"] >= 3

@pytest.mark.asyncio
async def test_get_leads_filter_by_status(client_with_leads):
    res = await client_with_leads.get("/api/leads?status=POSLANO")
    assert res.status_code == 200
    data = res.json()
    for lead in data["leads"]:
        assert lead["status"] == "POSLANO"

@pytest.mark.asyncio
async def test_get_leads_pagination(client_with_leads):
    res = await client_with_leads.get("/api/leads?limit=1&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert len(data["leads"]) <= 1

@pytest.mark.asyncio
async def test_get_leads_limit_respected(client_with_leads):
    res = await client_with_leads.get("/api/leads?limit=2")
    assert res.status_code == 200
    data = res.json()
    assert len(data["leads"]) <= 2


# ── /api/leads/{lead_id} ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_lead_detail_exists(client_with_leads):
    # Pridobi prvi lead in ga pokliči direktno
    leads_res = await client_with_leads.get("/api/leads")
    lead_id = leads_res.json()["leads"][0]["lead_id"]
    res = await client_with_leads.get(f"/api/leads/{lead_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["lead_id"] == lead_id
    assert "company_name" in data

@pytest.mark.asyncio
async def test_get_lead_detail_not_found_404(client):
    res = await client.get("/api/leads/LEAD-NEOBSTAJA")
    assert res.status_code == 404


# ── PATCH /api/leads/{lead_id} ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_lead_status_valid(client_with_leads):
    leads_res = await client_with_leads.get("/api/leads")
    lead_id = leads_res.json()["leads"][0]["lead_id"]
    res = await client_with_leads.patch(f"/api/leads/{lead_id}", json={"status": "ODGOVORIL"})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    # Preveri v DB
    detail = await client_with_leads.get(f"/api/leads/{lead_id}")
    assert detail.json()["status"] == "ODGOVORIL"

@pytest.mark.asyncio
async def test_update_lead_status_invalid_400(client_with_leads):
    leads_res = await client_with_leads.get("/api/leads")
    lead_id = leads_res.json()["leads"][0]["lead_id"]
    res = await client_with_leads.patch(f"/api/leads/{lead_id}", json={"status": "NEVELJAVEN_STATUS"})
    assert res.status_code == 400

@pytest.mark.asyncio
async def test_update_lead_not_found_404(client):
    res = await client.patch("/api/leads/LEAD-NEOBSTAJA", json={"status": "ODGOVORIL"})
    assert res.status_code == 404

@pytest.mark.asyncio
async def test_update_lead_notes(client_with_leads):
    leads_res = await client_with_leads.get("/api/leads")
    lead_id = leads_res.json()["leads"][0]["lead_id"]
    res = await client_with_leads.patch(f"/api/leads/{lead_id}", json={"notes": "Test opomba"})
    assert res.status_code == 200


# ── /api/emails ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_pending_emails(client_with_leads):
    res = await client_with_leads.get("/api/emails/pending")
    assert res.status_code == 200
    data = res.json()
    assert "emails" in data
    assert isinstance(data["emails"], list)

@pytest.mark.asyncio
async def test_get_lead_emails(client_with_leads):
    leads_res = await client_with_leads.get("/api/leads")
    lead_id = leads_res.json()["leads"][0]["lead_id"]
    res = await client_with_leads.get(f"/api/emails/{lead_id}")
    assert res.status_code == 200
    assert "emails" in res.json()


# ── /api/qualify ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_qualify_endpoint(client_with_leads):
    res = await client_with_leads.post("/api/qualify")
    assert res.status_code == 200
    data = res.json()
    # Vrne dict s statistikami
    assert "qualified" in data or "disqualified" in data or "processed" in data


# ── /api/generate-emails ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_emails_endpoint(client_with_leads):
    # Najprej kvalificiraj
    await client_with_leads.post("/api/qualify")
    res = await client_with_leads.post("/api/generate-emails")
    assert res.status_code == 200
    data = res.json()
    assert "generated" in data or "skipped" in data or isinstance(data, dict)


# ── /api/send (dry run) ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_dry_run(client_with_leads):
    res = await client_with_leads.post("/api/send", json={"daily_limit": 10, "dry_run": True})
    assert res.status_code == 200
    assert res.json()["ok"] is True


# ── /api/followup ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_followup_endpoint(client_with_leads):
    res = await client_with_leads.post("/api/followup", json={"days": 5})
    assert res.status_code == 200
    data = res.json()
    assert "generated" in data or isinstance(data, dict)


# ── /api/cleanup ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cleanup_endpoint(client):
    res = await client.delete("/api/cleanup?months=12")
    assert res.status_code == 200
    assert "deleted" in res.json()


# ── /api/unsubscribe ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unsubscribe_endpoint(client):
    res = await client.post("/api/unsubscribe", json={"email": "odjava@test.com"})
    assert res.status_code == 200
    assert res.json()["ok"] is True

@pytest.mark.asyncio
async def test_unsubscribe_idempotent(client):
    """Dvojna odjava ne sme vrniti napake."""
    await client.post("/api/unsubscribe", json={"email": "dvojna@test.com"})
    res = await client.post("/api/unsubscribe", json={"email": "dvojna@test.com"})
    assert res.status_code == 200


# ── PWA root ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_root_returns_html_or_json(client):
    res = await client.get("/")
    assert res.status_code == 200

@pytest.mark.asyncio
async def test_manifest_endpoint(client):
    res = await client.get("/manifest.json")
    assert res.status_code == 200

@pytest.mark.asyncio
async def test_docs_available(client):
    res = await client.get("/docs")
    assert res.status_code == 200


# ── /api/run/status ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_status_endpoint(client):
    res = await client.get("/api/run/status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert data["status"] in ("idle", "running", "done", "error")
