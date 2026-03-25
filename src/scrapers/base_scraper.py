"""Async osnovni razred za vse scraperje (aiohttp)."""
import asyncio
import itertools
import logging
import random
import re
from abc import ABC, abstractmethod
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp

from src.config import (
    SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX, USER_AGENT, PROXY_LIST
)

logger = logging.getLogger(__name__)

# Rotacija proxy-jev
_proxy_cycle = itertools.cycle(PROXY_LIST) if PROXY_LIST else None

# User-Agent lista za rotacijo
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
]


def _next_proxy() -> str | None:
    if _proxy_cycle is None:
        return None
    return next(_proxy_cycle)


def _random_ua() -> str:
    return random.choice(USER_AGENTS)


class BaseScraper(ABC):
    """Skupne async metode za vse scraperje."""

    def __init__(self):
        self._robots_cache: dict[str, RobotFileParser | None] = {}
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit=20, ssl=False)
        timeout = aiohttp.ClientTimeout(total=20)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "User-Agent": _random_ua(),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    # ─── robots.txt ──────────────────────────────────────────────────────────

    def _can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots_cache:
            # Sinhrona robots.txt preveritev (enkrat na domeno)
            rp = RobotFileParser()
            rp.set_url(f"{base}/robots.txt")
            try:
                rp.read()
                self._robots_cache[base] = rp
            except Exception:
                self._robots_cache[base] = None
        rp = self._robots_cache[base]
        if rp is None:
            return True
        return rp.can_fetch(USER_AGENT, url)

    # ─── HTTP ─────────────────────────────────────────────────────────────────

    async def _get(self, url: str, **kwargs) -> str | None:
        """Async GET zahtevek. Vrne HTML ali None."""
        if not self._can_fetch(url):
            logger.warning("robots.txt prepoveduje: %s", url)
            return None

        await self._rate_limit()

        headers = {"User-Agent": _random_ua()}
        proxy = _next_proxy()

        try:
            async with self._session.get(
                url, headers=headers, proxy=proxy, **kwargs
            ) as resp:
                if resp.status >= 400:
                    logger.warning("HTTP %d pri GET %s", resp.status, url)
                    return None
                text = await resp.text(errors="replace")
                logger.debug("GET %s → %d (%d bytes)", url, resp.status, len(text))
                return text
        except asyncio.TimeoutError:
            logger.warning("Timeout pri GET %s", url)
            return None
        except Exception as exc:
            logger.warning("Napaka pri GET %s: %s", url, exc)
            return None

    async def _rate_limit(self) -> None:
        delay = random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX)
        await asyncio.sleep(delay)

    # ─── Abstrakt ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def scrape(self, **kwargs) -> list[dict]:
        """Vrni seznam surovih podatkov o podjetjih."""

    # ─── Pomoč: zaznavanje spletne strani ────────────────────────────────────

    async def detect_website_status(self, url: str | None) -> dict:
        """Vrni {'website_status': 'none'|'outdated'|'modern', 'website_year': int|None}."""
        if not url or url.strip() in ("", "-", "N/A", "http://", "https://"):
            return {"website_status": "none", "website_year": None}

        html = await self._get(url)
        if html is None:
            return {"website_status": "none", "website_year": None}

        year = self._extract_year(html)
        if year and year < 2018:
            return {"website_status": "outdated", "website_year": year}
        elif year:
            return {"website_status": "modern", "website_year": year}
        return {"website_status": "modern", "website_year": None}

    @staticmethod
    def _extract_year(html: str) -> int | None:
        patterns = [
            r"©\s*(\d{4})",
            r"[Cc]opyright\s*[©\-]?\s*(\d{4})",
            r'<meta[^>]+name=["\']?generator["\']?[^>]*content=["\'][^"\']*?(\d{4})',
        ]
        for pattern in patterns:
            m = re.search(pattern, html)
            if m:
                year = int(m.group(1))
                if 2000 <= year <= 2030:
                    return year
        return None

    @staticmethod
    def _extract_city_from_address(address: str) -> str:
        """Izvleče ime mesta iz naslova (format: Ulica 1, 1000 Mesto)."""
        if not address:
            return ""
        m = re.search(r"\d{3,5}\s+([A-ZŠŽČĆĐ][^\d,;]+)", address)
        return m.group(1).strip() if m else ""
