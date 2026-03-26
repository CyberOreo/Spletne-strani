"""Generira realistične testne leade za testiranje email pipeline-a."""
import sys
sys.path.insert(0, '.')

from src.database import init_db, insert_lead

TEST_LEADS = [
    {"company_name": "Vodoinstalater Horvat", "email": "horvat.voda@gmail.com", "phone": "+386 41 123 456", "address": "Mestni trg 5", "city": "Ljubljana", "country": "si", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Elektro Novak d.o.o.", "email": "info@elektro-novak.si", "phone": "+386 1 234 5678", "address": "Industrijska 12", "city": "Maribor", "country": "si", "website_url": "http://elektro-novak.si", "website_status": "outdated", "data_source": "test"},
    {"company_name": "Frizer Mojca", "email": "mojca.frizerstvo@gmail.com", "phone": "+386 40 987 654", "address": "Prešernova 3", "city": "Celje", "country": "si", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Auto Servis Kranjc", "email": "servis@kranjc-avto.si", "phone": "+386 51 111 222", "address": "Obmestna 45", "city": "Kranj", "country": "si", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Restavracija Pri Mami", "email": "rezervacije@pri-mami.si", "phone": "+386 1 345 6789", "address": "Stara cesta 7", "city": "Koper", "country": "si", "website_url": "http://pri-mami.si", "website_status": "outdated", "data_source": "test"},
    {"company_name": "Klempner Müller GmbH", "email": "info@mueller-klempner.de", "phone": "+49 30 1234567", "address": "Hauptstraße 22", "city": "Berlin", "country": "de", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Elektro Wagner", "email": "wagner.elektro@gmail.com", "phone": "+49 89 9876543", "address": "Bahnhofstr. 15", "city": "München", "country": "de", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Friseur Schneider", "email": "schneider.friseur@web.de", "phone": "+49 40 555 1234", "address": "Marktplatz 8", "city": "Hamburg", "country": "de", "website_url": "http://friseur-schneider.de", "website_status": "outdated", "data_source": "test"},
    {"company_name": "Idraulico Rossi", "email": "rossi.idraulico@libero.it", "phone": "+39 06 1234567", "address": "Via Roma 14", "city": "Roma", "country": "it", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Ristorante Da Mario", "email": "info@damario.it", "phone": "+39 02 9876543", "address": "Corso Buenos Aires 5", "city": "Milano", "country": "it", "website_url": "http://damario.it", "website_status": "outdated", "data_source": "test"},
    {"company_name": "Vodoinstalater Kovač", "email": "kovac.voda@gmail.com", "phone": "+385 91 234 5678", "address": "Ilica 55", "city": "Zagreb", "country": "hr", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Auto Servis Split", "email": "info@autoservis-split.hr", "phone": "+385 21 333 444", "address": "Spinutska 12", "city": "Split", "country": "hr", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Installateur Bauer", "email": "bauer.installateur@gmx.at", "phone": "+43 1 2345678", "address": "Mariahilfer Str. 45", "city": "Wien", "country": "at", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Elektriker Huber", "email": "huber.elektro@aon.at", "phone": "+43 316 123456", "address": "Hauptplatz 3", "city": "Graz", "country": "at", "website_url": "http://huber-elektro.at", "website_status": "outdated", "data_source": "test"},
    {"company_name": "Instalatér Novák", "email": "novak.instalater@seznam.cz", "phone": "+420 776 123 456", "address": "Václavské nám. 12", "city": "Praha", "country": "cz", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Kaderník Jana", "email": "jana.kadernik@gmail.com", "phone": "+421 905 123 456", "address": "Obchodná 5", "city": "Bratislava", "country": "sk", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Vízszerelő Kiss", "email": "kiss.vizszerelo@freemail.hu", "phone": "+36 1 234 5678", "address": "Andrássy út 22", "city": "Budapest", "country": "hu", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Hydraulik Kowalski", "email": "kowalski.hydraulik@wp.pl", "phone": "+48 22 123 4567", "address": "ul. Marszałkowska 15", "city": "Warszawa", "country": "pl", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Instalator Popescu", "email": "popescu.instalatii@gmail.com", "phone": "+40 21 234 5678", "address": "Calea Victoriei 45", "city": "București", "country": "ro", "website_url": None, "website_status": "none", "data_source": "test"},
    {"company_name": "Zobozdravnik Zupan", "email": "zupan.zobozdr@gmail.com", "phone": "+386 1 456 7890", "address": "Gosposvetska 8", "city": "Ljubljana", "country": "si", "website_url": None, "website_status": "none", "data_source": "test"},
]

init_db()
inserted = 0
for lead in TEST_LEADS:
    if insert_lead(lead):
        inserted += 1
        print(f"  + {lead['company_name']} ({lead['country'].upper()}) — {lead['email']}")

print(f"\nDodano {inserted}/{len(TEST_LEADS)} testnih leadov v bazo.")
print("Zdaj v aplikaciji: Kampanja → Kvalificiraj → Generiraj emaile → Pošlji (test)")
