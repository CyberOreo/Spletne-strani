"""Vstopna tocka za LeadGen EU — zagane scheduler + API strežnik."""
import sys
import os
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Logging
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

from src.database import init_db
from src.scheduler import start_overnight_scheduler
import api as api_module
import uvicorn

init_db()
start_overnight_scheduler()

logging.getLogger("main").info("Sistem zagnan. Scraping ob 22:00, posiljanje ob 08:00.")
uvicorn.run(api_module.app, host="0.0.0.0", port=8000, log_level="warning")
