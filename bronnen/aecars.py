"""AE Cars (Ardooie, voorheen Kuurne) — WordPress-site (sinds okt. 2026).

De lijst komt uit de WordPress-API (/wp-json/wp/v2/cars, alleen titel + link);
prijs, km, pk enz. staan als "label / waarde"-regels op de detailpagina.
"""
import html
import json
import re
import time

NAAM = "AE Cars"
BASIS = "https://aecars.be"
PORSCHE = 9  # id van het merk "porsche" in /wp-json/wp/v2/merk


def _int(s):
    d = re.sub(r"\D", "", s or "")
    return int(d) if d else None


def _regels(page):
    """Detailpagina als lijst tekstregels (Elementor zet elk label en elke waarde in een eigen blok)."""
    t = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", page, flags=re.S)
    return [r.strip() for r in html.unescape(re.sub(r"<[^>]+>", "\n", t)).split("\n") if r.strip()]


def _veld(regels, label):
    """Waarde op de regel na het label (bv. 'km-stand' -> '49.812'); de eerste na de prijs telt."""
    for i, r in enumerate(regels[:-1]):
        if r.lower() == label.lower():
            return regels[i + 1]
    return ""


def fetch(get):
    lijst = json.loads(get(f"{BASIS}/wp-json/wp/v2/cars?merk={PORSCHE}&per_page=100&_fields=slug,link,title"))
    if not lijst:
        raise RuntimeError("AE Cars: geen wagens gevonden, paginastructuur gewijzigd?")
    cars = []
    for x in lijst:
        titel = re.sub(r"\s+", " ", html.unescape(x["title"]["rendered"])).strip()
        tl = (titel + " " + x["slug"]).lower()
        # enkel 911 GTS/Turbo, open dak, 997 of nieuwer: de site geeft "429 Too Many Requests"
        # als we te veel detailpagina's na elkaar ophalen, dus coupés en oudere generaties overslaan
        if not re.search(r"911|99[127]", tl) or not re.search(r"gts|turbo", tl):
            continue
        if not re.search(r"cabr|targa", tl) or re.search(r"\b(930|964|993|996)\b", tl):
            continue
        if len(cars) >= 15:
            break
        time.sleep(4)
        page = get(x["link"])
        regels = _regels(page)
        # alles vóór de prijs is menu/omschrijving; specs staan erna
        p = next((i for i, r in enumerate(regels) if re.fullmatch(r"€\s*[\d.]+,?-?|prijs op aanvraag", r, re.I)), None)
        if p is None or "km-stand" not in regels:
            raise RuntimeError("AE Cars: detailpagina onherkenbaar: " + x["link"])
        specs = regels[p:]
        inschr = re.search(r"(\d{1,2})/(\d{4})$", _veld(specs, "1ste inschrijving"))
        jaar = _int(_veld(specs, "bouwjaar"))
        transmissie = _veld(specs, "Transmissie").lower()
        co2 = _int(_veld(specs, "CO₂"))
        fotos = [u for u in re.findall(r"https://aecars\.be/wp-content/uploads/[^\"' ,]+?\.(?:jpe?g|webp|png)", page)
                 if "logo" not in u.lower()]
        cars.append({
            "id": "aecars-" + x["slug"],
            "bron": NAAM,
            "titel": titel.replace(" – ", " "),
            "prijs": _int(regels[p]),  # geen cijfers = prijs op aanvraag → None
            "km": _int(_veld(specs, "km-stand")) or 0,
            "jaar": int(inschr.group(2)) if inschr else jaar,
            "maand": int(inschr.group(1)) if inschr and 1 <= int(inschr.group(1)) <= 12 else 6,
            "pk": _int(_veld(specs, "vermogen")),
            "manueel": "manu" in transmissie,
            "co2": co2 if co2 and 80 < co2 < 600 else None,  # leeg veld → volgende regel (bv. bouwjaar)
            "land": "BE",
            "plaats": "Ardooie",
            "verkoper": NAAM,
            "dealer": True,
            "foto": fotos[0] if fotos else None,
            "url": x["link"],
            # omschrijving (net vóór de prijs) + specs en optielijst (erna)
            "_tekst": " ".join([titel] + regels[max(0, p - 3):p + 80]).lower(),
        })
    return cars
