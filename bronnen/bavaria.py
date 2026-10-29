"""Bavaria Motors (Harelbeke) - eigen site, geen API: de stockpagina is server-side HTML
met alle wagens op één pagina; km/jaar/pk/transmissie staan enkel op de detailpagina."""
import html
import re
import time

NAAM = "Bavaria Motors"
BASIS = "https://www.bavariamotors.be"
STOCK = BASIS + "/nl/aanbod-te-koop"
MAX_DETAILS = 25  # beleefd blijven: 1 stockpagina + max 25 detailpagina's
MAANDEN = ["jan", "feb", "maa", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


def _int(s):
    d = re.sub(r"\D", "", s or "")
    return int(d) if d else None


def _tekst(s):
    """HTML-fragment naar platte tekst op één regel."""
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _specs(page):
    """Alle label/waarde-paren: <div ..>Label</div> <div ..>Waarde</div>."""
    paren = re.findall(r"<div[^>]*>\s*([^<>]{2,40}?)\s*</div>\s*<div[^>]*>(.*?)</div>", page, re.S)
    return {html.unescape(k).strip().lower(): _tekst(v) for k, v in paren}


def _kaarten(page):
    """Stockpagina: één <a> per wagen met titel, link, foto en prijs."""
    kaarten = {}
    for m in re.finditer(r'<a href="(https://www\.bavariamotors\.be/nl/wagen/(\d+)-[^"]+)" title="([^"]*)"(.*?)</a>',
                         page, re.S):
        url, wid, titel, body = m.groups()
        foto = re.search(r'data-bgset="\s*(https?://[^\s"?]+)', body)
        prijs = re.search(r"€\s*([\d.]+)", body)
        kaarten[wid] = {"url": url, "titel": html.unescape(titel).strip(),
                        "foto": foto.group(1) if foto else None,
                        "prijs": _int(prijs.group(1)) if prijs else None}
    return kaarten


def fetch(get):
    kaarten = _kaarten(get(STOCK))
    if not kaarten:
        raise RuntimeError("Bavaria Motors: geen wagens gevonden op de stockpagina (structuur gewijzigd?)")
    # voorfilter op de titel: Porsche 911/997/991/992 met GTS of Turbo
    kandidaten = [(wid, k) for wid, k in kaarten.items()
                  if re.search(r"porsche", k["titel"], re.I) and re.search(r"\b(911|99[127])", k["titel"])
                  and re.search(r"gts|turbo", k["titel"], re.I)]
    cars = []
    for wid, k in kandidaten[:MAX_DETAILS]:
        time.sleep(1)
        page = get(k["url"])
        s = _specs(page)
        if "kilometerstand" not in s or "eerste registratie" not in s:
            raise RuntimeError("Bavaria Motors: specificaties niet gevonden op " + k["url"])
        reg = s["eerste registratie"].lower()  # bv. "mei 2016"
        jaar = re.search(r"(19|20)\d\d", reg)
        maand = next((i + 1 for i, n in enumerate(MAANDEN) if n in reg), None)
        if not maand:
            mm = re.search(r"\b(\d{1,2})[/-](?:19|20)\d\d", reg)
            maand = int(mm.group(1)) if mm and 1 <= int(mm.group(1)) <= 12 else 6
        verm = s.get("vermogen", "")
        pk = re.search(r"(\d+)\s*pk", verm, re.I)
        kw = re.search(r"(\d+)\s*kw", verm, re.I)
        pk = int(pk.group(1)) if pk else (round(int(kw.group(1)) * 1.36) if kw else None)
        prijs = re.search(r'itemprop="price" content="([\d.]+)"', page)
        prijs = int(float(prijs.group(1))) if prijs and float(prijs.group(1)) > 0 else k["prijs"]
        h1 = re.search(r"<title>(.*?)</title>", page, re.S)
        # beschrijving + opties + extra info: van de specs tot het contactformulier
        # (daarna volgen andere wagens, die zouden cabrio/targa-detectie vervuilen)
        body = _tekst(page[page.find("Eerste registratie"):])
        body = re.split(r"Bekijk alle foto|Interesse in deze", body)[0]
        cars.append({
            "id": "bavaria-" + wid,
            "bron": NAAM,
            "titel": _tekst(h1.group(1)).split(" | ")[0] if h1 else k["titel"],
            "prijs": prijs,
            "km": _int(s["kilometerstand"]) or 0,
            "jaar": int(jaar.group(0)) if jaar else None,
            "maand": maand,
            "pk": pk,
            "manueel": bool(re.search(r"manu|handgesch|schakel", s.get("transmissie", ""), re.I)),
            "co2": _int(s.get("co2-uitstoot")),
            "land": "BE",
            "plaats": "Harelbeke",
            "verkoper": NAAM,
            "dealer": True,
            "foto": k["foto"],
            "url": k["url"],
            "_tekst": (k["titel"] + " " + body).lower(),
        })
    return cars
