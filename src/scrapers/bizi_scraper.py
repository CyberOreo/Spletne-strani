"""Scraper za Bizi.si — iskanje po SKD kodi in regiji (async)."""
import logging

from bs4 import BeautifulSoup

from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)
BIZI_BASE = "https://www.bizi.si"


class BiziScraper(BaseScraper):
    """Zbira podatke o podjetjih iz bizi.si."""

    async def scrape(
        self,
        skd_code: str = "",
        region: str = "",
        keyword: str = "",
        limit: int = 100,
        **kwargs,
    ) -> list[dict]:
        results: list[dict] = []
        page = 1

        while len(results) < limit:
            url = self._build_url(skd_code, region, keyword, page)
            html = await self._get(url)
            if html is None:
                break

            soup = BeautifulSoup(html, "html.parser")
            listings = (
                soup.select(".company-item")
                or soup.select("article.result-item")
                or soup.select("div[class*='result']")
            )

            if not listings:
                logger.info("Bizi.si: ni rezultatov na strani %d", page)
                break

            for item in listings:
                if len(results) >= limit:
                    break
                data = self._parse_listing(item, skd_code, region)
                if data:
                    # Pridobi detajle (email) z detajlne strani
                    detail_link = item.select_one("a[href*='/podjetje/']")
                    if detail_link and not data.get("email"):
                        detail_url = detail_link["href"]
                        if not detail_url.startswith("http"):
                            detail_url = BIZI_BASE + detail_url
                        data = await self._enrich_from_detail(data, detail_url)

                    # Zaznaj status spletne strani
                    ws = await self.detect_website_status(data.get("website_url"))
                    data.update(ws)
                    results.append(data)

            next_btn = soup.select_one("a[rel='next'], .pagination .next, a[aria-label='Next']")
            if not next_btn:
                break
            page += 1

        logger.info("Bizi.si: zbrano %d rezultatov (SKD: %s, regija: %s)",
                    len(results), skd_code, region)
        return results

    def _build_url(self, skd_code: str, region: str, keyword: str, page: int) -> str:
        params = []
        if keyword:
            params.append(f"q={keyword.replace(' ', '+')}")
        if skd_code:
            params.append(f"skd={skd_code.replace('.', '')}")
        if region:
            params.append(f"regija={region.replace(' ', '+')}")
        if page > 1:
            params.append(f"stran={page}")
        return f"{BIZI_BASE}/iskanje/?{'&'.join(params)}"

    def _parse_listing(self, item, skd_code: str, region: str) -> dict | None:
        try:
            name_el = item.select_one("h2 a, h3 a, .company-name a, a[class*='name']")
            if not name_el:
                name_el = item.select_one("h2, h3, .company-name")
            company_name = name_el.get_text(strip=True) if name_el else ""
            if not company_name:
                return None

            addr_el = item.select_one(".address, .location, [class*='addr']")
            address = addr_el.get_text(strip=True) if addr_el else ""

            phone_el = item.select_one("a[href^='tel:']")
            phone = ""
            if phone_el:
                phone = phone_el["href"].replace("tel:", "").strip()

            email_el = item.select_one("a[href^='mailto:']")
            email = ""
            if email_el:
                email = email_el["href"].replace("mailto:", "").split("?")[0].strip()

            web_el = item.select_one("a[class*='web'], a[class*='url']")
            website_url = ""
            if web_el and web_el.get("href", "").startswith("http"):
                if "bizi.si" not in web_el["href"]:
                    website_url = web_el["href"]

            return {
                "company_name": company_name,
                "contact_person": None,
                "activity": None,
                "skd_code": skd_code,
                "email": email or None,
                "phone": phone or None,
                "address": address or None,
                "city": self._extract_city_from_address(address) or region,
                "region": region,
                "country": "si",
                "website_url": website_url or None,
                "website_status": "none",
                "website_year": None,
                "data_source": "bizi.si",
            }
        except Exception as exc:
            logger.debug("Napaka pri parsiranju Bizi: %s", exc)
            return None

    async def _enrich_from_detail(self, data: dict, url: str) -> dict:
        html = await self._get(url)
        if not html:
            return data
        soup = BeautifulSoup(html, "html.parser")

        if not data.get("email"):
            em = soup.select_one("a[href^='mailto:']")
            if em:
                data["email"] = em["href"].replace("mailto:", "").split("?")[0].strip()

        if not data.get("phone"):
            ph = soup.select_one("a[href^='tel:']")
            if ph:
                data["phone"] = ph["href"].replace("tel:", "").strip()

        if not data.get("website_url"):
            for a in soup.select("a[href^='http']"):
                href = a.get("href", "")
                if href and "bizi.si" not in href and "google" not in href:
                    data["website_url"] = href
                    break

        if not data.get("contact_person"):
            person_el = soup.select_one(".contact-name, [class*='person'], [class*='owner']")
            if person_el:
                data["contact_person"] = person_el.get_text(strip=True)

        return data
