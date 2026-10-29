"""Lampe Interesting Cars (Gits) — eigen stock op lampe.be (Modix-platform).

Geen JSON-API: de stocklijst /nl/te-koop?brand=porsche is gewone HTML met alle
wagens op één pagina (titel, inschrijving, km, prijs, foto). Vermogen, CO2 en
opties staan enkel op de detailpagina; die halen we alleen op voor 911 GTS/Turbo.
"""
import html
import re
import time

NAAM = "Lampe"
BASIS = "https://www.lampe.be"
LIJST = BASIS + "/nl/te-koop?brand=porsche"

KAART = re.compile(r'<div class="item-car-new item-car-index">(.*?)<div class="item-price">(.*?)</div>', re.S)


def _tekst(s):
    """HTML -> platte tekst op één regel."""
    s = re.sub(r"<br\s*/?>|</li>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _int(s):
    digits = re.sub(r"[^\d]", "", str(s or ""))
    return int(digits) if digits else None


def _spec(blok, label):
    """Waarde onder <small>label</small><br> in een specs-blok."""
    m = re.search(r"<small>\s*" + label + r"\s*</small>\s*<br>\s*([^<]+)", blok, re.I)
    return m.group(1).strip() if m else ""


def fetch(get):
    lijst = get(LIJST)
    kaarten = KAART.findall(lijst)
    if not kaarten:
        raise RuntimeError("Lampe: geen wagens gevonden in de stocklijst (structuur gewijzigd?)")
    cars = []
    for kaart, prijs in kaarten:
        link = re.search(r'href="(/nl/te-koop/detail-2/([^"#]+))"', kaart)
        titel = re.search(r"<h3>(.*?)</h3>", kaart, re.S)
        if not link or not titel:
            raise RuntimeError("Lampe: wagenkaart zonder link of titel (structuur gewijzigd?)")
        titel = _tekst(titel.group(1))
        # Voorfilter: enkel 911-familie met GTS of Turbo (fijnere filter zit in tracker.py)
        if not re.search(r"911|99[127]", titel) or not re.search(r"gts|turbo", titel.lower()):
            continue
        maand, _, jaar = _spec(kaart, "Inschrijving").partition("/")
        foto = re.search(r'<img class="car" src="([^"]+)"', kaart)
        url = BASIS + link.group(1)

        # Detailpagina: vermogen, omschrijving, opties
        time.sleep(1)
        det = get(url)
        kop = det.split('class="item-desc"', 1)[0]
        desc = det.split('class="item-desc"', 1)[-1].split("* Opgelet", 1)[0]
        txt = (titel + " " + _tekst(desc)).lower()
        pk = _int(re.sub(r"kw.*", "", _spec(kop, "Vermogen"), flags=re.I))
        if pk and "kw" in _spec(kop, "Vermogen").lower():
            pk = round(pk * 1.36)
        # CO2: WLTP voorrang (zoals AutoScout24), anders NEDC
        co2 = re.search(r"(\d{3})\s*gram\s*wltp", txt) or re.search(r"co2[^\d]{0,30}(\d{3})", txt)
        # Bak staat niet in de specs: manueel enkel als het expliciet vermeld wordt
        manueel = bool(re.search(r"manue|handgeschakeld|manual|schaltgetriebe|\bg1a\b", txt)) \
            and not re.search(r"\bpdk\b|tiptronic|doppelkupplung", txt)

        cars.append({
            "id": "lampe-" + link.group(2),
            "bron": NAAM,
            "titel": titel,
            "prijs": _int(prijs) if re.search(r"\d", prijs) else None,
            "km": _int(_spec(kaart, "Km-stand")) or 0,
            "jaar": _int(jaar),
            "maand": _int(maand) if _int(maand) and 1 <= _int(maand) <= 12 else 6,
            "pk": pk,
            "manueel": manueel,
            "co2": int(co2.group(1)) if co2 else None,
            "land": "BE",
            "plaats": "Gits",
            "verkoper": "Lampe Interesting Cars",
            "dealer": True,
            "foto": foto.group(1) if foto else None,
            "url": url,
            "_tekst": txt,
        })
    return cars
