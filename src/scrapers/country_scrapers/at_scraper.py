"""AT — Herold.at (Austria) scraper (async)."""
import logging
from bs4 import BeautifulSoup
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)
BASE = "https://www.herold.at"

AT_CATEGORIES = {
    "plumber": "Installateur", "electrician": "Elektriker", "painter": "Maler",
    "carpenter": "Tischler", "roofer": "Dachdecker", "mason": "Maurer",
    "auto_repair": "KFZ-Werkstatt", "hair_salon": "Friseur",
    "cleaning": "Gebäudereinigung", "restaurant": "Restaurant",
    "guesthouse": "Pension", "accounting": "Buchhalter",
    "dentist": "Zahnarzt", "fitness": "Fitnesscenter",
    "florist": "Blumengeschäft", "real_estate": "Immobilienmakler",
}


class AtScraper(BaseScraper):
    async def scrape(self, industry: str = "", region: str = "",
                     limit: int = 100, skd_code: str = "", **kwargs) -> list[dict]:
        category = AT_CATEGORIES.get(industry, industry)
        results: list[dict] = []
        page = 1

        while len(results) < limit:
            url = f"{BASE}/suche/{category.replace(' ', '-')}"
            if region:
                url += f"/{region.replace(' ', '-')}"
            if page > 1:
                url += f"?page={page}"

            html = await self._get(url)
            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")
            items = (
                soup.select(".result-entry, [class*='listing'], article[class*='result']")
            )
            if not items:
                break

            for item in items:
                if len(results) >= limit:
                    break
                data = self._parse(item, skd_code, region, category)
                if data:
                    ws = await self.detect_website_status(data.get("website_url"))
                    data.update(ws)
                    results.append(data)

            if not soup.select_one("a[rel='next']"):
                break
            page += 1

        logger.info("Herold.at: %d rezultatov", len(results))
        return results

    def _parse(self, item, skd_code: str, region: str, category: str) -> dict | None:
        try:
            name_el = item.select_one("h2, h3, [class*='name']")
            company_name = name_el.get_text(strip=True) if name_el else ""
            if not company_name:
                return None

            addr_el = item.select_one("address, [class*='address']")
            address = addr_el.get_text(strip=True) if addr_el else ""

            phone_el = item.select_one("a[href^='tel:']")
            phone = phone_el["href"].replace("tel:", "").strip() if phone_el else None

            email_el = item.select_one("a[href^='mailto:']")
            email = email_el["href"].replace("mailto:", "").split("?")[0] if email_el else None

            web_el = item.select_one("a[class*='web'], a[href*='www']")
            website_url = None
            if web_el and web_el.get("href", "").startswith("http"):
                if "herold.at" not in web_el["href"]:
                    website_url = web_el["href"]

            return {
                "company_name": company_name, "contact_person": None,
                "activity": category, "skd_code": skd_code,
                "email": email, "phone": phone,
                "address": address or None,
                "city": self._extract_city_from_address(address) or region,
                "region": region, "country": "at",
                "website_url": website_url, "website_status": "none",
                "website_year": None, "data_source": "herold.at",
            }
        except Exception as exc:
            logger.debug("Herold.at parse: %s", exc)
            return None
