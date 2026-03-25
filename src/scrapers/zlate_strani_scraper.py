"""Scraper za Zlate strani (zlatestrani.si) — async."""
import logging

from bs4 import BeautifulSoup

from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)
ZLATE_BASE = "https://www.zlatestrani.si"

SKD_TO_CATEGORY = {
    "43.22": "vodovodar", "43.21": "elektricar", "43.34": "slikopleskar",
    "43.32": "mizar", "43.91": "krovstvo", "43.11": "zidar",
    "45.20": "avtomehanik", "96.02": "frizer", "81.21": "cistilni-servis",
    "49.41": "prevoznik", "56.10": "restavracija", "55.20": "prenocisce",
    "69.20": "racunovodski-servis", "86.23": "zobozdravnik",
    "93.13": "fitnes", "47.76": "cvecicarna", "68.31": "nepremicninska-agencija",
}


class ZlateStraniScraper(BaseScraper):
    async def scrape(self, skd_code: str = "", region: str = "",
                     keyword: str = "", limit: int = 100, **kwargs) -> list[dict]:
        category = SKD_TO_CATEGORY.get(skd_code, keyword.replace(" ", "-").lower() or "")
        if not category:
            return []

        results: list[dict] = []
        page = 1

        while len(results) < limit:
            url = f"{ZLATE_BASE}/iskanje/{category}"
            if region:
                url += f"/{region.lower().replace(' ', '-')}"
            if page > 1:
                url += f"?stran={page}"

            html = await self._get(url)
            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")
            items = soup.select(".listing-item, .result-item, article[class*='company']")
            if not items:
                break

            for item in items:
                if len(results) >= limit:
                    break
                data = self._parse(item, skd_code, region)
                if data:
                    ws = await self.detect_website_status(data.get("website_url"))
                    data.update(ws)
                    results.append(data)

            if not soup.select_one("a[rel='next']"):
                break
            page += 1

        logger.info("Zlate strani: %d rezultatov", len(results))
        return results

    def _parse(self, item, skd_code: str, region: str) -> dict | None:
        try:
            name_el = item.select_one("h2, h3, .name, a[class*='title']")
            company_name = name_el.get_text(strip=True) if name_el else ""
            if not company_name:
                return None

            addr_el = item.select_one(".address, [class*='addr']")
            address = addr_el.get_text(strip=True) if addr_el else ""

            phone_el = item.select_one("a[href^='tel:']")
            phone = phone_el["href"].replace("tel:", "").strip() if phone_el else None

            email_el = item.select_one("a[href^='mailto:']")
            email = email_el["href"].replace("mailto:", "").split("?")[0] if email_el else None

            web_el = item.select_one("a[class*='web'], a[class*='website']")
            website_url = None
            if web_el and web_el.get("href", "").startswith("http"):
                if "zlatestrani.si" not in web_el["href"]:
                    website_url = web_el["href"]

            return {
                "company_name": company_name,
                "contact_person": None,
                "activity": None,
                "skd_code": skd_code,
                "email": email,
                "phone": phone,
                "address": address or None,
                "city": self._extract_city_from_address(address) or region,
                "region": region,
                "country": "si",
                "website_url": website_url,
                "website_status": "none",
                "website_year": None,
                "data_source": "zlatestrani.si",
            }
        except Exception as exc:
            logger.debug("Napaka Zlate strani: %s", exc)
            return None
