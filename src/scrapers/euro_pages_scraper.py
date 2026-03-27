"""EuroPages.com — pan-EU scraper za podjetja (async)."""
import logging

from bs4 import BeautifulSoup

from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)
EURO_BASE = "https://www.europages.co.uk"

# Kategorije na EuroPages po industrijsko-specifičnih ključnih besedah
EURO_CATEGORIES = {
    "plumber": "plumbing-sanitary-heating",
    "electrician": "electrical-installation",
    "painter": "painting-decorating",
    "carpenter": "carpentry-joinery",
    "roofer": "roofing",
    "mason": "masonry-bricklaying",
    "auto_repair": "vehicle-repair-maintenance",
    "hair_salon": "hairdressing-beauty",
    "cleaning": "cleaning-services",
    "restaurant": "restaurants-cafes-catering",
    "guesthouse": "hotels-guesthouses",
    "accounting": "accounting-bookkeeping",
    "dentist": "dental-care",
    "fitness": "sports-fitness-leisure",
    "florist": "flowers-plants-seeds",
    "real_estate": "real-estate-agencies",
}


class EuroPagesScraper(BaseScraper):
    """Zbira EU podjetja iz Europages.co.uk."""

    async def scrape(
        self,
        keyword: str = "",
        industry: str = "",
        region: str = "",
        country: str = "",
        limit: int = 200,
        skd_code: str = "",
        **kwargs,
    ) -> list[dict]:
        category = EURO_CATEGORIES.get(industry, keyword.lower().replace(" ", "-") or "services")
        results: list[dict] = []
        page = 1

        while len(results) < limit:
            url = self._build_url(category, region, country, page)
            html = await self._get(url)
            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")
            listings = (
                soup.select("article.company-result")
                or soup.select(".company-card")
                or soup.select("li[class*='result']")
            )

            if not listings:
                logger.info("EuroPages: ni rezultatov na strani %d", page)
                break

            for item in listings:
                if len(results) >= limit:
                    break
                data = self._parse(item, skd_code, category, country)
                if data:
                    # Obišči detail stran za email, če ga ni v listingu
                    if not data.get("email"):
                        detail_link = item.select_one(
                            "a[href*='/company/'], a[href*='/firma/'], "
                            "a[href*='/entreprise/'], h2 a, h3 a"
                        )
                        if detail_link:
                            detail_href = detail_link.get("href", "")
                            if detail_href and "europages" in detail_href:
                                detail_url = detail_href if detail_href.startswith("http") else EURO_BASE + detail_href
                                data = await self._enrich_from_detail(data, detail_url)
                    ws = await self.detect_website_status(data.get("website_url"))
                    data.update(ws)
                    results.append(data)

            if not soup.select_one("a[rel='next'], a[class*='next']"):
                break
            page += 1

        logger.info("EuroPages: %d rezultatov (kategorija: %s)", len(results), category)
        return results

    def _build_url(self, category: str, region: str, country: str, page: int) -> str:
        url = f"{EURO_BASE}/en/cat/{category}"
        params = []
        if country:
            params.append(f"countryCode={country.upper()}")
        if region:
            params.append(f"city={region.replace(' ', '+')}")
        if page > 1:
            params.append(f"page={page}")
        if params:
            url += "?" + "&".join(params)
        return url

    def _parse(self, item, skd_code: str, category: str, country: str) -> dict | None:
        try:
            name_el = item.select_one("h2, h3, a[class*='company-name'], .company-name")
            company_name = name_el.get_text(strip=True) if name_el else ""
            if not company_name:
                return None

            addr_el = item.select_one("address, .address, [class*='location']")
            address = addr_el.get_text(strip=True) if addr_el else ""

            phone_el = item.select_one("a[href^='tel:'], [class*='phone']")
            phone = None
            if phone_el:
                phone = phone_el.get("href", "").replace("tel:", "").strip() or phone_el.get_text(strip=True)

            email_el = item.select_one("a[href^='mailto:']")
            email = email_el["href"].replace("mailto:", "").split("?")[0] if email_el else None

            web_el = item.select_one("a[class*='website'], a[class*='web'], a[href*='www']")
            website_url = None
            if web_el and web_el.get("href", "").startswith("http"):
                if "europages" not in web_el["href"]:
                    website_url = web_el["href"]

            # Detekcija države iz naslova
            detected_country = country or self._detect_country_from_address(address)

            return {
                "company_name": company_name,
                "contact_person": None,
                "activity": category.replace("-", " ").title(),
                "skd_code": skd_code,
                "email": email,
                "phone": phone,
                "address": address or None,
                "city": self._extract_city_from_address(address),
                "region": self._extract_city_from_address(address),
                "country": detected_country,
                "website_url": website_url,
                "website_status": "none",
                "website_year": None,
                "data_source": "europages.com",
            }
        except Exception as exc:
            logger.debug("EuroPages parse napaka: %s", exc)
            return None

    async def _enrich_from_detail(self, data: dict, url: str) -> dict:
        """Obišči detail stran in izvleče email/telefon, ki ga ni v listingu."""
        html = await self._get(url)
        if not html:
            return data
        soup = BeautifulSoup(html, "html.parser")
        if not data.get("email"):
            em = soup.select_one("a[href^='mailto:']")
            if em:
                email = em["href"].replace("mailto:", "").split("?")[0].strip()
                if "@" in email:
                    data["email"] = email.lower()
        if not data.get("phone"):
            ph = soup.select_one("a[href^='tel:']")
            if ph:
                data["phone"] = ph["href"].replace("tel:", "").strip()
        return data

    @staticmethod
    def _detect_country_from_address(address: str) -> str:
        """Groba detekcija države iz naslova."""
        addr_lower = address.lower()
        country_hints = {
            "deutschland": "de", "germany": "de",
            "österreich": "at", "austria": "at",
            "slovenija": "si", "slovenia": "si",
            "hrvatska": "hr", "croatia": "hr",
            "italia": "it", "italy": "it",
            "polska": "pl", "poland": "pl",
            "česká": "cz", "czech": "cz",
            "magyarország": "hu", "hungary": "hu",
            "românia": "ro", "romania": "ro",
        }
        for hint, code in country_hints.items():
            if hint in addr_lower:
                return code
        return "eu"
