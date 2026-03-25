"""Scraper za Ajpes.si — javni register s.p. in d.o.o. (async)."""
import logging

from bs4 import BeautifulSoup

from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)
AJPES_BASE = "https://www.ajpes.si"


class AjpesScraper(BaseScraper):
    """Išče aktivna podjetja v registru Ajpes po SKD kodi."""

    async def scrape(self, skd_code: str = "", region: str = "",
                     keyword: str = "", limit: int = 100, **kwargs) -> list[dict]:
        results: list[dict] = []
        skd_clean = skd_code.replace(".", "")

        # Ajpes e-Register iskanje
        page = 1
        while len(results) < limit:
            url = (
                f"{AJPES_BASE}/eReg/Podjetje/Iskanje"
                f"?NazivFirme=&skd={skd_clean}"
                f"&ObcinaID=&stran={page}"
            )
            html = await self._get(url)
            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("table.seznam tr:not(:first-child), table tbody tr")

            if not rows:
                break

            for row in rows:
                if len(results) >= limit:
                    break
                data = self._parse_row(row, skd_code, region)
                if data:
                    results.append(data)

            if not soup.select_one("a[class*='naslednja'], a[title*='next']"):
                break
            page += 1

        logger.info("Ajpes: %d rezultatov (SKD: %s)", len(results), skd_code)
        return results

    def _parse_row(self, row, skd_code: str, region: str) -> dict | None:
        try:
            cells = row.select("td")
            if len(cells) < 3:
                return None

            company_name = cells[0].get_text(strip=True)
            if not company_name:
                return None

            address = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            city = self._extract_city_from_address(address) or region

            # Pridobi link na detajlno stran
            link = row.select_one("a[href]")
            detail_url = ""
            if link:
                href = link.get("href", "")
                detail_url = href if href.startswith("http") else AJPES_BASE + href

            return {
                "company_name": company_name,
                "contact_person": None,
                "activity": skd_code,
                "skd_code": skd_code,
                "email": None,
                "phone": None,
                "address": address or None,
                "city": city,
                "region": region,
                "country": "si",
                "website_url": None,
                "website_status": "none",
                "website_year": None,
                "data_source": "ajpes.si",
                "_detail_url": detail_url,
            }
        except Exception as exc:
            logger.debug("Napaka Ajpes row: %s", exc)
            return None
