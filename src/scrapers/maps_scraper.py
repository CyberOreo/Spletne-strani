"""Google Maps scraper — SerpAPI ali Playwright fallback (async)."""
import logging

import aiohttp

from src.config import SERPAPI_KEY
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)
SERPAPI_ENDPOINT = "https://serpapi.com/search"


class MapsScraper(BaseScraper):
    """
    Išče podjetja na Google Maps.
    Zahteva SERPAPI_KEY v .env. Brez ključa preskočimo.
    """

    async def scrape(
        self,
        keyword: str = "",
        region: str = "",
        country: str = "si",
        limit: int = 100,
        skd_code: str = "",
        **kwargs,
    ) -> list[dict]:
        if not SERPAPI_KEY:
            logger.warning("Maps scraper: SERPAPI_KEY ni nastavljen — preskakujem")
            return []

        results: list[dict] = []
        query = f"{keyword} {region}".strip()
        start = 0

        while len(results) < limit:
            params = {
                "engine": "google_maps",
                "q": query,
                "api_key": SERPAPI_KEY,
                "type": "search",
                "start": start,
                "hl": "en",
            }

            html_or_json = await self._serpapi_request(params)
            if not html_or_json:
                break

            local_results = html_or_json.get("local_results", [])
            if not local_results:
                break

            for item in local_results:
                if len(results) >= limit:
                    break
                data = self._parse_result(item, skd_code, region, country)
                if data:
                    ws = await self.detect_website_status(data.get("website_url"))
                    data.update(ws)
                    results.append(data)

            if len(local_results) < 20:
                break
            start += 20

        logger.info("Maps: %d rezultatov za '%s'", len(results), query)
        return results

    async def _serpapi_request(self, params: dict) -> dict | None:
        await self._rate_limit()
        try:
            async with self._session.get(SERPAPI_ENDPOINT, params=params) as resp:
                if resp.status != 200:
                    logger.warning("SerpAPI HTTP %d", resp.status)
                    return None
                return await resp.json()
        except Exception as exc:
            logger.warning("SerpAPI napaka: %s", exc)
            return None

    def _parse_result(self, item: dict, skd_code: str, region: str, country: str) -> dict | None:
        try:
            company_name = item.get("title", "")
            if not company_name:
                return None

            address = item.get("address", "")
            phone = item.get("phone", None)
            website_url = item.get("website", None)

            return {
                "company_name": company_name,
                "contact_person": None,
                "activity": item.get("type", None),
                "skd_code": skd_code,
                "email": None,
                "phone": phone,
                "address": address,
                "city": region,
                "region": region,
                "country": country,
                "website_url": website_url,
                "website_status": "none",
                "website_year": None,
                "facebook_url": None,
                "data_source": "google_maps",
            }
        except Exception as exc:
            logger.debug("Maps parse napaka: %s", exc)
            return None
