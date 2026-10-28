"""AE Cars (Kuurne) — eigen PHP-site, geen API: alles staat als HTML op /wagens/."""
import html
import re
import time

NAAM = "AE Cars"
BASIS = "https://www.aecars.be"

# één tegel in het overzicht: link, foto, titel, "pk / km / jaar", prijs
TEGEL = re.compile(
    r"<a href='(https://www\.aecars\.be/wagens/detail/([^']+))'[^>]*>.*?"
    r"ximgs='([^']*)'.*?acc_caption_inner'>\s*(.*?)<br>\s*(.*?)\s*"
    r"<span class='xb acc_price'>(.*?)</span>", re.S)


def _int(s):
    d = re.sub(r"\D", "", s or "")
    return int(d) if d else None


def _veld(page, label):
    """Waarde uit de spec-tabellen op de detailpagina (bv. 'transmissie')."""
    m = re.search(r"<td[^>]*>\s*" + re.escape(label) + r"\s*</td>\s*<td[^>]*>\s*(.*?)\s*</td>", page, re.S | re.I)
    return html.unescape(m.group(1)).strip() if m else ""


def _tekst(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def fetch(get):
    overzicht = get(BASIS + "/wagens/")
    tegels = TEGEL.findall(overzicht)
    if not tegels:
        raise RuntimeError("AE Cars: geen wagens gevonden, paginastructuur gewijzigd?")
    cars = []
    for url, slug, foto, titel, specs, prijs in tegels:
        titel = _tekst(titel)
        tl = (titel + " " + slug).lower()
        # enkel 911-familie met gts/turbo; de tracker filtert verder
        if "porsche" not in tl or not re.search(r"911|991|992", tl) or not re.search(r"gts|turbo", tl):
            continue
        m = re.search(r"([\d.]+)\s*pk", specs)
        pk = _int(m.group(1)) if m else None
        m = re.search(r"([\d.]+)\s*km", specs)
        km = _int(m.group(1)) if m else None
        m = re.search(r"(\d{4})\s*$", specs)
        jaar = int(m.group(1)) if m else None
        if len(cars) >= 29:  # beleefd blijven: max ~30 verzoeken per run
            break
        time.sleep(1)
        page = get(url)
        if "c_d_table" not in page:
            raise RuntimeError("AE Cars: detailpagina onherkenbaar: " + url)
        inschr = re.search(r"(\d{1,2})/(\d{4})", _veld(page, "1ste inschrijving"))
        co2 = re.search(r'uitstoot</div>\s*<div class="c_d_head">\s*<span[^>]*>\s*(\d+)', page)
        if not pk:  # val terug op vermogen in pk of kW op de detailpagina
            m = re.search(r'vermogen</div>\s*<div class="c_d_head">\s*<span[^>]*>\s*(\d+)\s*</span>\s*(pk|kw)', page, re.I)
            if m:
                pk = int(m.group(1)) if m.group(2).lower() == "pk" else round(int(m.group(1)) * 1.36)
        omschr = re.search(r'<div class="xb text_content">(.*?)</div>', page, re.S)
        transmissie = _veld(page, "transmissie").lower()
        cars.append({
            "id": "aecars-" + slug.strip("-"),
            "bron": NAAM,
            "titel": titel,
            "prijs": _int(prijs),  # geen cijfers = prijs op aanvraag → None
            "km": km or 0,
            "jaar": int(inschr.group(2)) if inschr else jaar,
            "maand": int(inschr.group(1)) if inschr and 1 <= int(inschr.group(1)) <= 12 else 6,
            "pk": pk,
            "manueel": "manu" in transmissie or (not transmissie and "manueel" in tl),
            "co2": int(co2.group(1)) if co2 and int(co2.group(1)) else None,
            "land": "BE",
            "plaats": "Kuurne",
            "verkoper": NAAM,
            "dealer": True,
            "foto": foto.split(",")[0].strip() or None,
            "url": url,
            "_tekst": " ".join([titel, slug.replace("-", " "), _tekst(omschr.group(1)) if omschr else ""]).lower(),
        })
    return cars
