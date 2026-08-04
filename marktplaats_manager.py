#!/usr/bin/env python3
"""
Marktplaats Product Manager - Registratie & voorraadbeheer

Vervangt de Google Form + Google Sheets-combinatie door een lokale app.
Deelt exact dezelfde kolomstructuur (A-X) als auto_marktplaats.py, zodat
beide apps dezelfde Google Sheet (of lokale XML) kunnen gebruiken.

Tab 1 "Registreren"  - nieuw product invoeren, artikelnummer + map +
                        omschrijving.txt + barcode genereren
Tab 2 "Overzicht"     - alle producten bekijken/bewerken/verwijderen,
                        markeren als verkocht, omzet-overzicht
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
import os
import sys
import json
import shutil
import subprocess
import datetime

# ============================================
# KOLOMSTRUCTUUR (gedeeld met auto_marktplaats.py)
# ============================================
# Let op: deze volgorde is bewust identiek aan wat auto_marktplaats.py
# leest (col A=0 .. X=23). Nieuwe velden staan in de kolommen die
# auto_marktplaats.py niet gebruikt (N t/m W), zodat beide apps dezelfde
# sheet/xml kunnen delen zonder conflicten.
COLUMNS = [
    "artikelnummer",      # A (0)  - ook gebruikt door auto_marktplaats.py
    "titel",               # B (1)  - ook gebruikt door auto_marktplaats.py
    "categorie",            # C (2)  - ook gebruikt door auto_marktplaats.py
    "omschrijving",          # D (3)  - ook gebruikt door auto_marktplaats.py
    "online",                 # E (4)  - "ja"/"nee", was "reserve"
    "lengte",                  # F (5)  - ook gebruikt door auto_marktplaats.py
    "breedte",                  # G (6)  - ook gebruikt door auto_marktplaats.py
    "hoogte",                     # H (7)  - ook gebruikt door auto_marktplaats.py
    "gewicht",                     # I (8)  - ook gebruikt door auto_marktplaats.py
    "conditie",                     # J (9)  - ook gebruikt door auto_marktplaats.py
    "staat_details",                 # K (10) - ook gebruikt door auto_marktplaats.py (als "Schades")
    "waarde_min",                     # L (11) - ook gebruikt door auto_marktplaats.py (als "Waarde")
    "waarde_max",                      # M (12) - ook gebruikt door auto_marktplaats.py (waarde-extra)
    "vraagprijs",                       # N (13)
    "aanmaakdatum",                      # O (14)
    "tijdsperiode",                       # P (15)
    "opslaglocatie",                       # Q (16)
    "sublocatie",                           # R (17)
    "rij",                                   # S (18)
    "folder_locatie",                         # T (19)
    "verkocht",                                 # U (20) - "ja"/"nee"
    "verkoopprijs",                              # V (21)
    "verkoopdatum",                               # W (22)
    "algemene_voorwaarden",                        # X (23) - ook gebruikt door auto_marktplaats.py
    "advertentie_url",                              # Y (24) - nieuw, alleen ingevuld als online=ja
    "leverwijze",                                     # Z (25) - "ophalen" of "verzenden"
    "klant_naam",                                      # AA (26) - Marktplaatsnaam koper
    "klant_telefoon",                                    # AB (27) - alleen bij ophalen
    "klant_email",                                        # AC (28) - alleen bij ophalen
    "ophaal_afspraak",                                     # AD (29) - alleen bij ophalen
    "track_trace",                                          # AE (30) - alleen bij verzenden, optioneel
]
COL = {name: idx for idx, name in enumerate(COLUMNS)}

CONDITIES = ["Nieuwstaat", "Zo goed als nieuw", "Gebruikt", "Beschadigd"]

STAAT_DETAILS = {
    "Nieuwstaat": ["In verpakking", "Zonder verpakking", "Beschadigde verpakking"],
    "Zo goed als nieuw": ["Lichte gebruikerssporen", "Ongebruikt", "Goede staat"],
    "Gebruikt": ["Gebruikerssporen", "Kleine schades zoals krassen en vlekken", "Mogelijk ontbrekende onderdelen"],
    "Beschadigd": ["Ontbrekende onderdelen", "Zware gebruikerssporen", "Opvallende krassen, sporen en vlekken", "Werking onbekend"],
}

DEFAULT_CATEGORIEEN = [
    "Huishouden", "Elektra/Elektronica", "Meubels", "Verlichting", "Speelgoed",
    "Kleding/Textiel", "Boeken/Media", "Sieraden/Accessoires", "Sport & Vrije tijd",
    "Tuin & Buiten", "Gereedschap", "Servies/Keuken", "Kunst & Decoratie", "Overig",
]

DEFAULT_TIJDSPERIODES = [
    "Antiek (100+ jaar)", "Vintage (20-100 jaar)", "Retro", "Klassiek",
    "Modern/Hedendaags", "Onbekend",
]

MAX_TITEL_LENGTE = 60

TEXTVIEW_CSS = b"""
textview {
    border: 1px solid alpha(@borders, 0.6);
    border-radius: 4px;
}
textview text {
    /* Vaste, thema-onafhankelijke kleur i.p.v. @theme_base_color - die
       bleek in dit thema hetzelfde te zijn als de vensterachtergrond,
       waardoor er geen zichtbaar contrast was. Pas deze hex gerust aan
       als 'ie op jouw systeem nog niet precies goed oogt. */
    background-color: #3a3a3a;
    color: #e8e8e8;
    padding: 5px;
}
"""


def apply_css():
    provider = Gtk.CssProvider()
    provider.load_from_data(TEXTVIEW_CSS)
    screen = Gdk.Screen.get_default()
    Gtk.StyleContext.add_provider_for_screen(
        screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

ALGEMENE_VOORWAARDEN = """Algemene voorwaarden: 
Wij zijn een kleine kringloopwinkel en proberen z.s.m. te reageren. Soms is het heel druk in de winkel en lukt dit niet dezelfde dag. 

De richtprijs van een product baseren wij op bestaand aanbod en staat van het artikel met minimum/maximum schatting. 

Graag alleen biedingen plaatsen via de bied optie van marktplaats. Advertenties laten we vaak minimaal 2 weken online staan voordat we akkoord gaan met het hoogste aannemelijke bod. Bedankt voor uw begrip 🙏🏻 

Als wij akkoord gaan met uw bod, reserveren wij het product maximaal een week voor u. U kunt het product ophalen en afrekenen in onze winkel.

U bent altijd welkom in onze winkel, maar langskomen voor de Marktplaats advertenties zonder afspraak wordt niet op prijs gesteld. Dit gaat altijd via specifieke medewerkers. 

Let op: Bij ophalen in de winkel vervalt het herroepingsrecht en kun je het product ter plekke testen. 

Ons adres:
Kringloop HerNieuw 
Willem Beukelszstraat 6B 
3261 LV Oud-Beijerland

Openingstijden Kringloop: 
Dinsdag t/m vrijdag 10.00 – 16.00 uur 
Zaterdag 10:00-13:00 uur 
Zondag en maandag Gesloten"""


def config_dir():
    return os.path.dirname(os.path.abspath(__file__))


def config_path():
    return os.path.join(config_dir(), "productmanager_config.json")


# ============================================
# CONFIGURATIE
# ============================================
class ConfigManager:
    DEFAULTS = {
        "storage_backend": "xml",  # "xml" of "sheets" - precies EEN actief tegelijk
        "xml_path": os.path.join(config_dir(), "producten.xml"),
        "sheets": {
            "sheet_url": "",
            "credentials_file": os.path.join(config_dir(), "credentials.json"),
        },
        "base_folder": os.path.expanduser("~/Documents/MarktplaatsProgramma/Producten"),
        "categorieen": DEFAULT_CATEGORIEEN,
        "tijdsperiodes": DEFAULT_TIJDSPERIODES,
        # opslaglocatie_codes: {weergavenaam: 1-teken-code}
        "opslaglocatie_codes": {"Locatie A": "A", "Locatie B": "B"},
        "sublocatie_codes": {"Sublocatie 1": "1", "Sublocatie 2": "2"},
        "rij_codes": {"Rij 1": "1", "Rij 2": "2"},
        "volgnummers": {},  # {prefix: laatst_gebruikte_nummer}
        "printer": {
            "enabled": False,
            "print_method": "cups",
            "printer_name": "",
            "brother_ql_model": "QL-500",
            "brother_ql_label": "62",
            "brother_ql_identifier": "",
        },
        "barcode": {
            # Afgestemd op 62mm continue labelrol (bv. Brother QL-serie).
            # Pas gerust aan en test opnieuw - dit bepaalt hoe breed/hoog
            # de barcode wordt EN hoeveel label er wordt "uitgespuugd".
            "module_width_mm": 0.4,   # dikte van elke streep - hoger = breder totaal + beter leesbaar
            "module_height_mm": 7.0,  # hoogte van de streepjes zelf (python-barcode default is 15mm)
            "quiet_zone_mm": 2.0,     # witruimte links/rechts (kleiner = meer van de 62mm benut)
        },
    }

    def __init__(self):
        self.path = config_path()
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                merged = json.loads(json.dumps(self.DEFAULTS))  # deep copy
                merged.update(loaded)
                return merged
            except Exception:
                pass
        return json.loads(json.dumps(self.DEFAULTS))

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()


# ============================================
# OPSLAG-BACKENDS (XML of Google Sheets, precies 1 actief)
# ============================================
class StorageBackend:
    def load_products(self):
        raise NotImplementedError

    def add_product(self, product):
        raise NotImplementedError

    def update_product(self, artikelnummer, product):
        raise NotImplementedError

    def delete_product(self, artikelnummer):
        raise NotImplementedError


class XmlBackend(StorageBackend):
    def __init__(self, xml_path):
        self.xml_path = xml_path

    def _ensure_file(self):
        if not os.path.exists(self.xml_path):
            import xml.etree.ElementTree as ET
            root = ET.Element("producten")
            tree = ET.ElementTree(root)
            os.makedirs(os.path.dirname(self.xml_path), exist_ok=True)
            tree.write(self.xml_path, encoding="utf-8", xml_declaration=True)

    def load_products(self):
        import xml.etree.ElementTree as ET
        self._ensure_file()
        tree = ET.parse(self.xml_path)
        root = tree.getroot()
        products = []
        for prod_el in root.findall("product"):
            product = {}
            for col in COLUMNS:
                el = prod_el.find(col)
                product[col] = el.text if el is not None and el.text else ""
            products.append(product)
        return products

    def _write_all(self, products):
        import xml.etree.ElementTree as ET
        root = ET.Element("producten")
        for product in products:
            prod_el = ET.SubElement(root, "product")
            for col in COLUMNS:
                el = ET.SubElement(prod_el, col)
                el.text = str(product.get(col, ""))
        tree = ET.ElementTree(root)
        os.makedirs(os.path.dirname(self.xml_path), exist_ok=True)
        tree.write(self.xml_path, encoding="utf-8", xml_declaration=True)

    def add_product(self, product):
        products = self.load_products()
        products.append(product)
        self._write_all(products)

    def update_product(self, artikelnummer, product):
        products = self.load_products()
        for i, p in enumerate(products):
            if p.get("artikelnummer") == artikelnummer:
                products[i] = product
                break
        self._write_all(products)

    def delete_product(self, artikelnummer):
        products = self.load_products()
        products = [p for p in products if p.get("artikelnummer") != artikelnummer]
        self._write_all(products)


class SheetsBackend(StorageBackend):
    def __init__(self, sheet_url, credentials_file):
        self.sheet_url = sheet_url
        self.credentials_file = credentials_file
        self._client = None
        self._worksheet = None

    def _connect(self):
        if self._worksheet is not None:
            return self._worksheet
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(self.credentials_file, scopes=scopes)
        self._client = gspread.authorize(creds)
        sheet = self._client.open_by_url(self.sheet_url)
        self._worksheet = sheet.get_worksheet(0)
        return self._worksheet

    def load_products(self):
        ws = self._connect()
        all_values = ws.get_all_values()
        products = []
        for row in all_values[1:]:
            if not row or not row[0]:
                continue
            product = {}
            for i, col in enumerate(COLUMNS):
                product[col] = row[i] if i < len(row) else ""
            products.append(product)
        return products

    def _product_to_row(self, product):
        return [str(product.get(col, "")) for col in COLUMNS]

    def add_product(self, product):
        ws = self._connect()
        ws.append_row(self._product_to_row(product))

    def _find_row_number(self, ws, artikelnummer):
        all_values = ws.get_all_values()
        for idx, row in enumerate(all_values, start=1):
            if row and row[0] == artikelnummer:
                return idx
        return None

    def update_product(self, artikelnummer, product):
        ws = self._connect()
        row_num = self._find_row_number(ws, artikelnummer)
        if row_num is None:
            self.add_product(product)
            return
        row = self._product_to_row(product)
        ws.update(f"A{row_num}:{chr(65 + len(COLUMNS) - 1)}{row_num}", [row])

    def delete_product(self, artikelnummer):
        ws = self._connect()
        row_num = self._find_row_number(ws, artikelnummer)
        if row_num is not None:
            ws.delete_rows(row_num)


def get_backend(config):
    backend = config.get("storage_backend", "xml")
    if backend == "sheets":
        sheets_cfg = config.get("sheets", {})
        return SheetsBackend(sheets_cfg.get("sheet_url", ""), sheets_cfg.get("credentials_file", ""))
    return XmlBackend(config.get("xml_path"))


# ============================================
# HELPERS: artikelnummer, map, txt, barcode
# ============================================
def generate_artikelnummer(config, storage, opslaglocatie_code, sublocatie_code, rij_code):
    """Bouwt het artikelnummer op als: locatie-prefix(3) + dag+maand(4) + volgnummer(2).
    Bijv. A51 + 0108 (1 augustus) + 03 = A51010803.
    Het volgnummer (01-99) telt per locatie-prefix EN per dag - begint dus
    elke dag vanzelf weer bij 01, ook voor dezelfde locatie."""
    prefix = f"{opslaglocatie_code}{sublocatie_code}{rij_code}"
    datum_deel = datetime.date.today().strftime("%d%m")  # DDMM, 4 cijfers
    teller_sleutel = f"{prefix}{datum_deel}"
    
    volgnummers = config.get("volgnummers", {})
    laatste = volgnummers.get(teller_sleutel, 0)
    
    # Kruis-check met bestaande data, voor het geval de teller (config.json)
    # niet meer synchroon loopt met de opslag (bv. na handmatige XML-edit
    # of een andere computer die dezelfde sheet gebruikt).
    try:
        bestaande = storage.load_products()
        for p in bestaande:
            nr = p.get("artikelnummer", "")
            if nr.startswith(teller_sleutel) and len(nr) == len(teller_sleutel) + 2:
                try:
                    val = int(nr[len(teller_sleutel):])
                    laatste = max(laatste, val)
                except ValueError:
                    pass
    except Exception:
        pass
    
    nieuw_nummer = laatste + 1
    if nieuw_nummer > 99:
        raise ValueError(
            f"Maximaal 99 artikelen per dag bereikt voor locatie '{prefix}' op {datum_deel}."
        )
    volgnummers[teller_sleutel] = nieuw_nummer
    config.set("volgnummers", volgnummers)
    
    return f"{teller_sleutel}{nieuw_nummer:02d}"


def build_txt_beschrijving(product):
    """Genereert omschrijving.txt in het mapje van het artikelnummer.
    Dit is BEWUST exact hetzelfde formaat als de advertentietekst die
    auto_marktplaats.py plaatst (zie build_description() daar) - deze
    .txt is de enige plek waar de opmaak wordt beheerd; auto_marktplaats.py
    leest 'm rechtstreeks in plaats van de tekst zelf opnieuw op te bouwen."""
    parts = []
    
    titel = product.get("titel", "")
    if titel:
        parts.append(titel)
    
    omschrijving = product.get("omschrijving", "")
    if omschrijving:
        parts.append(omschrijving)
    
    specs = []
    lengte = product.get("lengte", "")
    breedte = product.get("breedte", "")
    hoogte = product.get("hoogte", "")
    gewicht = product.get("gewicht", "")
    if lengte or breedte or hoogte or gewicht:
        dims = [f"{x}cm" for x in (lengte, breedte, hoogte) if x]
        line = f"* Afmeting (LxBxH & G): {' x '.join(dims)}"
        if gewicht:
            line += f" & {gewicht} kg"
        specs.append(line)
    if product.get("conditie"):
        specs.append(f"* Conditie/Staat: {product.get('conditie')}")
    if product.get("staat_details"):
        specs.append(f"* Schades: {product.get('staat_details')}")
    waarde_min = product.get("waarde_min", "")
    waarde_max = product.get("waarde_max", "")
    if waarde_min:
        line = f"* Waarde: {waarde_min}"
        if waarde_max:
            line += f" ~{waarde_max}"
        specs.append(line)
    if product.get("artikelnummer"):
        specs.append(f"* Artikelnummer: {product.get('artikelnummer')}")
    if specs:
        parts.append("\n".join(specs))
    
    voorwaarden = product.get("algemene_voorwaarden") or ALGEMENE_VOORWAARDEN
    parts.append(voorwaarden)
    
    return "\n\n".join(parts)


def maak_product_map(config, product):
    """Maakt (of hergebruikt) de map voor dit artikelnummer, identiek aan
    hoe marktplaats_manager.py de map benoemt (base_folder/artikelnummer),
    en schrijft de omschrijving.txt erin."""
    base_folder = config.get("base_folder")
    artikelnummer = product["artikelnummer"]
    folder = os.path.join(base_folder, artikelnummer)
    bestond_al = os.path.exists(folder)
    os.makedirs(folder, exist_ok=True)
    
    txt_path = os.path.join(folder, "omschrijving.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(build_txt_beschrijving(product))
    
    return folder, bestond_al


def genereer_barcode(artikelnummer, output_folder, barcode_config=None):
    """Genereert een Code128-barcode-afbeelding met het artikelnummer.
    Vereist: pip install python-barcode"""
    try:
        import barcode
        from barcode.writer import ImageWriter
        from PIL import Image as PILImage
    except ImportError:
        raise RuntimeError(
            "python-barcode is niet geïnstalleerd. Installeer met:\n"
            "pip install python-barcode --break-system-packages"
        )
    
    # Compatibiliteits-fix: Pillow 10+ heeft Image.ANTIALIAS verwijderd
    # (vervangen door Image.LANCZOS), maar python-barcode's ImageWriter
    # verwijst er intern nog naar. Zonder deze patch crasht het genereren
    # met "module 'PIL.Image' has no attribute 'ANTIALIAS'".
    if not hasattr(PILImage, "ANTIALIAS"):
        PILImage.ANTIALIAS = PILImage.LANCZOS
    
    barcode_config = barcode_config or {}
    writer_options = {
        "module_width": barcode_config.get("module_width_mm", 0.4),
        "module_height": barcode_config.get("module_height_mm", 7.0),
        "quiet_zone": barcode_config.get("quiet_zone_mm", 2.0),
        "font_size": 8,
        "text_distance": 3.0,
        "dpi": 300,
    }
    code128 = barcode.get("code128", artikelnummer, writer=ImageWriter())
    output_path = os.path.join(output_folder, f"{artikelnummer}_barcode")
    saved_path = code128.save(output_path, options=writer_options)
    return saved_path


def print_barcode(image_path, printer_config):
    """Print de barcode-afbeelding.
    
    Twee methoden:
    - 'brother_ql': praat rechtstreeks (via USB) met een Brother QL-serie
      printer met de brother_ql-library. Dit is de juiste aanpak voor een
      continue labelrol: de library berekent zelf de correcte labellengte
      op basis van de afbeelding, in plaats van te leunen op een vaste
      paginagrootte uit een CUPS-driver (wat foutmeldingen/knipperen kan
      geven als de gevraagde afmeting niet in de driver's vaste lijst zit).
    - 'cups': gewone lp-print, GEEN custom paginagrootte (dat gaf eerder
      een media-mismatch-fout op de QL-500). Werkt op de meeste
      printers, maar de labellengte is dan afhankelijk van de standaard-
      pagina-instelling van de driver.
    """
    methode = printer_config.get("print_method", "cups")
    
    if methode == "brother_ql":
        _print_barcode_brother_ql(image_path, printer_config)
    else:
        _print_barcode_cups(image_path, printer_config.get("printer_name", ""))


def _print_barcode_cups(image_path, printer_name):
    cmd = ["lp"]
    if printer_name:
        cmd += ["-d", printer_name]
    cmd += [image_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="ignore"))


def _print_barcode_brother_ql(image_path, printer_config):
    try:
        from brother_ql.conversion import convert
        from brother_ql.backends.helpers import send
        from brother_ql.raster import BrotherQLRaster
    except ImportError:
        raise RuntimeError(
            "brother_ql is niet geïnstalleerd. Installeer met:\n"
            "pip install brother_ql --break-system-packages"
        )
    
    model = printer_config.get("brother_ql_model", "QL-500")
    label_size = printer_config.get("brother_ql_label", "62")  # 62mm continu
    identifier = printer_config.get("brother_ql_identifier", "")
    if not identifier:
        raise RuntimeError(
            "Geen USB-identifier ingesteld voor brother_ql.\n"
            "Vind 'm met: python3 -m brother_ql discover"
        )
    
    from PIL import Image
    with Image.open(image_path) as img:
        qlr = BrotherQLRaster(model)
        qlr.exception_on_warning = True
        instructions = convert(
            qlr=qlr,
            images=[img],
            label=label_size,
            rotate="0",
            threshold=70.0,
            dither=False,
            compress=False,
            red=False,
            cut=True,
        )
        send(instructions=instructions, printer_identifier=identifier, backend_identifier="pyusb", blocking=True)


def get_cups_printers():
    """Haalt beschikbare CUPS-printers op (Linux)."""
    try:
        result = subprocess.run(["lpstat", "-p"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        printers = []
        for line in result.stdout.decode("utf-8", errors="ignore").splitlines():
            if line.startswith("printer "):
                printers.append(line.split()[1])
        return printers
    except Exception:
        return []


# ============================================
# INSTELLINGEN-DIALOOG
# ============================================
class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent, config):
        super().__init__(title="Instellingen", transient_for=parent, flags=0)
        self.config = config
        self.set_default_size(560, 640)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        
        box = self.get_content_area()
        box.set_spacing(10)
        box.set_border_width(15)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.pack_start(scrolled, True, True, 0)
        
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        inner.set_border_width(5)
        scrolled.add(inner)
        
        # --- Opslagmethode ---
        inner.pack_start(self._section_label("Opslagmethode (kies er één)"), False, False, 0)
        
        self.backend_combo = Gtk.ComboBoxText()
        self.backend_combo.append("xml", "Lokaal XML-bestand")
        self.backend_combo.append("sheets", "Google Sheets")
        self.backend_combo.set_active_id(config.get("storage_backend", "xml"))
        inner.pack_start(self.backend_combo, False, False, 0)
        
        warning = Gtk.Label()
        warning.set_markup("<small><i>⚠️ Zorg dat deze keuze overeenkomt met wat auto_marktplaats.py gebruikt - beide apps moeten dezelfde opslag lezen.</i></small>")
        warning.set_xalign(0)
        warning.set_line_wrap(True)
        inner.pack_start(warning, False, False, 0)
        
        inner.pack_start(Gtk.Label(label="XML-bestandspad:"), False, False, 0)
        self.xml_path_entry = Gtk.Entry()
        self.xml_path_entry.set_text(config.get("xml_path", ""))
        inner.pack_start(self.xml_path_entry, False, False, 0)
        
        inner.pack_start(Gtk.Label(label="Google Sheets URL:"), False, False, 0)
        self.sheet_url_entry = Gtk.Entry()
        self.sheet_url_entry.set_text(config.get("sheets", {}).get("sheet_url", ""))
        inner.pack_start(self.sheet_url_entry, False, False, 0)
        
        inner.pack_start(Gtk.Label(label="credentials.json pad:"), False, False, 0)
        self.creds_entry = Gtk.Entry()
        self.creds_entry.set_text(config.get("sheets", {}).get("credentials_file", ""))
        inner.pack_start(self.creds_entry, False, False, 0)
        
        inner.pack_start(Gtk.Separator(), False, False, 5)
        
        # --- Basis-map ---
        inner.pack_start(self._section_label("Basismap voor productmappen"), False, False, 0)
        base_warn = Gtk.Label()
        base_warn.set_markup("<small><i>⚠️ Zorg dat dit exact dezelfde basismap is als in marktplaats_manager.py, anders maakt die een nieuwe/andere map aan voor hetzelfde artikelnummer.</i></small>")
        base_warn.set_xalign(0)
        base_warn.set_line_wrap(True)
        inner.pack_start(base_warn, False, False, 0)
        
        self.base_folder_entry = Gtk.Entry()
        self.base_folder_entry.set_text(config.get("base_folder", ""))
        inner.pack_start(self.base_folder_entry, False, False, 0)
        
        inner.pack_start(Gtk.Separator(), False, False, 5)
        
        # --- Categorieën ---
        inner.pack_start(self._section_label("Categorieën (één per regel)"), False, False, 0)
        self.categorieen_view = Gtk.TextView()
        self.categorieen_view.get_buffer().set_text("\n".join(config.get("categorieen", DEFAULT_CATEGORIEEN)))
        cat_scroll = Gtk.ScrolledWindow()
        cat_scroll.set_size_request(-1, 100)
        cat_scroll.add(self.categorieen_view)
        inner.pack_start(cat_scroll, False, False, 0)
        
        # --- Tijdsperiodes ---
        inner.pack_start(self._section_label("Tijdsperiodes (één per regel)"), False, False, 0)
        self.tijdsperiodes_view = Gtk.TextView()
        self.tijdsperiodes_view.get_buffer().set_text("\n".join(config.get("tijdsperiodes", DEFAULT_TIJDSPERIODES)))
        tp_scroll = Gtk.ScrolledWindow()
        tp_scroll.set_size_request(-1, 100)
        tp_scroll.add(self.tijdsperiodes_view)
        inner.pack_start(tp_scroll, False, False, 0)
        
        inner.pack_start(Gtk.Separator(), False, False, 5)
        
        # --- Opslaglocatie-codes ---
        inner.pack_start(self._section_label("Opslaglocatie-codes (naam=code, 1 teken, één per regel)"), False, False, 0)
        loc_hint = Gtk.Label()
        loc_hint.set_markup("<small><i>De code van Opslaglocatie + Sublocatie + Rij vormt samen de eerste 3 tekens van het artikelnummer. Bijv: Zolder=Z</i></small>")
        loc_hint.set_xalign(0)
        loc_hint.set_line_wrap(True)
        inner.pack_start(loc_hint, False, False, 0)
        
        self.opslaglocatie_view = Gtk.TextView()
        self.opslaglocatie_view.get_buffer().set_text(
            "\n".join(f"{k}={v}" for k, v in config.get("opslaglocatie_codes", {}).items())
        )
        loc_scroll = Gtk.ScrolledWindow()
        loc_scroll.set_size_request(-1, 80)
        loc_scroll.add(self.opslaglocatie_view)
        inner.pack_start(loc_scroll, False, False, 0)
        
        inner.pack_start(Gtk.Label(label="Sublocatie-codes (naam=code):"), False, False, 0)
        self.sublocatie_view = Gtk.TextView()
        self.sublocatie_view.get_buffer().set_text(
            "\n".join(f"{k}={v}" for k, v in config.get("sublocatie_codes", {}).items())
        )
        sub_scroll = Gtk.ScrolledWindow()
        sub_scroll.set_size_request(-1, 80)
        sub_scroll.add(self.sublocatie_view)
        inner.pack_start(sub_scroll, False, False, 0)
        
        inner.pack_start(Gtk.Label(label="Rij-codes (naam=code):"), False, False, 0)
        self.rij_view = Gtk.TextView()
        self.rij_view.get_buffer().set_text(
            "\n".join(f"{k}={v}" for k, v in config.get("rij_codes", {}).items())
        )
        rij_scroll = Gtk.ScrolledWindow()
        rij_scroll.set_size_request(-1, 80)
        rij_scroll.add(self.rij_view)
        inner.pack_start(rij_scroll, False, False, 0)
        
        inner.pack_start(Gtk.Separator(), False, False, 5)
        
        # --- Labelprinter ---
        inner.pack_start(self._section_label("Labelprinter (barcode)"), False, False, 0)
        printer_hint = Gtk.Label()
        printer_hint.set_markup("<small><i>Indien uitgeschakeld wordt alleen een barcode-afbeelding opgeslagen in de productmap.</i></small>")
        printer_hint.set_xalign(0)
        printer_hint.set_line_wrap(True)
        inner.pack_start(printer_hint, False, False, 0)
        
        self.printer_enabled_check = Gtk.CheckButton(label="Direct printen inschakelen")
        self.printer_enabled_check.set_active(config.get("printer", {}).get("enabled", False))
        inner.pack_start(self.printer_enabled_check, False, False, 0)
        
        printer_cfg = config.get("printer", {})
        
        method_row = Gtk.Box(spacing=5)
        method_row.pack_start(Gtk.Label(label="Methode:"), False, False, 0)
        self.print_method_combo = Gtk.ComboBoxText()
        self.print_method_combo.append("cups", "CUPS (lp) - algemeen")
        self.print_method_combo.append("brother_ql", "Brother QL direct via USB (brother_ql)")
        self.print_method_combo.set_active_id(printer_cfg.get("print_method", "cups"))
        self.print_method_combo.connect("changed", self._on_print_method_changed)
        method_row.pack_start(self.print_method_combo, False, False, 0)
        inner.pack_start(method_row, False, False, 0)
        
        # CUPS-specifieke velden
        self.cups_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        inner.pack_start(self.cups_box, False, False, 0)
        
        printer_row = Gtk.Box(spacing=5)
        printer_row.pack_start(Gtk.Label(label="Printer:"), False, False, 0)
        self.printer_combo = Gtk.ComboBoxText()
        for p in get_cups_printers():
            self.printer_combo.append_text(p)
        huidige_printer = printer_cfg.get("printer_name", "")
        if huidige_printer:
            self.printer_combo.prepend_text(huidige_printer)
        self.printer_combo.set_active(0)
        printer_row.pack_start(self.printer_combo, True, True, 0)
        
        refresh_btn = Gtk.Button(label="🔄")
        refresh_btn.connect("clicked", self._refresh_printers)
        printer_row.pack_start(refresh_btn, False, False, 0)
        
        self.cups_box.pack_start(printer_row, False, False, 0)
        cups_hint = Gtk.Label()
        cups_hint.set_markup("<small><i>⚠️ Op de QL-500 gaf een aangepaste paginagrootte een media-mismatch-fout (snel knipperend lampje). Gebruik hiervoor liever de brother_ql-methode hieronder.</i></small>")
        cups_hint.set_xalign(0)
        cups_hint.set_line_wrap(True)
        self.cups_box.pack_start(cups_hint, False, False, 0)
        
        # brother_ql-specifieke velden
        self.brother_ql_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        inner.pack_start(self.brother_ql_box, False, False, 0)
        
        bq_grid = Gtk.Grid()
        bq_grid.set_column_spacing(10)
        bq_grid.set_row_spacing(5)
        self.brother_ql_box.pack_start(bq_grid, False, False, 0)
        
        bq_grid.attach(Gtk.Label(label="Model:", xalign=0), 0, 0, 1, 1)
        self.bq_model_entry = Gtk.Entry()
        self.bq_model_entry.set_text(printer_cfg.get("brother_ql_model", "QL-500"))
        bq_grid.attach(self.bq_model_entry, 1, 0, 1, 1)
        
        bq_grid.attach(Gtk.Label(label="Labelformaat:", xalign=0), 0, 1, 1, 1)
        self.bq_label_entry = Gtk.Entry()
        self.bq_label_entry.set_text(printer_cfg.get("brother_ql_label", "62"))
        bq_grid.attach(self.bq_label_entry, 1, 1, 1, 1)
        bq_label_hint = Gtk.Label()
        bq_label_hint.set_markup("<small><i>'62' = 62mm continue rol</i></small>")
        bq_label_hint.set_xalign(0)
        bq_grid.attach(bq_label_hint, 2, 1, 1, 1)
        
        bq_grid.attach(Gtk.Label(label="USB-identifier:", xalign=0), 0, 2, 1, 1)
        self.bq_identifier_entry = Gtk.Entry()
        self.bq_identifier_entry.set_text(printer_cfg.get("brother_ql_identifier", ""))
        self.bq_identifier_entry.set_placeholder_text("bijv. usb://0x04f9:0x2015/000M6Z401370")
        bq_grid.attach(self.bq_identifier_entry, 1, 2, 1, 1)
        
        bq_find_btn = Gtk.Button(label="🔍 Zoek printer")
        bq_find_btn.connect("clicked", self._discover_brother_ql)
        self.brother_ql_box.pack_start(bq_find_btn, False, False, 0)
        
        self._on_print_method_changed(self.print_method_combo)
        

        # --- Barcode-afmetingen ---
        size_hint = Gtk.Label()
        size_hint.set_markup(
            "<small><i>Voor labelprinters (bv. Brother QL op 62mm rol): "
            "de paginagrootte bij het printen wordt automatisch gelijk gezet aan "
            "de afbeelding, dus deze instellingen bepalen direct hoeveel label "
            "er wordt uitgevoerd.</i></small>"
        )
        size_hint.set_xalign(0)
        size_hint.set_line_wrap(True)
        size_hint.set_margin_top(8)
        inner.pack_start(size_hint, False, False, 0)
        
        barcode_cfg = config.get("barcode", {})
        
        size_grid = Gtk.Grid()
        size_grid.set_column_spacing(10)
        size_grid.set_row_spacing(5)
        inner.pack_start(size_grid, False, False, 0)
        
        size_grid.attach(Gtk.Label(label="Streepdikte (mm):", xalign=0), 0, 0, 1, 1)
        self.module_width_entry = Gtk.Entry()
        self.module_width_entry.set_text(str(barcode_cfg.get("module_width_mm", 0.4)))
        size_grid.attach(self.module_width_entry, 1, 0, 1, 1)
        width_hint = Gtk.Label()
        width_hint.set_markup("<small><i>hoger = breder totaal + beter leesbaar</i></small>")
        width_hint.set_xalign(0)
        size_grid.attach(width_hint, 2, 0, 1, 1)
        
        size_grid.attach(Gtk.Label(label="Streephoogte (mm):", xalign=0), 0, 1, 1, 1)
        self.module_height_entry = Gtk.Entry()
        self.module_height_entry.set_text(str(barcode_cfg.get("module_height_mm", 7.0)))
        size_grid.attach(self.module_height_entry, 1, 1, 1, 1)
        height_hint = Gtk.Label()
        height_hint.set_markup("<small><i>standaard (python-barcode) is 15mm</i></small>")
        height_hint.set_xalign(0)
        size_grid.attach(height_hint, 2, 1, 1, 1)
        
        size_grid.attach(Gtk.Label(label="Marge/quiet zone (mm):", xalign=0), 0, 2, 1, 1)
        self.quiet_zone_entry = Gtk.Entry()
        self.quiet_zone_entry.set_text(str(barcode_cfg.get("quiet_zone_mm", 2.0)))
        size_grid.attach(self.quiet_zone_entry, 1, 2, 1, 1)
        qz_hint = Gtk.Label()
        qz_hint.set_markup("<small><i>kleiner = meer van de rolbreedte benut</i></small>")
        qz_hint.set_xalign(0)
        size_grid.attach(qz_hint, 2, 2, 1, 1)
        
        self.show_all()
    
    def _on_print_method_changed(self, widget):
        is_brother_ql = self.print_method_combo.get_active_id() == "brother_ql"
        self.cups_box.set_visible(not is_brother_ql)
        self.brother_ql_box.set_visible(is_brother_ql)
    
    def _discover_brother_ql(self, widget):
        try:
            result = subprocess.run(
                ["python3", "-m", "brother_ql", "discover"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10
            )
            output = result.stdout.decode("utf-8", errors="ignore").strip()
            if output:
                # pak de eerste gevonden identifier
                for line in output.splitlines():
                    if "usb://" in line:
                        identifier = line.strip().split()[0] if " " not in line.split("usb://")[0] else line.strip()
                        self.bq_identifier_entry.set_text(line.strip())
                        break
                self._toon_info_dialoog(f"Gevonden:\n{output}")
            else:
                self._toon_info_dialoog("Geen brother_ql-printer gevonden. Is de printer aan en verbonden via USB?")
        except FileNotFoundError:
            self._toon_info_dialoog("brother_ql is niet geïnstalleerd. Installeer met:\npip install brother_ql --break-system-packages")
        except Exception as e:
            self._toon_info_dialoog(f"Fout bij zoeken: {e}")
    
    def _toon_info_dialoog(self, msg):
        dialog = Gtk.MessageDialog(
            transient_for=self, flags=0, message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK, text=msg
        )
        dialog.run()
        dialog.destroy()
    
    def _refresh_printers(self, widget):
        self.printer_combo.remove_all()
        for p in get_cups_printers():
            self.printer_combo.append_text(p)
        self.printer_combo.set_active(0)
    
    def _section_label(self, text):
        label = Gtk.Label()
        label.set_markup(f"<b>{text}</b>")
        label.set_xalign(0)
        return label
    
    def _parse_key_value_lines(self, textview):
        buf = textview.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        result = {}
        for line in text.splitlines():
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                result[k.strip()] = v.strip()
        return result
    
    def _parse_lines(self, textview):
        buf = textview.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        return [l.strip() for l in text.splitlines() if l.strip()]
    
    def apply_to_config(self):
        self.config.set("storage_backend", self.backend_combo.get_active_id())
        self.config.set("xml_path", self.xml_path_entry.get_text().strip())
        self.config.set("sheets", {
            "sheet_url": self.sheet_url_entry.get_text().strip(),
            "credentials_file": self.creds_entry.get_text().strip(),
        })
        self.config.set("base_folder", self.base_folder_entry.get_text().strip())
        self.config.set("categorieen", self._parse_lines(self.categorieen_view))
        self.config.set("tijdsperiodes", self._parse_lines(self.tijdsperiodes_view))
        self.config.set("opslaglocatie_codes", self._parse_key_value_lines(self.opslaglocatie_view))
        self.config.set("sublocatie_codes", self._parse_key_value_lines(self.sublocatie_view))
        self.config.set("rij_codes", self._parse_key_value_lines(self.rij_view))
        printer_name = self.printer_combo.get_active_text() or ""
        self.config.set("printer", {
            "enabled": self.printer_enabled_check.get_active(),
            "print_method": self.print_method_combo.get_active_id() or "cups",
            "printer_name": printer_name,
            "brother_ql_model": self.bq_model_entry.get_text().strip(),
            "brother_ql_label": self.bq_label_entry.get_text().strip(),
            "brother_ql_identifier": self.bq_identifier_entry.get_text().strip(),
        })
        
        def _safe_float(entry, default):
            try:
                return float(entry.get_text().strip().replace(",", "."))
            except ValueError:
                return default
        
        self.config.set("barcode", {
            "module_width_mm": _safe_float(self.module_width_entry, 0.4),
            "module_height_mm": _safe_float(self.module_height_entry, 7.0),
            "quiet_zone_mm": _safe_float(self.quiet_zone_entry, 2.0),
        })


# ============================================
# TAB 1: REGISTREREN
# ============================================
class RegistreerTab(Gtk.Box):
    def __init__(self, main_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_window = main_window
        self.config = main_window.config
        self.set_border_width(15)
        
        self.condition_checks = {}  # widgets per staat-detail optie
        self.condition_box = None
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(scrolled, True, True, 0)
        
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        form.set_border_width(5)
        scrolled.add(form)
        
        # Titel
        form.pack_start(self._label("Titel (max 60 tekens)"), False, False, 0)
        title_row = Gtk.Box(spacing=5)
        self.titel_entry = Gtk.Entry()
        self.titel_entry.set_max_length(MAX_TITEL_LENGTE)
        self.titel_entry.connect("changed", self._on_titel_changed)
        title_row.pack_start(self.titel_entry, True, True, 0)
        self.titel_counter = Gtk.Label(label=f"0/{MAX_TITEL_LENGTE}")
        title_row.pack_start(self.titel_counter, False, False, 0)
        form.pack_start(title_row, False, False, 0)
        
        # Omschrijving
        form.pack_start(self._label("Omschrijving"), False, False, 0)
        self.omschrijving_view = Gtk.TextView()
        self.omschrijving_view.set_wrap_mode(Gtk.WrapMode.WORD)
        omschrijving_scroll = Gtk.ScrolledWindow()
        omschrijving_scroll.set_size_request(-1, 100)
        omschrijving_scroll.add(self.omschrijving_view)
        form.pack_start(omschrijving_scroll, False, False, 0)
        
        # Categorie & Tijdsperiode
        cat_row = Gtk.Box(spacing=10)
        cat_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        cat_col.pack_start(self._label("Categorie"), False, False, 0)
        self.categorie_combo = Gtk.ComboBoxText.new_with_entry()
        for c in self.config.get("categorieen", DEFAULT_CATEGORIEEN):
            self.categorie_combo.append_text(c)
        cat_col.pack_start(self.categorie_combo, False, False, 0)
        cat_row.pack_start(cat_col, True, True, 0)
        
        tp_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        tp_col.pack_start(self._label("Tijdsperiode"), False, False, 0)
        self.tijdsperiode_combo = Gtk.ComboBoxText.new_with_entry()
        for t in self.config.get("tijdsperiodes", DEFAULT_TIJDSPERIODES):
            self.tijdsperiode_combo.append_text(t)
        tp_col.pack_start(self.tijdsperiode_combo, False, False, 0)
        cat_row.pack_start(tp_col, True, True, 0)
        form.pack_start(cat_row, False, False, 0)
        
        # Conditie
        form.pack_start(self._label("Staat van het artikel"), False, False, 0)
        self.conditie_combo = Gtk.ComboBoxText()
        for c in CONDITIES:
            self.conditie_combo.append_text(c)
        self.conditie_combo.connect("changed", self._on_conditie_changed)
        form.pack_start(self.conditie_combo, False, False, 0)
        
        self.condition_details_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        form.pack_start(self.condition_details_container, False, False, 0)
        
        self.staat_details_extra_entry = Gtk.Entry()
        self.staat_details_extra_entry.set_placeholder_text("Overige staat-details (optioneel, vrije tekst)")
        form.pack_start(self.staat_details_extra_entry, False, False, 0)
        
        # Afmetingen & gewicht
        form.pack_start(self._label("Afmetingen (cm) en gewicht (kg)"), False, False, 0)
        dim_row = Gtk.Box(spacing=5)
        self.lengte_entry = self._number_entry("Lengte")
        self.breedte_entry = self._number_entry("Breedte")
        self.hoogte_entry = self._number_entry("Hoogte")
        self.gewicht_entry = self._number_entry("Gewicht")
        for e in (self.lengte_entry, self.breedte_entry, self.hoogte_entry, self.gewicht_entry):
            dim_row.pack_start(e, True, True, 0)
        form.pack_start(dim_row, False, False, 0)
        
        # Waarde & vraagprijs
        form.pack_start(self._label("Geschatte waarde en vraagprijs (€)"), False, False, 0)
        waarde_row = Gtk.Box(spacing=5)
        self.waarde_min_entry = self._number_entry("Min. waarde")
        self.waarde_max_entry = self._number_entry("Max. waarde")
        self.vraagprijs_entry = self._number_entry("Vraagprijs")
        for e in (self.waarde_min_entry, self.waarde_max_entry, self.vraagprijs_entry):
            waarde_row.pack_start(e, True, True, 0)
        form.pack_start(waarde_row, False, False, 0)
        
        # Opslaglocatie / Sublocatie / Rij
        form.pack_start(self._label("Opslaglocatie (bepaalt de eerste 3 tekens van het artikelnummer)"), False, False, 0)
        loc_row = Gtk.Box(spacing=5)
        self.opslaglocatie_combo = Gtk.ComboBoxText()
        for naam in self.config.get("opslaglocatie_codes", {}).keys():
            self.opslaglocatie_combo.append_text(naam)
        loc_row.pack_start(self.opslaglocatie_combo, True, True, 0)
        
        self.sublocatie_combo = Gtk.ComboBoxText()
        for naam in self.config.get("sublocatie_codes", {}).keys():
            self.sublocatie_combo.append_text(naam)
        loc_row.pack_start(self.sublocatie_combo, True, True, 0)
        
        self.rij_combo = Gtk.ComboBoxText()
        for naam in self.config.get("rij_codes", {}).keys():
            self.rij_combo.append_text(naam)
        loc_row.pack_start(self.rij_combo, True, True, 0)
        form.pack_start(loc_row, False, False, 0)
        
        warning_label = Gtk.Label()
        warning_label.set_markup(
            "<small><i>⚠️ Zorg dat de basismap-instelling overeenkomt met marktplaats_manager, "
            "zodat die hetzelfde mapje voor dit artikelnummer hergebruikt (de map bestaat dan al).</i></small>"
        )
        warning_label.set_xalign(0)
        warning_label.set_line_wrap(True)
        form.pack_start(warning_label, False, False, 5)
        
        # Barcode
        self.barcode_check = Gtk.CheckButton(label="Barcode genereren bij opslaan")
        self.barcode_check.set_active(True)
        form.pack_start(self.barcode_check, False, False, 0)
        
        # Opslaan-knop
        self.opslaan_btn = Gtk.Button(label="💾 Product registreren")
        self.opslaan_btn.connect("clicked", self._on_opslaan)
        form.pack_start(self.opslaan_btn, False, False, 10)
        
        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0)
        self.status_label.set_line_wrap(True)
        form.pack_start(self.status_label, False, False, 0)
        
        self._on_conditie_changed(self.conditie_combo)
    
    def _label(self, text):
        label = Gtk.Label()
        label.set_markup(f"<b>{text}</b>")
        label.set_xalign(0)
        return label
    
    def _number_entry(self, placeholder):
        entry = Gtk.Entry()
        entry.set_placeholder_text(placeholder)
        return entry
    
    def _on_titel_changed(self, widget):
        length = len(widget.get_text())
        self.titel_counter.set_text(f"{length}/{MAX_TITEL_LENGTE}")
    
    def _on_conditie_changed(self, widget):
        for child in self.condition_details_container.get_children():
            self.condition_details_container.remove(child)
        self.condition_checks = {}
        
        conditie = widget.get_active_text()
        opties = STAAT_DETAILS.get(conditie, [])
        for optie in opties:
            check = Gtk.CheckButton(label=optie)
            self.condition_checks[optie] = check
            self.condition_details_container.pack_start(check, False, False, 0)
        self.condition_details_container.show_all()
    
    def _verzamel_staat_details(self):
        geselecteerd = [naam for naam, check in self.condition_checks.items() if check.get_active()]
        extra = self.staat_details_extra_entry.get_text().strip()
        if extra:
            geselecteerd.append(extra)
        return ", ".join(geselecteerd)
    
    def _reset_form(self):
        self.titel_entry.set_text("")
        self.omschrijving_view.get_buffer().set_text("")
        self.categorie_combo.get_child().set_text("")
        self.tijdsperiode_combo.get_child().set_text("")
        self.conditie_combo.set_active(0)
        self.staat_details_extra_entry.set_text("")
        for e in (self.lengte_entry, self.breedte_entry, self.hoogte_entry, self.gewicht_entry,
                  self.waarde_min_entry, self.waarde_max_entry, self.vraagprijs_entry):
            e.set_text("")
    
    def _on_opslaan(self, widget):
        titel = self.titel_entry.get_text().strip()
        if not titel:
            self._toon_fout("Titel is verplicht.")
            return
        if len(titel) > MAX_TITEL_LENGTE:
            self._toon_fout(f"Titel mag maximaal {MAX_TITEL_LENGTE} tekens zijn.")
            return
        
        opslaglocatie_naam = self.opslaglocatie_combo.get_active_text()
        sublocatie_naam = self.sublocatie_combo.get_active_text()
        rij_naam = self.rij_combo.get_active_text()
        if not (opslaglocatie_naam and sublocatie_naam and rij_naam):
            self._toon_fout("Kies een opslaglocatie, sublocatie en rij.")
            return
        
        opslaglocatie_code = self.config.get("opslaglocatie_codes", {}).get(opslaglocatie_naam, "X")
        sublocatie_code = self.config.get("sublocatie_codes", {}).get(sublocatie_naam, "X")
        rij_code = self.config.get("rij_codes", {}).get(rij_naam, "X")
        
        buf = self.omschrijving_view.get_buffer()
        omschrijving = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        
        storage = get_backend(self.config)
        
        try:
            artikelnummer = generate_artikelnummer(
                self.config, storage, opslaglocatie_code, sublocatie_code, rij_code
            )
        except Exception as e:
            self._toon_fout(f"Kon artikelnummer niet genereren: {e}")
            return
        
        product = {col: "" for col in COLUMNS}
        product.update({
            "artikelnummer": artikelnummer,
            "titel": titel,
            "categorie": self.categorie_combo.get_active_text() or "",
            "omschrijving": omschrijving,
            "lengte": self.lengte_entry.get_text().strip(),
            "breedte": self.breedte_entry.get_text().strip(),
            "hoogte": self.hoogte_entry.get_text().strip(),
            "gewicht": self.gewicht_entry.get_text().strip(),
            "conditie": self.conditie_combo.get_active_text() or "",
            "staat_details": self._verzamel_staat_details(),
            "waarde_min": self.waarde_min_entry.get_text().strip(),
            "waarde_max": self.waarde_max_entry.get_text().strip(),
            "vraagprijs": self.vraagprijs_entry.get_text().strip(),
            "aanmaakdatum": datetime.date.today().isoformat(),
            "tijdsperiode": self.tijdsperiode_combo.get_active_text() or "",
            "opslaglocatie": opslaglocatie_naam,
            "sublocatie": sublocatie_naam,
            "rij": rij_naam,
            "verkocht": "nee",
            "online": "nee",
            "algemene_voorwaarden": "",  # leeg = auto_marktplaats.py gebruikt de vaste tekst
        })
        
        try:
            folder, bestond_al = maak_product_map(self.config, product)
            product["folder_locatie"] = folder
        except Exception as e:
            self._toon_fout(f"Kon productmap niet aanmaken: {e}")
            return
        
        barcode_msg = ""
        if self.barcode_check.get_active():
            try:
                barcode_path = genereer_barcode(artikelnummer, folder, self.config.get("barcode", {}))
                barcode_msg = f"\n📊 Barcode opgeslagen: {barcode_path}"
                printer_cfg = self.config.get("printer", {})
                if printer_cfg.get("enabled"):
                    print_barcode(barcode_path, printer_cfg)
                    methode = printer_cfg.get("print_method", "cups")
                    doel = printer_cfg.get("printer_name") if methode == "cups" else "Brother QL (USB)"
                    barcode_msg += f"\n🖨️ Verstuurd naar printer '{doel}'"
            except Exception as e:
                barcode_msg = f"\n⚠️ Barcode-fout: {e}"
        
        try:
            storage.add_product(product)
        except Exception as e:
            self._toon_fout(f"Kon niet opslaan naar opslag-backend: {e}")
            return
        
        map_msg = "Bestaande map hergebruikt" if bestond_al else "Nieuwe map aangemaakt"
        self.status_label.set_markup(
            f"<span foreground='green'>✅ Product <b>{artikelnummer}</b> geregistreerd.\n"
            f"📁 {map_msg}: {folder}{barcode_msg}</span>"
        )
        self._reset_form()
        self.main_window.overzicht_tab.herlaad()
    
    def _toon_fout(self, msg):
        self.status_label.set_markup(f"<span foreground='red'>❌ {msg}</span>")


# ============================================
# TAB 2: OVERZICHT
# ============================================
OVERZICHT_KOLOMMEN = ["artikelnummer", "titel", "categorie", "conditie", "vraagprijs",
                      "aanmaakdatum", "online", "advertentie_url", "verkocht", "verkoopprijs",
                      "verkoopdatum", "leverwijze", "klant_naam"]
OVERZICHT_LABELS = ["Artikelnummer", "Titel", "Categorie", "Conditie", "Vraagprijs",
                    "Aanmaakdatum", "Online", "Advertentie-URL", "Verkocht", "Verkoopprijs",
                    "Verkoopdatum", "Leverwijze", "Klant"]


class OverzichtTab(Gtk.Box):
    def __init__(self, main_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_window = main_window
        self.config = main_window.config
        self.set_border_width(15)
        
        # Filter-knoppen
        filter_row = Gtk.Box(spacing=5)
        self.filter_alles_btn = Gtk.RadioButton.new_with_label_from_widget(None, "Alles")
        self.filter_offline_btn = Gtk.RadioButton.new_with_label_from_widget(self.filter_alles_btn, "Offline")
        self.filter_online_btn = Gtk.RadioButton.new_with_label_from_widget(self.filter_alles_btn, "Online")
        self.filter_verkocht_btn = Gtk.RadioButton.new_with_label_from_widget(self.filter_alles_btn, "Verkocht")
        self.filter_offline_btn.set_active(True)
        for btn in (self.filter_alles_btn, self.filter_offline_btn, self.filter_online_btn, self.filter_verkocht_btn):
            btn.connect("toggled", lambda w: self.herlaad())
            filter_row.pack_start(btn, False, False, 0)
        
        refresh_btn = Gtk.Button(label="🔄 Vernieuwen")
        refresh_btn.connect("clicked", lambda w: self.herlaad())
        filter_row.pack_start(refresh_btn, False, False, 10)
        
        self.pack_start(filter_row, False, False, 0)
        
        # Tabel
        self.store = Gtk.ListStore(*([str] * len(OVERZICHT_KOLOMMEN)))
        self.tree_view = Gtk.TreeView(model=self.store)
        self.tree_view.set_search_column(0)
        
        for i, label in enumerate(OVERZICHT_LABELS):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(label, renderer, text=i)
            column.set_sort_column_id(i)
            column.set_resizable(True)
            self.tree_view.append_column(column)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.tree_view)
        self.pack_start(scrolled, True, True, 0)
        
        # Actie-knoppen
        actie_row = Gtk.Box(spacing=5)
        self.bewerk_btn = Gtk.Button(label="✏️ Bewerken")
        self.bewerk_btn.connect("clicked", self._on_bewerken)
        actie_row.pack_start(self.bewerk_btn, False, False, 0)
        
        self.verwijder_btn = Gtk.Button(label="🗑️ Verwijderen")
        self.verwijder_btn.connect("clicked", self._on_verwijderen)
        actie_row.pack_start(self.verwijder_btn, False, False, 0)
        
        self.online_btn = Gtk.Button(label="🌐 Markeer als online")
        self.online_btn.connect("clicked", self._on_markeer_online)
        actie_row.pack_start(self.online_btn, False, False, 0)
        
        self.verkocht_btn = Gtk.Button(label="💰 Markeer als verkocht")
        self.verkocht_btn.connect("clicked", self._on_markeer_verkocht)
        actie_row.pack_start(self.verkocht_btn, False, False, 0)
        
        self.pack_start(actie_row, False, False, 0)
        
        self.omzet_label = Gtk.Label()
        self.omzet_label.set_xalign(0)
        self.pack_start(self.omzet_label, False, False, 0)
        
        self.herlaad()
    
    def _huidige_producten(self):
        storage = get_backend(self.config)
        try:
            return storage.load_products()
        except Exception as e:
            self._toon_foutdialoog(f"Kon producten niet laden: {e}")
            return []
    
    def herlaad(self):
        self.store.clear()
        producten = self._huidige_producten()
        
        if self.filter_offline_btn.get_active():
            producten = [p for p in producten
                         if p.get("verkocht", "nee").lower() != "ja"
                         and p.get("online", "nee").lower() != "ja"]
        elif self.filter_online_btn.get_active():
            producten = [p for p in producten
                         if p.get("verkocht", "nee").lower() != "ja"
                         and p.get("online", "nee").lower() == "ja"]
        elif self.filter_verkocht_btn.get_active():
            producten = [p for p in producten if p.get("verkocht", "nee").lower() == "ja"]
        
        for p in producten:
            row = [p.get(col, "") for col in OVERZICHT_KOLOMMEN]
            self.store.append(row)
        
        if self.filter_verkocht_btn.get_active():
            totaal = 0.0
            for p in producten:
                try:
                    prijs = p.get("verkoopprijs", "").replace("€", "").replace(",", ".").strip()
                    totaal += float(prijs) if prijs else 0.0
                except ValueError:
                    pass
            self.omzet_label.set_markup(
                f"<b>Totale omzet (verkocht, {len(producten)} items): €{totaal:.2f}</b>\n"
                f"<small><i>Let op: er wordt geen inkoopprijs bijgehouden (kringloop-donaties), "
                f"dus omzet = winst in dit overzicht.</i></small>"
            )
        else:
            self.omzet_label.set_text("")
    
    def _geselecteerd_artikelnummer(self):
        selection = self.tree_view.get_selection()
        model, treeiter = selection.get_selected()
        if treeiter is None:
            return None
        return model[treeiter][0]
    
    def _toon_foutdialoog(self, msg):
        dialog = Gtk.MessageDialog(
            transient_for=self.main_window, flags=0,
            message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, text=msg
        )
        dialog.run()
        dialog.destroy()
    
    def _on_bewerken(self, widget):
        artikelnummer = self._geselecteerd_artikelnummer()
        if not artikelnummer:
            self._toon_foutdialoog("Selecteer eerst een product.")
            return
        
        storage = get_backend(self.config)
        producten = storage.load_products()
        product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
        if not product:
            self._toon_foutdialoog("Product niet gevonden.")
            return
        
        dialog = BewerkDialog(self.main_window, product)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            bijgewerkt = dialog.get_product()
            try:
                storage.update_product(artikelnummer, bijgewerkt)
                self.herlaad()
            except Exception as e:
                self._toon_foutdialoog(f"Kon niet opslaan: {e}")
        dialog.destroy()
    
    def _on_verwijderen(self, widget):
        artikelnummer = self._geselecteerd_artikelnummer()
        if not artikelnummer:
            self._toon_foutdialoog("Selecteer eerst een product.")
            return
        
        storage = get_backend(self.config)
        producten = storage.load_products()
        product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
        folder = product.get("folder_locatie", "").strip() if product else ""
        folder_bestaat = bool(folder) and os.path.isdir(folder)
        
        confirm = Gtk.MessageDialog(
            transient_for=self.main_window, flags=0,
            message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
            text=f"Product {artikelnummer} verwijderen uit de opslag?"
        )
        if folder_bestaat:
            confirm.format_secondary_text(f"De productmap wordt naar de prullenbak verplaatst:\n{folder}")
        else:
            confirm.format_secondary_text("Geen (bestaande) productmap gevonden om te verplaatsen.")
        response = confirm.run()
        confirm.destroy()
        
        if response == Gtk.ResponseType.YES:
            try:
                storage.delete_product(artikelnummer)
            except Exception as e:
                self._toon_foutdialoog(f"Kon niet verwijderen: {e}")
                return
            
            if folder_bestaat:
                try:
                    from send2trash import send2trash
                    send2trash(folder)
                except ImportError:
                    self._toon_foutdialoog(
                        "Product is verwijderd uit de opslag, maar send2trash is niet "
                        "geïnstalleerd - de map is blijven staan. Installeer met:\n"
                        "pip install Send2Trash --break-system-packages"
                    )
                except Exception as e:
                    self._toon_foutdialoog(
                        f"Product is verwijderd uit de opslag, maar de map kon niet naar "
                        f"de prullenbak worden verplaatst: {e}"
                    )
            
            self.herlaad()
    
    def _on_markeer_online(self, widget):
        artikelnummer = self._geselecteerd_artikelnummer()
        if not artikelnummer:
            self._toon_foutdialoog("Selecteer eerst een product.")
            return
        
        dialog = Gtk.Dialog(title="Markeer als online", transient_for=self.main_window, flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(10)
        
        box.pack_start(Gtk.Label(label=f"Advertentie-URL voor {artikelnummer} (optioneel):"), False, False, 0)
        url_entry = Gtk.Entry()
        url_entry.set_placeholder_text("https://www.marktplaats.nl/v/...")
        box.pack_start(url_entry, False, False, 0)
        
        dialog.show_all()
        response = dialog.run()
        url = url_entry.get_text().strip()
        dialog.destroy()
        
        if response == Gtk.ResponseType.OK:
            storage = get_backend(self.config)
            producten = storage.load_products()
            product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
            if not product:
                self._toon_foutdialoog("Product niet gevonden.")
                return
            product["online"] = "ja"
            if url:
                product["advertentie_url"] = url
            try:
                storage.update_product(artikelnummer, product)
                self.herlaad()
            except Exception as e:
                self._toon_foutdialoog(f"Kon niet opslaan: {e}")
    
    def _on_markeer_verkocht(self, widget):
        artikelnummer = self._geselecteerd_artikelnummer()
        if not artikelnummer:
            self._toon_foutdialoog("Selecteer eerst een product.")
            return
        
        dialog = VerkochtDialog(self.main_window, artikelnummer)
        response = dialog.run()
        gegevens = dialog.get_gegevens() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        
        if gegevens is None:
            return
        
        if not gegevens["verkoopprijs"]:
            self._toon_foutdialoog("Vul een verkoopprijs in.")
            return
        
        storage = get_backend(self.config)
        producten = storage.load_products()
        product = next((p for p in producten if p.get("artikelnummer") == artikelnummer), None)
        if not product:
            self._toon_foutdialoog("Product niet gevonden.")
            return
        
        product["verkocht"] = "ja"
        product.update(gegevens)
        try:
            storage.update_product(artikelnummer, product)
            self.herlaad()
        except Exception as e:
            self._toon_foutdialoog(f"Kon niet opslaan: {e}")


class VerkochtDialog(Gtk.Dialog):
    """Dialoog voor het markeren als verkocht: eerst kiezen tussen Ophalen
    en Verzenden, met bijbehorende klantgegevens."""
    def __init__(self, parent, artikelnummer):
        super().__init__(title=f"Markeer als verkocht - {artikelnummer}", transient_for=parent, flags=0)
        self.set_default_size(420, 380)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        
        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)
        
        box.pack_start(Gtk.Label(label=f"Verkoopprijs voor {artikelnummer}:", xalign=0), False, False, 0)
        self.prijs_entry = Gtk.Entry()
        self.prijs_entry.set_placeholder_text("bijv. 45.00")
        box.pack_start(self.prijs_entry, False, False, 0)
        
        vandaag = datetime.date.today().isoformat()
        box.pack_start(Gtk.Label(label=f"Verkoopdatum: {vandaag} (automatisch)", xalign=0), False, False, 0)
        self.vandaag = vandaag
        
        box.pack_start(Gtk.Separator(), False, False, 6)
        
        box.pack_start(self._bold_label("Leverwijze"), False, False, 0)
        lever_row = Gtk.Box(spacing=10)
        self.ophalen_btn = Gtk.RadioButton.new_with_label_from_widget(None, "Ophalen")
        self.verzenden_btn = Gtk.RadioButton.new_with_label_from_widget(self.ophalen_btn, "Verzenden")
        self.ophalen_btn.connect("toggled", self._on_leverwijze_changed)
        lever_row.pack_start(self.ophalen_btn, False, False, 0)
        lever_row.pack_start(self.verzenden_btn, False, False, 0)
        box.pack_start(lever_row, False, False, 0)
        
        box.pack_start(Gtk.Label(label="Marktplaatsnaam koper:", xalign=0), False, False, 0)
        self.klant_naam_entry = Gtk.Entry()
        box.pack_start(self.klant_naam_entry, False, False, 0)
        
        # --- Ophalen-specifieke velden ---
        self.ophalen_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(self.ophalen_box, False, False, 0)
        
        self.ophalen_box.pack_start(Gtk.Label(label="Telefoonnummer:", xalign=0), False, False, 0)
        self.telefoon_entry = Gtk.Entry()
        self.ophalen_box.pack_start(self.telefoon_entry, False, False, 0)
        
        self.ophalen_box.pack_start(Gtk.Label(label="E-mail:", xalign=0), False, False, 0)
        self.email_entry = Gtk.Entry()
        self.ophalen_box.pack_start(self.email_entry, False, False, 0)
        
        self.ophalen_box.pack_start(Gtk.Label(label="Afspraak (datum/tijd ophalen):", xalign=0), False, False, 0)
        self.afspraak_entry = Gtk.Entry()
        self.afspraak_entry.set_placeholder_text("bijv. zaterdag 14:00")
        self.ophalen_box.pack_start(self.afspraak_entry, False, False, 0)
        
        # --- Verzenden-specifieke velden ---
        self.verzenden_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(self.verzenden_box, False, False, 0)
        
        self.verzenden_box.pack_start(Gtk.Label(label="Track & Trace-nummer (optioneel):", xalign=0), False, False, 0)
        self.track_trace_entry = Gtk.Entry()
        self.verzenden_box.pack_start(self.track_trace_entry, False, False, 0)
        
        self.ophalen_btn.set_active(True)
        self._on_leverwijze_changed(self.ophalen_btn)
        
        self.show_all()
    
    def _bold_label(self, text):
        label = Gtk.Label()
        label.set_markup(f"<b>{text}</b>")
        label.set_xalign(0)
        return label
    
    def _on_leverwijze_changed(self, widget):
        is_ophalen = self.ophalen_btn.get_active()
        self.ophalen_box.set_visible(is_ophalen)
        self.verzenden_box.set_visible(not is_ophalen)
    
    def get_gegevens(self):
        leverwijze = "ophalen" if self.ophalen_btn.get_active() else "verzenden"
        gegevens = {
            "verkoopprijs": self.prijs_entry.get_text().strip(),
            "verkoopdatum": self.vandaag,
            "leverwijze": leverwijze,
            "klant_naam": self.klant_naam_entry.get_text().strip(),
        }
        if leverwijze == "ophalen":
            gegevens["klant_telefoon"] = self.telefoon_entry.get_text().strip()
            gegevens["klant_email"] = self.email_entry.get_text().strip()
            gegevens["ophaal_afspraak"] = self.afspraak_entry.get_text().strip()
            gegevens["track_trace"] = ""
        else:
            gegevens["klant_telefoon"] = ""
            gegevens["klant_email"] = ""
            gegevens["ophaal_afspraak"] = ""
            gegevens["track_trace"] = self.track_trace_entry.get_text().strip()
        return gegevens


class BewerkDialog(Gtk.Dialog):
    """Dialoog om alle velden van een product te bewerken."""
    def __init__(self, parent, product):
        super().__init__(title=f"Bewerken - {product.get('artikelnummer', '')}", transient_for=parent, flags=0)
        self.product = dict(product)
        self.set_default_size(500, 600)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        
        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(10)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.pack_start(scrolled, True, True, 0)
        
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        inner.set_border_width(5)
        scrolled.add(inner)
        
        self.entries = {}
        # artikelnummer niet bewerkbaar (is de sleutel)
        inner.pack_start(Gtk.Label(label=f"Artikelnummer: {self.product.get('artikelnummer', '')}"), False, False, 0)
        
        bewerkbare_velden = [c for c in COLUMNS if c not in ("artikelnummer", "folder_locatie")]
        for veld in bewerkbare_velden:
            label = Gtk.Label(label=veld)
            label.set_xalign(0)
            inner.pack_start(label, False, False, 0)
            if veld in ("omschrijving", "algemene_voorwaarden"):
                view = Gtk.TextView()
                view.get_buffer().set_text(self.product.get(veld, ""))
                view_scroll = Gtk.ScrolledWindow()
                view_scroll.set_size_request(-1, 80)
                view_scroll.add(view)
                inner.pack_start(view_scroll, False, False, 0)
                self.entries[veld] = view
            else:
                entry = Gtk.Entry()
                entry.set_text(self.product.get(veld, ""))
                inner.pack_start(entry, False, False, 0)
                self.entries[veld] = entry
        
        self.show_all()
    
    def get_product(self):
        result = dict(self.product)
        for veld, widget in self.entries.items():
            if isinstance(widget, Gtk.TextView):
                buf = widget.get_buffer()
                result[veld] = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
            else:
                result[veld] = widget.get_text()
        return result


# ============================================
# HOOFDVENSTER
# ============================================
class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Marktplaats Product Manager")
        self.set_default_size(700, 800)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        icon_path = os.path.join(config_dir(), "icon.png")
        if os.path.exists(icon_path):
            try:
                self.set_icon_from_file(icon_path)
            except Exception:
                pass
        
        self.config = ConfigManager()
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)
        
        # Menubalk met instellingen
        menu_row = Gtk.Box(spacing=5)
        menu_row.set_border_width(5)
        settings_btn = Gtk.Button(label="⚙️ Instellingen")
        settings_btn.connect("clicked", self._open_settings)
        menu_row.pack_end(settings_btn, False, False, 0)
        
        backend_label = Gtk.Label()
        backend_label.set_markup(f"<small>Actieve opslag: <b>{self.config.get('storage_backend')}</b></small>")
        self.backend_label = backend_label
        menu_row.pack_start(backend_label, False, False, 5)
        vbox.pack_start(menu_row, False, False, 0)
        
        # Tabs
        self.notebook = Gtk.Notebook()
        vbox.pack_start(self.notebook, True, True, 0)
        
        self.registreer_tab = RegistreerTab(self)
        self.notebook.append_page(self.registreer_tab, Gtk.Label(label="📝 Registreren"))
        
        self.overzicht_tab = OverzichtTab(self)
        self.notebook.append_page(self.overzicht_tab, Gtk.Label(label="📊 Overzicht"))
    
    def _open_settings(self, widget):
        dialog = SettingsDialog(self, self.config)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            dialog.apply_to_config()
            self.backend_label.set_markup(f"<small>Actieve opslag: <b>{self.config.get('storage_backend')}</b></small>")
            # Comboboxen in registreer-tab verversen met eventueel gewijzigde lijsten
            self._herbouw_registreer_tab()
        dialog.destroy()
    
    def _herbouw_registreer_tab(self):
        self.notebook.remove_page(0)
        self.registreer_tab = RegistreerTab(self)
        self.notebook.insert_page(self.registreer_tab, Gtk.Label(label="📝 Registreren"), 0)
        self.notebook.show_all()


def main():
    GLib.set_prgname("marktplaats_productmanager")
    apply_css()
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
