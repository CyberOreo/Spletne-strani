"""Overpass API scraper — primarni vir podatkov za B2B lead generation.

Poizveduje po poslovnih subjektih na OpenStreetMap prek Overpass API-ja.
Podpira vse 10 EU držav. Vrne do `limit` rezultatov na klic.
"""
import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote_plus

import aiohttp

from src.scrapers.base_scraper import BaseScraper


def _url_encode(text: str) -> str:
    """URL-kodira poizvedbo za POST telo (application/x-www-form-urlencoded)."""
    return quote_plus(text)

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Preslikava dvočrkovna ISO koda → ISO 3166-1 alfa-2 (kot jo pozna OSM)
COUNTRY_ISO: dict[str, str] = {
    "si": "SI",
    "hr": "HR",
    "at": "AT",
    "de": "DE",
    "it": "IT",
    "cz": "CZ",
    "sk": "SK",
    "hu": "HU",
    "ro": "RO",
    "pl": "PL",
}

# Preslikava naše kategorije industrije → OSM tagi
# Vsak vnos je seznam (tag_key, tag_value_ali_regex) parov
INDUSTRY_OSM_TAGS: dict[str, list[tuple[str, str]]] = {
    "plumber":      [("craft", "plumber"), ("shop", "plumber")],
    "electrician":  [("craft", "electrician"), ("shop", "electrician")],
    "painter":      [("craft", "painter"), ("craft", "decorator")],
    "carpenter":    [("craft", "carpenter"), ("craft", "joiner"), ("shop", "furniture")],
    "roofer":       [("craft", "roofer")],
    "mason":        [("craft", "mason"), ("craft", "stonemason")],
    "auto_repair":  [("shop", "car_repair"), ("amenity", "car_repair")],
    "hair_salon":   [("shop", "hairdresser"), ("amenity", "hairdresser")],
    "cleaning":     [("office", "cleaning_company"), ("craft", "cleaning")],
    "restaurant":   [("amenity", "restaurant"), ("amenity", "fast_food")],
    "guesthouse":   [("tourism", "guest_house"), ("tourism", "hotel"), ("tourism", "motel")],
    "accounting":   [("office", "accountant"), ("office", "financial")],
    "dentist":      [("amenity", "dentist")],
    "fitness":      [("leisure", "fitness_centre"), ("sport", "fitness")],
    "florist":      [("shop", "florist")],
    "real_estate":  [("office", "estate_agent")],
    # Generični fallback — zajame vse poslovne objekte
    "":             [
        ("shop", ""),
        ("office", ""),
        ("craft", ""),
        ("amenity", "restaurant|cafe|bar|hotel|bank|pharmacy|dentist|fast_food"),
        ("tourism", "hotel|guest_house|hostel"),
    ],
}

# Mesta po državah za fallback (ko državna poizvedba traja predolgo)
CITIES_BY_COUNTRY: dict[str, list[str]] = {
    "si": ["Ljubljana", "Maribor", "Celje", "Kranj", "Koper", "Velenje",
           "Novo Mesto", "Ptuj", "Murska Sobota", "Nova Gorica"],
    "hr": ["Zagreb", "Split", "Rijeka", "Osijek", "Zadar", "Slavonski Brod",
           "Pula", "Šibenik", "Dubrovnik", "Varaždin"],
    "at": ["Wien", "Graz", "Linz", "Salzburg", "Innsbruck", "Klagenfurt",
           "Wels", "Sankt Pölten", "Dornbirn", "Wiener Neustadt"],
    "de": ["Berlin", "München", "Hamburg", "Frankfurt am Main", "Köln",
           "Stuttgart", "Düsseldorf", "Leipzig", "Dortmund", "Nürnberg",
           "Dresden", "Bremen", "Hannover", "Duisburg", "Bochum"],
    "it": ["Roma", "Milano", "Napoli", "Torino", "Palermo", "Genova",
           "Bologna", "Firenze", "Venezia", "Trieste", "Udine", "Verona"],
    "cz": ["Praha", "Brno", "Ostrava", "Plzeň", "Liberec", "Olomouc",
           "České Budějovice", "Hradec Králové", "Pardubice", "Zlín"],
    "sk": ["Bratislava", "Košice", "Prešov", "Žilina", "Banská Bystrica",
           "Nitra", "Trnava", "Trenčín", "Martin", "Poprad"],
    "hu": ["Budapest", "Debrecen", "Miskolc", "Szeged", "Pécs", "Győr",
           "Nyíregyháza", "Kecskemét", "Székesfehérvár", "Szombathely"],
    "ro": ["București", "Cluj-Napoca", "Timișoara", "Iași", "Constanța",
           "Craiova", "Brașov", "Galați", "Ploiești", "Oradea"],
    "pl": ["Warszawa", "Kraków", "Łódź", "Wrocław", "Poznań", "Gdańsk",
           "Szczecin", "Katowice", "Lublin", "Białystok", "Bydgoszcz",
           "Toruń", "Rzeszów", "Gdynia", "Sosnowiec"],
}


def _build_country_query(iso2: str, osm_tags: list[tuple[str, str]], limit: int) -> str:
    """Sestavi Overpass QL poizvedbo za celotno državo."""
    filters = _build_tag_filters(osm_tags)
    return f"""[out:json][timeout:120];
area["ISO3166-1"="{iso2}"]->.country;
(
{filters}
);
out body center {limit};"""


def _build_city_query(city: str, osm_tags: list[tuple[str, str]], limit: int) -> str:
    """Sestavi Overpass QL poizvedbo za posamezno mesto."""
    filters = _build_tag_filters(osm_tags, area_var=".city")
    return f"""[out:json][timeout:90];
area["name"="{city}"]->.city;
(
{filters}
);
out body center {limit};"""


def _build_tag_filters(
    osm_tags: list[tuple[str, str]],
    area_var: str = ".country",
) -> str:
    """Pretvori seznam (key, value) parov v Overpass filter vrstice."""
    lines: list[str] = []
    for key, value in osm_tags:
        if not value:
            # Splošni filter — samo po ključu, z imenom
            for node_type in ("node", "way"):
                lines.append(f'  {node_type}["name"]["{key}"](area{area_var});')
        elif "|" in value:
            # Regex filter
            for node_type in ("node", "way"):
                lines.append(f'  {node_type}["name"]["{key}"~"{value}"](area{area_var});')
        else:
            # Točna vrednost
            for node_type in ("node", "way"):
                lines.append(f'  {node_type}["name"]["{key}"="{value}"](area{area_var});')
    return "\n".join(lines)


def _parse_element(el: dict, country_code: str) -> dict | None:
    """Pretvori en OSM element v lead dict."""
    tags: dict[str, str] = el.get("tags", {})

    company_name = tags.get("name", "").strip()
    if not company_name:
        return None

    # Naslov
    street = tags.get("addr:street", "")
    housenumber = tags.get("addr:housenumber", "")
    postcode = tags.get("addr:postcode", "")
    city = tags.get("addr:city", "") or tags.get("addr:town", "") or tags.get("addr:village", "")

    address_parts = []
    if street:
        address_parts.append(f"{street} {housenumber}".strip())
    if postcode:
        address_parts.append(postcode)
    if city:
        address_parts.append(city)
    address = ", ".join(p for p in address_parts if p)

    # Kontakt
    phone = (
        tags.get("phone")
        or tags.get("contact:phone")
        or tags.get("mobile")
        or tags.get("contact:mobile")
        or ""
    )
    email = (
        tags.get("email")
        or tags.get("contact:email")
        or ""
    )
    website_url = (
        tags.get("website")
        or tags.get("contact:website")
        or tags.get("url")
        or ""
    )

    # Čiščenje kontaktnih podatkov
    phone = _clean_phone(phone)
    email = _clean_email(email)
    website_url = _clean_url(website_url)

    # Določi status spletne strani
    if website_url:
        website_status = "has_website"
    else:
        website_status = "none"

    # Določi aktivnost iz OSM tagov
    activity = _detect_activity(tags)

    return {
        "company_name": company_name,
        "contact_person": None,
        "activity": activity,
        "skd_code": None,
        "email": email or None,
        "phone": phone or None,
        "address": address or None,
        "city": city or None,
        "region": city or None,
        "country": country_code,
        "website_url": website_url or None,
        "website_status": website_status,
        "website_year": None,
        "data_source": "openstreetmap",
    }


def _detect_activity(tags: dict[str, str]) -> str | None:
    """Določi kategorijo podjetja iz OSM tagov."""
    priority_keys = ["shop", "craft", "office", "amenity", "tourism", "leisure"]
    for key in priority_keys:
        val = tags.get(key)
        if val and val not in ("yes", "no", ""):
            return f"{key}:{val}"
    return None


def _clean_phone(phone: str) -> str:
    if not phone:
        return ""
    # Ohrani samo številke, presledke, +, -, (, )
    cleaned = re.sub(r"[^\d\s\+\-\(\)]", "", phone).strip()
    return cleaned[:30]  # Omeji dolžino


def _clean_email(email: str) -> str:
    if not email:
        return ""
    email = email.strip().lower()
    # Osnovna validacija
    if "@" not in email or "." not in email.split("@")[-1]:
        return ""
    return email[:100]


def _clean_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if url in ("-", "N/A", "http://", "https://", "none"):
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url[:200]


class OverpassScraper(BaseScraper):
    """
    Primarni scraper — poizveduje prek OpenStreetMap Overpass API.

    Strategija:
    1. Najprej poskusi celotno državno poizvedbo (hitro za manjše države).
    2. Če pride do timeoutov ali premalo rezultatov, se preklopi na
       poizvedbe po mestih (fallback).
    3. Med poizvedbami počaka 2–3 sekunde, da ne preobremeni API-ja.
    """

    OVERPASS_TIMEOUT = 150  # sekunde za aiohttp
    BETWEEN_REQUESTS_DELAY = 2.5  # sekunde med Overpass zahtevki

    def __init__(self):
        super().__init__()
        # Overpass potrebuje daljši timeout kot privzeti BaseScraper
        self._overpass_session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        await super().__aenter__()
        connector = aiohttp.TCPConnector(limit=5, ssl=True)
        timeout = aiohttp.ClientTimeout(total=self.OVERPASS_TIMEOUT)
        self._overpass_session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "User-Agent": "B2BLeadGen/1.0 (contact@example.com)",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        return self

    async def __aexit__(self, *args):
        if self._overpass_session:
            await self._overpass_session.close()
        await super().__aexit__(*args)

    async def scrape(
        self,
        industry: str = "",
        country: str = "si",
        limit: int = 300,
        **kwargs,
    ) -> list[dict]:
        """
        Zberi poslovne leade za dano državo in industrijo.

        Args:
            industry: Ključ iz INDUSTRY_OSM_TAGS (npr. "plumber"). Prazen = vse.
            country:  Dvočrkovna koda države (npr. "si", "de").
            limit:    Maksimalno število rezultatov.
        """
        country = country.lower()
        iso2 = COUNTRY_ISO.get(country)
        if not iso2:
            logger.warning("OverpassScraper: neznana država '%s'", country)
            return []

        osm_tags = INDUSTRY_OSM_TAGS.get(industry, INDUSTRY_OSM_TAGS[""])
        results: list[dict] = []

        logger.info(
            "OverpassScraper: začenjam poizvedbo — država=%s, industrija='%s', limit=%d",
            country, industry, limit,
        )

        # ── 1. Poskus: celotna državna poizvedba ─────────────────────────────
        try:
            query = _build_country_query(iso2, osm_tags, limit)
            elements = await self._post_overpass(query)
            if elements is not None:
                results = self._parse_elements(elements, country, limit)
                logger.info(
                    "OverpassScraper: državna poizvedba vrnila %d elementov (%s)",
                    len(results), country,
                )
        except asyncio.TimeoutError:
            logger.warning(
                "OverpassScraper: timeout pri državni poizvedbi (%s) — preklop na mesta",
                country,
            )
            elements = None
        except Exception as exc:
            logger.warning(
                "OverpassScraper: napaka pri državni poizvedbi (%s): %s — preklop na mesta",
                country, exc,
            )
            elements = None

        # ── 2. Fallback: poizvedbe po mestih ─────────────────────────────────
        if len(results) < max(50, limit // 3):
            logger.info(
                "OverpassScraper: premalo rezultatov (%d), preklop na mestne poizvedbe (%s)",
                len(results), country,
            )
            results = await self._scrape_by_cities(country, osm_tags, limit)

        logger.info(
            "OverpassScraper: končano — %d leadov (država=%s, industrija='%s')",
            len(results), country, industry,
        )
        return results[:limit]

    async def _scrape_by_cities(
        self,
        country: str,
        osm_tags: list[tuple[str, str]],
        total_limit: int,
    ) -> list[dict]:
        """Poizveduje po posameznih mestih in združi rezultate."""
        cities = CITIES_BY_COUNTRY.get(country, [])
        if not cities:
            logger.warning("OverpassScraper: ni mest za državo '%s'", country)
            return []

        all_results: list[dict] = []
        per_city_limit = max(50, (total_limit // len(cities)) + 20)
        seen_names: set[str] = set()

        for city in cities:
            if len(all_results) >= total_limit:
                break

            try:
                query = _build_city_query(city, osm_tags, per_city_limit)
                elements = await self._post_overpass(query)
                if elements is not None:
                    parsed = self._parse_elements(elements, country, per_city_limit)
                    # Deduplikacija po imenu podjetja
                    for lead in parsed:
                        key = (lead["company_name"].lower(), lead.get("city", "").lower())
                        if key not in seen_names:
                            seen_names.add(key)
                            all_results.append(lead)
                    logger.info(
                        "OverpassScraper: mesto %s → %d rezultatov (skupaj: %d)",
                        city, len(parsed), len(all_results),
                    )
            except asyncio.TimeoutError:
                logger.warning("OverpassScraper: timeout za mesto %s — preskakujem", city)
            except Exception as exc:
                logger.warning("OverpassScraper: napaka za mesto %s: %s", city, exc)

            # Obvezna zamuda med zahtevki
            await asyncio.sleep(self.BETWEEN_REQUESTS_DELAY)

        return all_results[:total_limit]

    async def _post_overpass(self, query: str) -> list[dict] | None:
        """
        Pošlje POST zahtevek na Overpass API in vrne seznam elementov.
        Vrne None ob napaki ali timeoutu.
        """
        if self._overpass_session is None:
            raise RuntimeError("OverpassScraper ni inicializiran — uporabi 'async with'")

        # Obvezna zamuda pred vsako Overpass poizvedbo
        await asyncio.sleep(self.BETWEEN_REQUESTS_DELAY)

        try:
            async with self._overpass_session.post(
                OVERPASS_URL,
                data=f"data={_url_encode(query)}",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as resp:
                if resp.status == 429:
                    logger.warning("OverpassScraper: rate limit (429) — čakam 30s")
                    await asyncio.sleep(30)
                    return None
                if resp.status == 504:
                    logger.warning("OverpassScraper: gateway timeout (504)")
                    raise asyncio.TimeoutError("Overpass gateway timeout")
                if resp.status >= 400:
                    body = await resp.text()
                    logger.warning(
                        "OverpassScraper: HTTP %d — %s", resp.status, body[:200]
                    )
                    return None

                data: dict[str, Any] = await resp.json(content_type=None)
                elements: list[dict] = data.get("elements", [])
                logger.debug(
                    "OverpassScraper: Overpass vrnil %d elementov", len(elements)
                )
                return elements

        except asyncio.TimeoutError:
            raise
        except aiohttp.ClientError as exc:
            logger.warning("OverpassScraper: omrežna napaka: %s", exc)
            return None
        except Exception as exc:
            logger.warning("OverpassScraper: nepričakovana napaka: %s", exc)
            return None

    def _parse_elements(
        self,
        elements: list[dict],
        country: str,
        limit: int,
    ) -> list[dict]:
        """Pretvori seznam OSM elementov v seznam lead dictov."""
        results: list[dict] = []
        for el in elements:
            if len(results) >= limit:
                break
            lead = _parse_element(el, country)
            if lead is not None:
                results.append(lead)
        return results
