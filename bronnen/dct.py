"""DCT (Wielsbeke, Maldegem, Brussel, Knokke) — eigen stock op dct.be (Modix/Fork CMS).

Geen bruikbare JSON-API: de lijst /nl/aanbod?manufacturers=[porsche] toont 12 wagens
in HTML; "Toon meer" doet een POST naar /frontend/ajax met de filter in de sessie,
dus met enkel GET onbruikbaar. Daarom splitsen we op showroom (companyLocations)
en sorteren we op prijs oplopend + aflopend: zo komen tot 24 wagens per showroom
boven. Km, inschrijving, pk, CO2 en bak staan enkel op de detailpagina; die halen
we alleen op voor 911 GTS/Turbo.
"""
import html
import re
import time

NAAM = "DCT"
BASIS = "https://www.dct.be"
LIJST = BASIS + "/nl/aanbod?manufacturers=[porsche]&submitted=true"
MAX_DETAILS = 18  # samen met de lijstpagina's blijven we onder ~30 requests
PAUZE = 2.5  # dct.be geeft HTTP 429 bij ~10 snelle requests na elkaar

KAART = re.compile(r'<a href="(/nl/aanbod/detail/(\d+)/[^"?]*)[^"]*" class="card vehicle-card"(.*?)</a>', re.S)


def _tekst(s):
    """HTML -> platte tekst op één regel."""
    s = re.sub(r"<br\s*/?>|</li>|</td>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _int(s):
    digits = re.sub(r"[^\d]", "", str(s or ""))
    return int(digits) if digits else None


def _spec(det, label):
    """Waarde uit de specificatietabel: <th>label</th><td>waarde</td>."""
    m = re.search(r"<th[^>]*>\s*" + re.escape(label) + r"[^<]*</th>\s*<td>(.*?)</td>", det, re.S | re.I)
    return _tekst(m.group(1)) if m else ""


def _get(get, url):
    """Ophalen met pauze; bij HTTP 429 (te snel) één keer opnieuw na 15 s."""
    try:
        r = get(url)
    except Exception as e:
        if "429" not in str(e):
            raise
        time.sleep(15)
        r = get(url)
    time.sleep(PAUZE)
    return r


def _lijst(get, url, kaarten):
    """Eén lijstpagina ophalen; kaarten aanvullen per id. Geeft (html, hasMore) terug."""
    pagina = _get(get, url)
    if 'class="vehicle-cards' not in pagina and "vehicle-card" not in pagina:
        raise RuntimeError("DCT: geen wagenlijst op " + url + " (structuur gewijzigd?)")
    for pad, vid, kaart in KAART.findall(pagina):
        kaarten.setdefault(vid, (pad, kaart))
    meer = re.search(r'"hasMore":(true|false)', pagina)
    return pagina, bool(meer and meer.group(1) == "true")


def fetch(get):
    kaarten = {}
    eerste, meer = _lijst(get, LIJST + "&sorting=2", kaarten)
    if meer:
        _lijst(get, LIJST + "&sorting=3", kaarten)
    # Per showroom (lijst uit de filterknoppen), prijs oplopend en aflopend
    for loc in re.findall(r'data-url="([^"]+)" data-filter="companyLocations"', eerste):
        url = LIJST + "&companyLocations=[" + loc + "]"
        _, meer = _lijst(get, url + "&sorting=2", kaarten)
        if meer:
            _lijst(get, url + "&sorting=3", kaarten)
    if not kaarten:
        raise RuntimeError("DCT: geen wagenkaarten gevonden (structuur gewijzigd?)")

    cars = []
    for vid, (pad, kaart) in sorted(kaarten.items()):
        model = re.search(r'<h2 itemprop="name">(.*?)</h2>', kaart, re.S)
        sub = re.search(r'<h3 itemprop="description">(.*?)</h3>', kaart, re.S)
        if not model:
            raise RuntimeError("DCT: wagenkaart zonder titel (structuur gewijzigd?)")
        titel = (_tekst(model.group(1)) + " " + _tekst(sub.group(1) if sub else "")).strip()
        # Voorfilter: enkel 911-familie met GTS of Turbo (fijnere filter zit in tracker.py)
        if not re.search(r"911|99[127]", titel) or not re.search(r"gts|turbo", titel.lower()):
            continue
        if len(cars) >= MAX_DETAILS:
            break
        prijs = re.search(r'itemprop="price" content="(\d+)"', kaart)
        foto = re.search(r'<img src="([^"]+)"', kaart)
        plaats = re.search(r'class="location-overlay">([^<]+)<', kaart)
        url = BASIS + pad

        # Detailpagina: specificaties en highlights
        det = _get(get, url)
        if "Kilometerstand" not in det:
            raise RuntimeError("DCT: geen specificaties op " + url + " (structuur gewijzigd?)")
        maand, _, jaar = _spec(det, "Eerste inschrijving").partition("/")
        vermogen = _spec(det, "Vermogen").lower()
        pk = re.search(r"(\d+)\s*pk", vermogen)
        kw = re.search(r"(\d+)\s*kw", vermogen)
        pk = int(pk.group(1)) if pk else (round(int(kw.group(1)) * 1.36) if kw else None)
        bak = _spec(det, "Transmissie").lower()
        high = det.split('class="card highlights">', 1)[-1].split("car-pass", 1)[0][:6000] \
            if 'class="card highlights"' in det else ""
        # Carrosserie ("Cabriolet", "Sportwagen") mee in de tekst: titels laten 'Cabrio' soms weg
        txt = (titel + " " + _spec(det, "Carrosserie") + " " + _tekst(high)).lower()

        cars.append({
            "id": "dct-" + vid,
            "bron": NAAM,
            "titel": titel,
            "prijs": int(prijs.group(1)) if prijs and int(prijs.group(1)) > 0 else None,
            "km": _int(_spec(det, "Kilometerstand")) or 0,
            "jaar": _int(jaar),
            "maand": _int(maand) if _int(maand) and 1 <= _int(maand) <= 12 else 6,
            "pk": pk,
            "manueel": bool(re.search(r"manu|handgeschakeld", bak)),
            "co2": _int(_spec(det, "CO2")),
            "land": "BE",
            "plaats": _tekst(plaats.group(1)) if plaats else None,
            "verkoper": "DCT",
            "dealer": True,
            "foto": (BASIS + foto.group(1) if foto.group(1).startswith("/") else foto.group(1)) if foto else None,
            "url": url,
            "_tekst": txt,
        })
    return cars
