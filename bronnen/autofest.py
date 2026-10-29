"""Autofest (Oostkamp) – eigen WordPress-site, geen AutoScout24-widget.
Elke wagen is een gewone WP-post: lijst via de WP REST API, specs staan enkel op de detailpagina."""
import html
import json
import re
import time

NAAM = "Autofest"
BASIS = "https://autofestbelgium.be"
LIJST = BASIS + "/wp-json/wp/v2/posts?per_page=100&page={}&_fields=id,slug,link,title,yoast_head_json.og_image"


def _int(s):
    s = re.sub(r"[^\d]", "", s or "")
    return int(s) if s else None


def _regels(pagina):
    """Detailpagina -> lijst zichtbare tekstregels."""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", pagina, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", s))
    return [r.strip() for r in t.split("\n") if r.strip()]


def fetch(get):
    posts = []
    for page in range(1, 4):  # max 300 posts, ruim genoeg
        deel = json.loads(get(LIJST.format(page)))
        if not isinstance(deel, list):
            raise ValueError("Autofest: onverwacht antwoord van wp-json")
        posts += deel
        time.sleep(1)
        if len(deel) < 100:
            break
    if not posts:
        raise ValueError("Autofest: geen wagens gevonden in wp-json")

    cars = []
    for p in posts:
        titel = html.unescape(p.get("title", {}).get("rendered", "")).strip()
        tl = titel.lower()
        # voorfilter: enkel 911-familie met gts/turbo, pas dan de detailpagina ophalen
        if "porsche" not in tl or not re.search(r"911|99[127]", tl) or not re.search(r"gts|turbo", tl):
            continue
        if len(cars) >= 25:
            break  # beleefd blijven
        regels = _regels(get(p["link"]))
        time.sleep(1)
        try:
            start = regels.index(titel) if titel in regels else next(
                i for i, r in enumerate(regels) if r.startswith("€"))
        except StopIteration:
            raise ValueError("Autofest: detailpagina niet herkend: " + p["link"])
        kop = regels[start:start + 15]
        prijs = next((_int(r) for r in kop if re.match(r"€\s*[\d .]+", r)), None)
        datum = next((re.match(r"(\d{1,2})/(\d{4})$", r) for r in kop if re.match(r"\d{1,2}/\d{4}$", r)), None)
        km = next((_int(r) for r in kop if re.match(r"[\d .]+\s*km$", r, re.I)), None)
        vermogen = next((r.lower() for r in kop if re.search(r"\d+\s*(kw|pk)", r, re.I)), "")
        pk = re.search(r"(\d+)\s*pk", vermogen)
        kw = re.search(r"(\d+)\s*kw", vermogen)
        bak = " ".join(kop).lower()
        if datum is None or km is None:
            raise ValueError("Autofest: bouwjaar/km niet gevonden op " + p["link"])
        # opties-lijst als extra tekst (cabrio/targa/chrono herkennen)
        try:
            i = regels.index("Enkele opties:")
            opties = " ".join(regels[i:i + 60]).split("Download")[0]
        except ValueError:
            opties = ""
        foto = ((p.get("yoast_head_json") or {}).get("og_image") or [{}])[0].get("url")
        cars.append({
            "id": "autofest-" + p["slug"],
            "bron": NAAM,
            "titel": titel,
            "prijs": prijs,
            "km": km,
            "jaar": int(datum.group(2)),
            "maand": int(datum.group(1)) if 1 <= int(datum.group(1)) <= 12 else 6,
            "pk": int(pk.group(1)) if pk else (round(int(kw.group(1)) * 1.36) if kw else None),
            "manueel": "manueel" in bak or "handgeschakeld" in bak,
            "co2": None,  # niet vermeld op de site
            "land": "BE",
            "plaats": "Oostkamp",
            "verkoper": NAAM,
            "dealer": True,
            "foto": foto,
            "url": p["link"],
            "_tekst": (titel + " " + " ".join(kop) + " " + opties).lower(),
        })
    return cars
