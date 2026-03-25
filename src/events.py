"""Deljeni event bus za real-time komunikacijo med scheduler in API."""
import threading
from collections import deque
from datetime import datetime

_lock = threading.Lock()

# Circular buffer zadnjih 150 dogodkov
_activity_log: deque = deque(maxlen=150)

# Trenutno stanje pipeline-a
_pipeline_state: dict = {
    "status": "idle",       # idle | running | done | error
    "stage": "",
    "stage_label": "",
    "scraped": 0,
    "qualified": 0,
    "emails_generated": 0,
    "emails_sent": 0,
    "errors": 0,
    "message": "",
    "started_at": None,
    "updated_at": None,
    "progress_pct": 0,
}


def add_event(message: str, event_type: str = "info") -> None:
    """Dodaj dogodek v activity log (thread-safe)."""
    with _lock:
        _activity_log.appendleft({
            "time": datetime.now().strftime("%H:%M:%S"),
            "ts": datetime.now().isoformat(),
            "message": message,
            "type": event_type,   # info | success | warning | error
        })


def update_pipeline(updates: dict) -> None:
    """Posodobi stanje pipeline-a (thread-safe)."""
    with _lock:
        _pipeline_state.update(updates)
        _pipeline_state["updated_at"] = datetime.now().isoformat()


def get_state() -> dict:
    with _lock:
        return dict(_pipeline_state)


def get_activity(limit: int = 50) -> list:
    with _lock:
        return list(_activity_log)[:limit]


def reset_pipeline() -> None:
    with _lock:
        _pipeline_state.update({
            "status": "idle", "stage": "", "stage_label": "",
            "scraped": 0, "qualified": 0, "emails_generated": 0,
            "emails_sent": 0, "errors": 0, "message": "",
            "started_at": None, "progress_pct": 0,
        })
