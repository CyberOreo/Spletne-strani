"""Konfiguracija sistema — .env loader, EU konstante, industrijsko-specifični podatki."""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env")

# ─── SMTP rotacija ────────────────────────────────────────────────────────────
# Vrne seznam SMTP računov iz JSON ali en privzeti račun
def _load_smtp_accounts() -> list[dict]:
    raw = os.getenv("SMTP_ACCOUNTS", "")
    if raw.strip().startswith("["):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    # Privzeti en račun
    return [{
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "name": os.getenv("SENDER_NAME", ""),
        "phone": os.getenv("SENDER_PHONE", ""),
        "daily_limit": int(os.getenv("DAILY_EMAIL_LIMIT", "3000")),
    }]

SMTP_ACCOUNTS = _load_smtp_accounts()

# ─── IMAP ─────────────────────────────────────────────────────────────────────
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "")

# ─── Limiti ───────────────────────────────────────────────────────────────────
DAILY_EMAIL_LIMIT  = int(os.getenv("DAILY_EMAIL_LIMIT",  "3000"))
DAILY_SCRAPE_LIMIT = int(os.getenv("DAILY_SCRAPE_LIMIT", "3000"))
MIN_DELAY_SECONDS  = int(os.getenv("MIN_DELAY_SECONDS",  "10"))
MAX_DELAY_SECONDS  = int(os.getenv("MAX_DELAY_SECONDS",  "30"))

# ─── Proxy rotacija ───────────────────────────────────────────────────────────
def _load_proxies() -> list[str]:
    raw = os.getenv("PROXY_LIST", "")
    if not raw.strip():
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]

PROXY_LIST = _load_proxies()

# ─── Scraping ─────────────────────────────────────────────────────────────────
SCRAPE_DELAY_MIN = float(os.getenv("SCRAPE_DELAY_MIN", "1"))
SCRAPE_DELAY_MAX = float(os.getenv("SCRAPE_DELAY_MAX", "3"))
SCRAPE_CONCURRENCY = int(os.getenv("SCRAPE_CONCURRENCY", "10"))
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)

# ─── Ostalo ───────────────────────────────────────────────────────────────────
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "")
DATABASE_PATH = str(_BASE_DIR / os.getenv("DATABASE_PATH", "data/leads.db"))
PREVIEW_BASE_URL = os.getenv("PREVIEW_BASE_URL", "http://localhost:8080/previews")
DAILY_RUN_TIME = os.getenv("DAILY_RUN_TIME", "08:00")

# ─── Čas pošiljanja emailov ────────────────────────────────────────────────────
SEND_WINDOW_START = os.getenv("SEND_WINDOW_START", "07:00")
SEND_WINDOW_END   = os.getenv("SEND_WINDOW_END",   "18:00")
SEND_WEEKEND      = os.getenv("SEND_WEEKEND", "false").lower() == "true"

# ─── Overnight način ──────────────────────────────────────────────────────────
OVERNIGHT_SCRAPE_TIME = os.getenv("OVERNIGHT_SCRAPE_TIME", "22:00")
OVERNIGHT_SEND_TIME   = os.getenv("OVERNIGHT_SEND_TIME", DAILY_RUN_TIME)

# ─── Unsubscribe URL (za List-Unsubscribe header) ─────────────────────────────
UNSUBSCRIBE_BASE_URL = os.getenv("UNSUBSCRIBE_BASE_URL", "")

# ─── EU — po-državna konfiguracija ───────────────────────────────────────────
COUNTRIES: dict[str, dict] = {
    "si": {
        "lang": "sl",
        "name": "Slovenija",
        "sources": ["bizi", "zlate_strani", "ajpes", "maps", "euro_pages"],
        "currency": "EUR",
        "greeting": "Spoštovani",
    },
    "hr": {
        "lang": "hr",
        "name": "Hrvatska",
        "sources": ["zlatne_stranice", "maps", "euro_pages"],
        "currency": "EUR",
        "greeting": "Poštovani",
    },
    "at": {
        "lang": "de",
        "name": "Österreich",
        "sources": ["herold", "maps", "euro_pages"],
        "currency": "EUR",
        "greeting": "Sehr geehrte(r)",
    },
    "de": {
        "lang": "de",
        "name": "Deutschland",
        "sources": ["gelbe_seiten", "maps", "euro_pages"],
        "currency": "EUR",
        "greeting": "Sehr geehrte(r)",
    },
    "it": {
        "lang": "it",
        "name": "Italia",
        "sources": ["pagine_bianche", "maps", "euro_pages"],
        "currency": "EUR",
        "greeting": "Gentile",
    },
    "cz": {
        "lang": "cs",
        "name": "Česká republika",
        "sources": ["firmy", "maps", "euro_pages"],
        "currency": "CZK",
        "greeting": "Vážený/á",
    },
    "hu": {
        "lang": "hu",
        "name": "Magyarország",
        "sources": ["aranylap", "maps", "euro_pages"],
        "currency": "HUF",
        "greeting": "Tisztelt",
    },
    "pl": {
        "lang": "pl",
        "name": "Polska",
        "sources": ["panoramafirm", "maps", "euro_pages"],
        "currency": "PLN",
        "greeting": "Szanowny/a",
    },
    "ro": {
        "lang": "ro",
        "name": "România",
        "sources": ["pagina_aurie", "maps", "euro_pages"],
        "currency": "RON",
        "greeting": "Stimate/Stimată",
    },
    "sk": {
        "lang": "sk",
        "name": "Slovensko",
        "sources": ["maps", "euro_pages"],
        "currency": "EUR",
        "greeting": "Vážený/á",
    },
}

ALL_COUNTRY_CODES = list(COUNTRIES.keys())

# ─── SKD kode → naziv dejavnosti (SL) ────────────────────────────────────────
SKD_DEJAVNOSTI: dict[str, str] = {
    "43.22": "Vodovodne in plinske inštalacije",
    "43.21": "Elektroinštalacije",
    "43.34": "Slikopleskarstvo in zastekljevanje",
    "43.32": "Tesarstvo in mizarstvo",
    "43.91": "Krovstvo",
    "43.11": "Rušenje objektov in zemeljska dela",
    "45.20": "Vzdrževanje in popravila motornih vozil",
    "96.02": "Frizerska in druga osebna nega",
    "81.21": "Splošno čiščenje stavb",
    "49.41": "Cestni tovorni promet",
    "56.10": "Dejavnost restavracij in drugih strežb jedi",
    "55.20": "Počitniški domovi in turistične kmetije",
    "69.20": "Računovodske in knjigovodske dejavnosti",
    "86.23": "Zobozdravstvena dejavnost",
    "93.13": "Fitnes centri",
    "47.76": "Cvetličarne",
    "68.31": "Posredništvo v prometu z nepremičninami",
}

# ─── Iskalni ključi po državah (prevodi kategorij) ───────────────────────────
INDUSTRY_TRANSLATIONS: dict[str, dict[str, str]] = {
    "plumber": {
        "sl": "vodovodar", "hr": "vodoinstalater", "de": "Klempner",
        "it": "idraulico", "cs": "instalatér", "hu": "vízszerelő",
        "pl": "hydraulik", "ro": "instalator", "sk": "inštalatér",
    },
    "electrician": {
        "sl": "elektrikar", "hr": "električar", "de": "Elektriker",
        "it": "elettricista", "cs": "elektrikář", "hu": "villanyszerelő",
        "pl": "elektryk", "ro": "electrician", "sk": "elektrikár",
    },
    "painter": {
        "sl": "slikopleskar", "hr": "soboslikar", "de": "Maler",
        "it": "imbianchino", "cs": "malíř pokojů", "hu": "festő",
        "pl": "malarz", "ro": "zugrav", "sk": "maliar",
    },
    "carpenter": {
        "sl": "mizar", "hr": "stolar", "de": "Tischler",
        "it": "falegname", "cs": "truhlář", "hu": "asztalos",
        "pl": "stolarz", "ro": "tâmplar", "sk": "stolár",
    },
    "roofer": {
        "sl": "krovec", "hr": "krovičar", "de": "Dachdecker",
        "it": "copritetto", "cs": "klempíř", "hu": "tetőfedő",
        "pl": "dekarz", "ro": "tinichigiu", "sk": "klampiár",
    },
    "mason": {
        "sl": "zidar", "hr": "zidar", "de": "Maurer",
        "it": "muratore", "cs": "zedník", "hu": "kőműves",
        "pl": "murarz", "ro": "zidar", "sk": "murár",
    },
    "auto_repair": {
        "sl": "avtomehanik", "hr": "automehaničar", "de": "Kfz-Werkstatt",
        "it": "meccanico auto", "cs": "autoservis", "hu": "autószerelő",
        "pl": "mechanik samochodowy", "ro": "mecanic auto", "sk": "autoservis",
    },
    "hair_salon": {
        "sl": "frizer", "hr": "frizer", "de": "Friseur",
        "it": "parrucchiere", "cs": "kadeřník", "hu": "fodrász",
        "pl": "fryzjer", "ro": "frizerie", "sk": "kaderník",
    },
    "cleaning": {
        "sl": "čistilni servis", "hr": "čistionice", "de": "Reinigungsdienst",
        "it": "pulizie", "cs": "úklidová firma", "hu": "takarítás",
        "pl": "firma sprzątająca", "ro": "firmă curățenie", "sk": "upratovacia firma",
    },
    "restaurant": {
        "sl": "restavracija", "hr": "restoran", "de": "Restaurant",
        "it": "ristorante", "cs": "restaurace", "hu": "étterem",
        "pl": "restauracja", "ro": "restaurant", "sk": "reštaurácia",
    },
    "guesthouse": {
        "sl": "prenočišče", "hr": "privatni smještaj", "de": "Pension",
        "it": "pensione", "cs": "penzion", "hu": "panzió",
        "pl": "pensjonat", "ro": "pensiune", "sk": "penzión",
    },
    "accounting": {
        "sl": "računovodski servis", "hr": "računovodstvo", "de": "Buchhalter",
        "it": "commercialista", "cs": "účetní", "hu": "könyvelő",
        "pl": "biuro rachunkowe", "ro": "contabil", "sk": "účtovník",
    },
    "dentist": {
        "sl": "zobozdravnik", "hr": "zubar", "de": "Zahnarzt",
        "it": "dentista", "cs": "zubař", "hu": "fogorvos",
        "pl": "dentysta", "ro": "dentist", "sk": "zubár",
    },
    "fitness": {
        "sl": "fitnes center", "hr": "fitnes", "de": "Fitnessstudio",
        "it": "palestra", "cs": "fitness centrum", "hu": "fitness terem",
        "pl": "siłownia", "ro": "sala de fitness", "sk": "fitnes centrum",
    },
    "florist": {
        "sl": "cvetličarna", "hr": "cvjećarnica", "de": "Blumenladen",
        "it": "fioraio", "cs": "květinářství", "hu": "virágbolt",
        "pl": "kwiaciarnia", "ro": "florărie", "sk": "kvetinárstvo",
    },
    "real_estate": {
        "sl": "nepremičninska agencija", "hr": "agencija za nekretnine",
        "de": "Immobilienmakler", "it": "agenzia immobiliare",
        "cs": "realitní kancelář", "hu": "ingatlaniroda",
        "pl": "agencja nieruchomości", "ro": "agenție imobiliară",
        "sk": "realitná kancelária",
    },
}

# ─── Industrijsko-specifični hooks (za personalizacijo emailov) ───────────────
# Ključ: SKD koda (ali ključna beseda), vrednost: dict po jezikih
INDUSTRIJSKO_DEJSTVO: dict[str, dict[str, str]] = {
    "43.22": {
        "sl": "Stranke iščejo vodovodarja na Google — brez spletne strani ste nevidni.",
        "hr": "Mušterije traže vodoinstalatera na Googleu — bez web stranice ste nevidljivi.",
        "de": "Kunden suchen Klempner auf Google — ohne Webseite sind Sie unsichtbar.",
        "it": "I clienti cercano idraulici su Google — senza sito web siete invisibili.",
    },
    "43.21": {
        "sl": "Večina strank pred klicem poišče električarja na spletu.",
        "hr": "Većina mušterija traži električara online prije poziva.",
        "de": "Die meisten Kunden suchen Elektriker online, bevor sie anrufen.",
        "it": "La maggior parte dei clienti cerca un elettricista online prima di chiamare.",
    },
    "96.02": {
        "sl": "Spletno naročanje terminov zmanjša klice in polni vaš urnik.",
        "hr": "Online rezervacije termina smanjuju pozive i punite vaš raspored.",
        "de": "Online-Terminbuchung reduziert Anrufe und füllt Ihren Kalender.",
        "it": "La prenotazione online degli appuntamenti riduce le chiamate e riempie il calendario.",
    },
    "56.10": {
        "sl": "Spletno naročanje miz in objava menija povečata obisk restavracije.",
        "hr": "Online rezervacije stolova i objava menija povećavaju posjete.",
        "de": "Online-Tischreservierung und Menüanzeige erhöhen die Besucherzahl.",
        "it": "La prenotazione online dei tavoli e il menu aumentano le visite al ristorante.",
    },
    "55.20": {
        "sl": "Rezervacije prek vaše strani namesto Booking.com — brez provizij.",
        "hr": "Rezervacije putem vlastite stranice umjesto Booking.com — bez provizija.",
        "de": "Buchungen über Ihre eigene Seite statt Booking.com — ohne Provision.",
        "it": "Prenotazioni tramite il vostro sito invece di Booking.com — senza commissioni.",
    },
    "86.23": {
        "sl": "Pacienti iščejo zobozdravnika na Google — spletno naročanje poveča zasedenost.",
        "hr": "Pacijenti traže zubara na Googleu — online naručivanje povećava zauzetost.",
        "de": "Patienten suchen Zahnärzte auf Google — Online-Terminbuchung steigert Auslastung.",
        "it": "I pazienti cercano dentisti su Google — la prenotazione online aumenta l'occupazione.",
    },
    "default": {
        "sl": "Večina strank danes podjetje najprej poišče na spletu.",
        "hr": "Većina mušterija danas prvo traži tvrtku na internetu.",
        "de": "Die meisten Kunden suchen heute zuerst online nach Unternehmen.",
        "it": "La maggior parte dei clienti oggi cerca prima online le aziende.",
        "cs": "Většina zákazníků dnes nejdříve hledá firmu online.",
        "hu": "A legtöbb ügyfél ma először online keres vállalkozást.",
        "pl": "Większość klientów najpierw szuka firmy w Internecie.",
        "ro": "Majoritatea clienților caută mai întâi o firmă online.",
        "sk": "Väčšina zákazníkov dnes najskôr hľadá firmu online.",
    },
}

# ─── Regije za iskanje (po državah) ──────────────────────────────────────────
REGIJE_PO_DRZAVAH: dict[str, list[str]] = {
    "si": ["Ljubljana", "Maribor", "Celje", "Kranj", "Velenje", "Koper",
           "Novo mesto", "Ptuj", "Murska Sobota", "Nova Gorica"],
    "hr": ["Zagreb", "Split", "Rijeka", "Osijek", "Zadar", "Slavonski Brod",
           "Pula", "Šibenik", "Dubrovnik", "Varaždin"],
    "at": ["Wien", "Graz", "Linz", "Salzburg", "Innsbruck", "Klagenfurt",
           "Wels", "Sankt Pölten", "Dornbirn"],
    "de": ["Berlin", "München", "Hamburg", "Frankfurt", "Köln", "Stuttgart",
           "Düsseldorf", "Leipzig", "Dortmund", "Nürnberg", "Dresden"],
    "it": ["Roma", "Milano", "Napoli", "Torino", "Palermo", "Genova",
           "Bologna", "Firenze", "Venezia", "Trieste", "Udine"],
    "cz": ["Praha", "Brno", "Ostrava", "Plzeň", "Liberec", "Olomouc",
           "České Budějovice", "Hradec Králové", "Pardubice"],
    "hu": ["Budapest", "Debrecen", "Miskolc", "Szeged", "Pécs", "Győr",
           "Nyíregyháza", "Kecskemét", "Székesfehérvár"],
    "pl": ["Warszawa", "Kraków", "Łódź", "Wrocław", "Poznań", "Gdańsk",
           "Szczecin", "Katowice", "Lublin", "Białystok"],
    "ro": ["București", "Cluj-Napoca", "Timișoara", "Iași", "Constanța",
           "Craiova", "Brașov", "Galați", "Ploiești"],
    "sk": ["Bratislava", "Košice", "Prešov", "Žilina", "Banská Bystrica",
           "Nitra", "Trnava", "Trenčín"],
}

# ─── Dnevni bulk config ────────────────────────────────────────────────────────
# PRIMARNI VIR: Country-specific scraperji (herold.at, gelbeseiten.de, itd.)
#   → imajo EMAIL + TELEFON + detail-page enrichment → ~70-80% email coverage
# BACKUP VIR: EuroPages za Slovaško (ni country-specific scraperja)
#
# Kriterij za kvalifikacijo: lead MORA imeti email + NE sme imeti spletne strani
# Skupaj target: ~3450 leadov/dan
DAILY_BULK_CONFIG: list[dict] = [
    # ── SI — BiziScraper (bizi.si, detail-page enrichment, najboljša kakovost) ─
    {"source": "bizi", "country": "si", "industry": "plumber",     "limit": 100},
    {"source": "bizi", "country": "si", "industry": "electrician", "limit": 100},
    {"source": "bizi", "country": "si", "industry": "hair_salon",  "limit": 100},
    {"source": "bizi", "country": "si", "industry": "accounting",  "limit": 100},

    # ── HR — HrScraper (zlatne-stranice.hr) ───────────────────────────────────
    {"source": "hr", "country": "hr", "industry": "plumber",     "limit": 150},
    {"source": "hr", "country": "hr", "industry": "electrician", "limit": 150},
    {"source": "hr", "country": "hr", "industry": "restaurant",  "limit": 100},

    # ── AT — AtScraper (herold.at) ────────────────────────────────────────────
    {"source": "at", "country": "at", "industry": "plumber",     "limit": 150},
    {"source": "at", "country": "at", "industry": "electrician", "limit": 150},
    {"source": "at", "country": "at", "industry": "hair_salon",  "limit": 100},

    # ── DE — DeScraper (gelbeseiten.de) — največji trg ────────────────────────
    {"source": "de", "country": "de", "industry": "plumber",     "limit": 200},
    {"source": "de", "country": "de", "industry": "electrician", "limit": 200},
    {"source": "de", "country": "de", "industry": "hair_salon",  "limit": 150},
    {"source": "de", "country": "de", "industry": "accounting",  "limit": 150},

    # ── IT — ItScraper (paginebianche.it) ────────────────────────────────────
    {"source": "it", "country": "it", "industry": "plumber",     "limit": 150},
    {"source": "it", "country": "it", "industry": "electrician", "limit": 150},
    {"source": "it", "country": "it", "industry": "restaurant",  "limit": 100},

    # ── PL — PlScraper (panoramafirm.pl) ─────────────────────────────────────
    {"source": "pl", "country": "pl", "industry": "plumber",     "limit": 200},
    {"source": "pl", "country": "pl", "industry": "electrician", "limit": 150},
    {"source": "pl", "country": "pl", "industry": "hair_salon",  "limit": 100},

    # ── CZ — CzScraper ───────────────────────────────────────────────────────
    {"source": "cz", "country": "cz", "industry": "plumber",     "limit": 150},
    {"source": "cz", "country": "cz", "industry": "electrician", "limit": 100},

    # ── HU — HuScraper ───────────────────────────────────────────────────────
    {"source": "hu", "country": "hu", "industry": "plumber",     "limit": 150},
    {"source": "hu", "country": "hu", "industry": "electrician", "limit": 100},

    # ── RO — RoScraper ───────────────────────────────────────────────────────
    {"source": "ro", "country": "ro", "industry": "plumber",     "limit": 150},
    {"source": "ro", "country": "ro", "industry": "electrician", "limit": 100},

    # ── SK — EuroPages (ni country-specific scraperja za SK) ─────────────────
    {"source": "euro_pages", "country": "sk", "industry": "plumber",     "limit": 100},
    {"source": "euro_pages", "country": "sk", "industry": "electrician", "limit": 100},
]
