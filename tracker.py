#!/usr/bin/env python3
"""Porsche 911 GTS / Turbo / Turbo S (Cabriolet + Targa) tracker.

Haalt advertenties op van AutoScout24 (BE/NL/DE), Belgische dealersites (bronnen/)
en 2dehands.be, voegt dezelfde auto op meerdere sites samen, berekent een
geschatte Vlaamse BIV en een score (waardebehoud + prijs t.o.v. de markt),
en schrijft een dashboard (dashboard.html). Bij nieuwe toppers volgt een Mac-melding.

Alleen standaardbibliotheek, werkt met de Python 3.9 die macOS meelevert.
"""
import importlib
import json
import re
import secrets
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text())
TEMPLATE = ROOT / "dashboard_template.html"
# Gegevens buiten ~/Documents: macOS laat geplande taken daar niet in (zie install.sh).
DATA_DIR = Path.home() / "Library" / "Application Support" / "porsche-tracker"
STATE_FILE = DATA_DIR / "state.json"
DASHBOARD = DATA_DIR / "dashboard.html"
# Geheime ntfy-kanaalnaam: wie hem kent, kan meelezen. Staat bewust niet in de repo.
NTFY_TOPIC_FILE = DATA_DIR / "ntfy_topic.txt"

ECHTE_GTS = re.compile(r"carrera\s*(4\s*)?gts|targa\s*(4\s*)?gts|\b4\s*gts|\bgts\s*cabr|99[12](\.\d)?\s*gts"
                       r"|\d\.\d\s*gts|^gts")
OPEN_DAK = re.compile(r"cabr|targa|convertible|verdeck|soft\s*-?top|stoffdach|stoffen dak")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "nl-BE,nl;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def to_int(s):
    digits = re.sub(r"[^\d]", "", str(s or ""))
    return int(digits) if digits else None


# ---------------------------------------------------------------- bronnen

def fetch_autoscout():
    # Targa's staan vaak als "Cabriolet" ingegeven, soms niet: daarom een extra zoekopdracht.
    cars, ids = [], set()
    for zoek in ({"mmmv": "57||70|GTS", "body": "2"}, {"mmmv": "57||70|Targa 4 GTS"},
                 {"mmmv": "57||70|Turbo", "body": "2"}):
        for c in fetch_autoscout_zoek(zoek):
            if c["id"] not in ids:
                ids.add(c["id"])
                cars.append(c)
    return cars


def fetch_autoscout_zoek(zoek):
    params = {
        "atype": "C", **zoek,
        "cy": ",".join(CONFIG["landen_autoscout"]),
        "kmto": CONFIG["max_km"], "priceto": CONFIG["max_prijs"],
        "fregfrom": CONFIG["vanaf_bouwjaar"], "ustate": "N,U",
        "sort": "age", "desc": "1",
    }
    cars, page = [], 1
    while page <= 10:
        url = "https://www.autoscout24.be/nl/lst/porsche?" + urllib.parse.urlencode({**params, "page": page})
        html = get(url)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        pp = json.loads(m.group(1))["props"]["pageProps"]
        for l in pp["listings"]:
            v, tr = l["vehicle"], l.get("tracking", {})
            details = {d.get("ariaLabel"): d.get("data") for d in l.get("vehicleDetails", [])}
            reg = tr.get("firstRegistration") or ""          # "06-2017"
            mon, _, yr = reg.partition("-")
            co2 = next((to_int(w) for w in l.get("wltpValues", []) if "g/km" in w and to_int(w)), None)
            seller = l.get("seller", {})
            cars.append({
                "id": "as-" + l["id"],
                "bron": "AutoScout24",
                "titel": f'{v.get("variant") or ""} – {v.get("modelVersionInput") or ""}'.strip(" –"),
                "prijs": l["price"].get("priceRaw"),
                "km": to_int(tr.get("mileage")) or to_int(v.get("mileageInKm")) or 0,
                "jaar": int(yr) if yr.isdigit() else None,
                "maand": int(mon) if mon.isdigit() else 6,
                "pk": to_int((details.get("Vermogen") or "").split("(")[-1]),
                "manueel": (v.get("transmission") or "").lower().startswith("manu"),
                "co2": co2,
                "land": l["location"].get("countryCode"),
                "plaats": l["location"].get("city"),
                "verkoper": seller.get("companyName") or seller.get("contactName") or "",
                "dealer": seller.get("type") == "Dealer",
                "foto": (l.get("images") or [None])[0],
                "url": "https://www.autoscout24.be" + l["url"],
            })
        if page >= pp.get("numberOfPages", 1):
            break
        page += 1
        time.sleep(2)
    return cars


def fetch_2dehands():
    listings = {}
    for query in ("gts", "turbo"):
        url = ("https://www.2dehands.be/lrp/api/search?l1CategoryId=91&l2CategoryId=144"
               f"&limit=100&offset=0&query={query}&viewOptions=list-view")
        for l in json.loads(get(url)).get("listings", []):
            listings[l["itemId"]] = l
    cars = []
    for l in listings.values():
        a = {x["key"]: x.get("value") for x in l.get("attributes", [])}
        title = l.get("title", "")
        txt = (title + " " + l.get("description", "")).lower()
        if not re.search(r"gts|turbo", title.lower()) or not re.search(r"911|991|992", title):
            continue
        if a.get("body") != "Cabriolet" and "cabrio" not in txt and "targa" not in txt:
            continue
        price = (l.get("priceInfo", {}).get("priceCents") or 0) // 100
        pk = re.search(r"(\d{3})\s*(pk|cv|ps)\b", txt)
        foto = (l.get("imageUrls") or [None])[0]
        cars.append({
            "id": "2dh-" + l["itemId"],
            "bron": "2dehands",
            "titel": title,
            "prijs": price,
            "km": to_int(a.get("mileage")) or 0,
            "jaar": to_int(a.get("constructionYear")),
            "maand": 6,
            "pk": int(pk.group(1)) if pk else None,
            "manueel": a.get("transmission") == "Handgeschakeld",
            "co2": None,
            "land": "BE" if not l.get("location", {}).get("abroad") else "?",
            "plaats": l.get("location", {}).get("cityName"),
            "verkoper": l.get("sellerInformation", {}).get("sellerName", ""),
            "dealer": bool(l.get("sellerInformation", {}).get("sellerLogoUrl")),
            "foto": ("https:" + foto) if foto and foto.startswith("//") else foto,
            "url": "https://www.2dehands.be" + l.get("vipUrl", ""),
            "_tekst": txt,
        })
    return cars


# ---------------------------------------------------------------- verrijken

def echt_open_dak(car, cache):
    """Het carrosserietype in het keuzemenu klopt niet altijd (coupé als 'Cabriolet' ingegeven).
    Staat cabrio/targa niet in de eigen tekst van de verkoper, dan lezen we de omschrijving."""
    eigen = car["titel"].split(" – ", 1)[-1] + " " + car.get("_tekst", "")
    if OPEN_DAK.search(eigen.lower()):
        return True
    if car["id"] in cache:
        return cache[car["id"]]
    try:
        html = get(car["url"])
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        desc = json.loads(m.group(1))["props"]["pageProps"]["listingDetails"].get("description") or ""
    except Exception:
        return True  # bij een ophaalfout niet weggooien (en niet onthouden)
    cache[car["id"]] = bool(OPEN_DAK.search(desc.lower()))
    time.sleep(1)
    return cache[car["id"]]


def zelfde_auto(a, b):
    """Dezelfde wagen op twee sites: zelfde model en bouwjaar, km bijna gelijk (sites ronden
    soms af) en prijs binnen 10% (dealer vraagt op eigen site soms minder). De bak vergelijken
    we niet: dealersites vermelden die niet altijd betrouwbaar."""
    return (a["model"] == b["model"] and a["jaar"] == b["jaar"]
            and abs(a["km"] - b["km"]) <= max(500, a["km"] * 0.02)
            and abs(a["prijs"] - b["prijs"]) <= a["prijs"] * 0.10)


def model(car):
    """GTS, Turbo of Turbo S — of None. Veel Carrera's heten '3.0 Turbo' (de motor),
    een echte 911 Turbo herken je aan het vermogen: minstens 520 pk (Carrera max. 480)."""
    t, pk = car["titel"].lower(), car["pk"] or 0
    if "turbo" in t and pk >= 500 and not ECHTE_GTS.search(t):
        s = re.search(r"turbo\s*s\b", t) or pk in (560, 650) or (pk == 580 and (car["jaar"] or 0) < 2020)
        return "Turbo S" if s else "Turbo"
    if ECHTE_GTS.search(t):
        return "GTS"
    return None


def generatie(car):
    t, pk, y = car["titel"].lower(), car["pk"] or 0, car["jaar"] or 0
    if "992" in t:
        return "992"
    if "991.2" in t or "991/2" in t:
        return "991.2"
    if "991.1" in t:
        return "991.1"
    if car["model"] == "GTS":
        if pk >= 470:
            return "992"
        if pk in (450, 449):
            return "991.2"
        if pk in (430, 431):
            return "991.1"
        return "991.1" if y <= 2016 else ("991.2" if y <= 2020 else "992")
    # Turbo: 991.1 = 520/560 pk, 991.2 = 540/580 pk, 992 = 580/650 pk (vanaf 2020)
    if pk in (519, 520, 521, 560):
        return "991.1"
    if pk == 540 or (pk == 580 and y < 2020):
        return "991.2"
    if pk in (580, 650):
        return "992"
    return "991.1" if y <= 2015 else ("991.2" if y <= 2019 else "992")


def biv(car):
    """Geschatte Vlaamse BIV (privé): (((CO2*f*q)/246)^6*4500 + c) * LC."""
    b = CONFIG["biv"]
    std = b["co2_standaard"][car["model"]][car["generatie"]]
    if isinstance(std, dict):  # GTS: verschil manueel/PDK; Turbo is altijd PDK
        std = std["manueel" if car["manueel"] else "pdk"]
    co2 = car["co2"] or std
    today = date.today()
    months = (today.year - (car["jaar"] or today.year)) * 12 + today.month - car["maand"]
    leeftijd = max(0, months // 12)
    lc = [1.0, .9, .8, .7, .6, .54, .48, .42, .36, .3, .24, .18, .12, .06, .01]
    factor = lc[leeftijd] if leeftijd < len(lc) else 0
    if factor == 0:
        return round(b["minimum"]), co2, leeftijd
    raw = ((co2 * b["f_benzine"] * b["q"]) / 246) ** 6 * 4500 + b["c_euro6"]
    raw = min(raw, b["maximum"])
    return round(max(raw * factor, b["minimum"])), co2, leeftijd


def solve(a, y):
    """Kleinste kwadraten via normaalvergelijkingen (zonder numpy)."""
    n = len(a[0])
    ata = [[sum(r[i] * r[j] for r in a) + (1e-6 if i == j else 0) for j in range(n)] for i in range(n)]
    aty = [sum(r[i] * v for r, v in zip(a, y)) for i in range(n)]
    for i in range(n):  # Gauss-eliminatie
        p = max(range(i, n), key=lambda k: abs(ata[k][i]))
        ata[i], ata[p], aty[i], aty[p] = ata[p], ata[i], aty[p], aty[i]
        for k in range(i + 1, n):
            f = ata[k][i] / ata[i][i]
            ata[k] = [x - f * z for x, z in zip(ata[k], ata[i])]
            aty[k] -= f * aty[i]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (aty[i] - sum(ata[i][j] * x[j] for j in range(i + 1, n))) / ata[i][i]
    return x


def features(c):
    return [1, c["leeftijd_jr"], c["km"] / 10000, 1 if c["manueel"] else 0, 1 if c["generatie"] == "992" else 0,
            1 if c["type"] == "Targa" else 0, 1 if c["model"] == "Turbo" else 0, 1 if c["model"] == "Turbo S" else 0]


def import_kosten(car):
    """Geschatte kosten om een buitenlandse auto hier in te schrijven (transport, keuring, COC, platen)."""
    k = CONFIG["import_kosten"]
    return k.get(car["land"], k["anders"])


def score(cars):
    """Marktprijs en korting rekenen met de prijs 'in België' (vraagprijs + importkosten),
    zodat een Duitse auto die €1.500 goedkoper lijkt niet als koopje telt."""
    s = CONFIG["score"]
    usable = [c for c in cars if c["prijs"] and c["jaar"]]
    landed = lambda c: c["prijs"] + c["import_kosten"]
    coef = solve([features(c) for c in usable], [landed(c) for c in usable]) if len(usable) >= 8 else None
    for c in cars:
        pts = 50.0
        why = []
        if coef:
            c["marktprijs"] = round(sum(a * b for a, b in zip(coef, features(c))), -2)
            deal = (c["marktprijs"] - landed(c)) / c["marktprijs"]
            d = max(-s["deal_max"], min(s["deal_max"], deal * s["deal_factor"]))
            pts += d
            c["deal_pct"] = round(deal * 100, 1)
            why.append(f'{"onder" if deal > 0 else "boven"} marktprijs ({deal*100:+.0f}%)')
        txt = (c["titel"] + " " + c.get("_tekst", "")).lower()
        if c["manueel"]:
            pts += s["manueel"]; why.append("manuele bak")
        if c["generatie"] == "991.1" and c["model"] == "GTS":
            pts += s["atmo_991_1"]; why.append("991.1: laatste atmosferische 3.8")
        if c["land"] == "BE":
            pts += s["belgie"]; why.append("Belgische auto")
        if "approved" in txt:
            pts += s["porsche_approved"]; why.append("Porsche Approved")
        if re.search(r"porsche (zentrum|centre|center|centrum)", c["verkoper"].lower()):
            pts += s["porsche_centre"]; why.append("Porsche Centre")
        if "chrono" in txt or "sportuitlaat" in txt or "abgas" in txt or "sport exhaust" in txt:
            pts += s["chrono_of_uitlaat_vermeld"]
        if c["dagen_online"] >= s["lang_online_dagen"]:
            pts += s["lang_online"]; why.append(f'{c["dagen_online"]} dagen te koop: ruimte om te onderhandelen')
        pts += max(0, (CONFIG["max_km"] - c["km"]) / CONFIG["max_km"]) * s["lage_km_max"]
        pts -= min(1, c["biv"] / CONFIG["max_biv"]) * s["biv_straf_max"]
        c["score"] = round(max(0, min(100, pts)))
        c["waarom"] = why


# ---------------------------------------------------------------- hoofdlus

def melding(msg, knop_dashboard=True):
    """Venster met geluid i.p.v. een macOS-notificatie: die worden vanuit scripts vaak stil
    tegengehouden (Scripteditor zonder toestemming) en openen bij klikken niet het dashboard."""
    msg = msg.replace("\\", "").replace('"', "'")
    knoppen = '{"Later", "Open dashboard"} default button "Open dashboard"' if knop_dashboard else '{"OK"}'
    subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
    r = subprocess.run(["osascript", "-e", f'display dialog "{msg}" with title "Porsche GTS tracker" '
                        f'buttons {knoppen} with icon note giving up after 3600'],
                       capture_output=True, text=True, check=False)
    if "Open dashboard" in r.stdout:
        subprocess.run(["open", str(DASHBOARD)], check=False)


def ntfy_topic():
    if not NTFY_TOPIC_FILE.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        NTFY_TOPIC_FILE.write_text("porsche-" + secrets.token_urlsafe(18) + "\n")
    return NTFY_TOPIC_FILE.read_text().strip()


def push(titel, tekst, url=None, prioriteit=3):
    """Pushmelding naar de ntfy-app op je gsm (abonneer je op het kanaal uit ntfy_topic.txt).
    JSON i.p.v. headers zodat € en andere tekens gewoon werken. Een fout mag de run niet stoppen."""
    bericht = {"topic": ntfy_topic(), "title": titel, "message": tekst, "priority": prioriteit, "tags": ["red_car"]}
    if url:
        bericht["click"] = url
    try:
        req = urllib.request.Request("https://ntfy.sh", data=json.dumps(bericht).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15).close()
    except Exception as e:
        print(f"Pushmelding mislukt: {e}")


def push_auto(c):
    reden = "Prijsdaling" if not c["nieuw"] else "Nieuw"
    push(f"{reden}: {c['model']} {c['type']} {c['generatie']} – score {c['score']}",
         auto_regel(c).lstrip("• ") + f"\nAll-in ±€{c['all_in']:,} (incl. BIV €{c['biv']:,}".replace(",", ".")
         + (f" + import €{c['import_kosten']:,}".replace(",", ".") if c["import_kosten"] else "")
         + f") · {c['bron']}",
         url=c["url"], prioriteit=4)


def auto_regel(c):
    return (f"• {c['model']} {c['type']} {c['generatie']} {c['jaar']}, {c['km']:,} km, "
            f"€{c['prijs']:,} – score {c['score']}").replace(",", ".")


def dealer_bronnen():
    """Elke module in bronnen/ (bv. bronnen/dct.py) met NAAM en fetch(get) is een dealersite."""
    sys.path.insert(0, str(ROOT))
    bronnen = []
    for f in sorted((ROOT / "bronnen").glob("[!_]*.py")):
        mod = importlib.import_module(f"bronnen.{f.stem}")
        bronnen.append((mod.NAAM, lambda mod=mod: mod.fetch(get)))
    return bronnen


def bron_bewaking(aantallen, historiek):
    """Een site die haar opbouw wijzigt, geeft vaak geen fout maar stil (bijna) 0 auto's.
    Vergelijk met de mediaan van de vorige runs. Kleine dealers (mediaan < 3) slaan we over:
    daar is 0 vaak echt 0, en hun module geeft zelf een fout als de structuur verandert."""
    waarschuwingen = []
    for naam, n in aantallen.items():
        vorige = historiek.get(naam, [])
        if len(vorige) >= 4:
            med = sorted(vorige)[len(vorige) // 2]
            if med >= 3 and n < med * 0.4:
                waarschuwingen.append(f"{naam}: maar {n} advertenties (normaal ±{med}), site gewijzigd?")
        historiek[naam] = (vorige + [n])[-10:]
    return waarschuwingen


def markt_punt(cars, markt, vandaag):
    """Mediaan-vraagprijs per model + generatie, één punt per dag (laatste run van de dag telt)."""
    groepen = {}
    for c in cars:
        groepen.setdefault(f'{c["model"]}|{c["generatie"]}', []).append(c["prijs"])
    segmenten = {k: {"mediaan": sorted(v)[len(v) // 2], "aantal": len(v)} for k, v in groepen.items()}
    markt = [m for m in markt if m["datum"] != vandaag]
    return markt + [{"datum": vandaag, "segmenten": segmenten}]


def main():
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"auto": {}}
    typecheck = state.get("typecheck", {})
    errors, cars, aantallen = [], [], {}
    # volgorde = voorkeur bij dubbels: AutoScout24 heeft de rijkste gegevens (CO2, pk)
    for name, fn in [("AutoScout24", fetch_autoscout)] + dealer_bronnen() + [("2dehands", fetch_2dehands)]:
        try:
            gevonden = fn()
            cars += gevonden
            aantallen[name] = len(gevonden)
        except Exception as e:  # één bron die faalt mag de rest niet stoppen
            errors.append(f"{name}: {e}")
    bron_historiek = state.get("bronnen", {})
    errors += bron_bewaking(aantallen, bron_historiek)

    # filter + dubbels (zelfde auto op meerdere sites) samenvoegen
    uniek = []
    for c in cars:
        t = c["titel"].lower()
        if not c["prijs"] or c["prijs"] > CONFIG["max_prijs"] or c["km"] > CONFIG["max_km"]:
            continue
        if (c["jaar"] or 0) < CONFIG["vanaf_bouwjaar"] or "boxster" in t:
            continue
        c["model"] = model(c)
        if not c["model"]:  # bv. "Carrera 4S ... GTS Carbon-pakket" of "Carrera 3.0 Turbo"
            continue
        if c["bron"] not in ("AutoScout24", "2dehands") and not OPEN_DAK.search((t + " " + c.get("_tekst", "")).lower()):
            continue  # dealersites: geen carrosserie-menu, dus cabrio/targa moet in de tekst staan
        dubbel = next((p for p in uniek if zelfde_auto(p, c)), None)
        if dubbel:  # zelfde auto op een andere site: één kaart, laagste prijs, alle links
            if not any(s["bron"] == c["bron"] and s["prijs"] == c["prijs"] for s in dubbel["te_koop_op"]):
                dubbel["te_koop_op"].append({"bron": c["bron"], "url": c["url"], "prijs": c["prijs"]})
            dubbel["prijs"] = min(dubbel["prijs"], c["prijs"])
            continue
        if c["bron"] == "AutoScout24" and not echt_open_dak(c, typecheck):
            continue
        c["te_koop_op"] = [{"bron": c["bron"], "url": c["url"], "prijs": c["prijs"]}]
        c["generatie"] = generatie(c)
        c["type"] = "Targa" if "targa" in t or "targa" in c.get("_tekst", "") else "Cabrio"
        c["biv"], c["co2_gebruikt"], c["leeftijd_jr"] = biv(c)
        uniek.append(c)

    now = datetime.now().isoformat(timespec="minutes")
    for c in uniek:
        old = state["auto"].get(c["id"])
        if old:
            c["eerst_gezien"] = old["eerst_gezien"]
            c["prijshistoriek"] = old["prijshistoriek"]
            if c["prijshistoriek"][-1][1] != c["prijs"]:
                c["prijshistoriek"].append([now, c["prijs"]])
        else:
            c["eerst_gezien"] = now
            c["prijshistoriek"] = [[now, c["prijs"]]]
        eerste = c["prijshistoriek"][0][1]
        c["prijsdaling_pct"] = round((eerste - c["prijs"]) / eerste * 100, 1) if eerste else 0
        c["nieuw"] = not old
        c["dagen_online"] = (date.today() - date.fromisoformat(c["eerst_gezien"][:10])).days
        # na het samenvoegen van dubbels: prijs = laagste van alle sites
        c["import_kosten"] = import_kosten(c)
        c["all_in"] = c["prijs"] + c["biv"] + c["import_kosten"]
    score(uniek)

    nieuw_top = []
    for c in uniek:
        old = state["auto"].get(c["id"])
        c.pop("_tekst", None)
        interessant = c["score"] >= CONFIG["melding_vanaf_score"] and c["biv"] <= CONFIG["max_biv"]
        gedaald = old and old["prijs"] - c["prijs"] >= old["prijs"] * CONFIG["melding_bij_prijsdaling_pct"] / 100
        if interessant and (not old or gedaald) and state.get("laatste_run"):
            nieuw_top.append(c)

    markt = markt_punt(uniek, state.get("markt", []), now[:10])
    state = {"laatste_run": now, "fouten": errors, "typecheck": typecheck, "bronnen": bron_historiek, "markt": markt,
             "auto": {c["id"]: {k: c[k] for k in ("eerst_gezien", "prijshistoriek", "prijs")} for c in uniek}}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1))

    uniek.sort(key=lambda c: -c["score"])
    payload = {"bijgewerkt": now, "fouten": errors, "config": CONFIG, "autos": uniek, "markt": markt}
    DASHBOARD.write_text(TEMPLATE.read_text().replace("/*__DATA__*/null", json.dumps(payload)))

    print(f"{now}: {len(uniek)} auto's, {len(nieuw_top)} nieuwe toppers, fouten: {errors or 'geen'}")
    if "--geen-melding" in sys.argv:
        return
    if nieuw_top:
        nieuw_top.sort(key=lambda c: -c["score"])
        regels = "\n".join(auto_regel(c) for c in nieuw_top[:5])
        meer = f"\n… en nog {len(nieuw_top) - 5}" if len(nieuw_top) > 5 else ""
        for c in nieuw_top[:5]:
            push_auto(c)
        if len(nieuw_top) > 5:
            push("Porsche-tracker", f"… en nog {len(nieuw_top) - 5} andere: zie dashboard")
        melding(f"{len(nieuw_top)} nieuwe interessante auto('s) of prijsdaling:\n\n{regels}{meer}")
    elif errors:
        push("Porsche-tracker: fout bij ophalen", "; ".join(errors)[:300], prioriteit=2)
        melding("Fout bij ophalen: " + "; ".join(errors)[:200], knop_dashboard=False)


if __name__ == "__main__":
    if "--test-melding" in sys.argv:
        push("Testmelding: GTS Cabrio 991.1 – score 80",
             "GTS Cabrio 991.1 2015, 34.859 km, €105.800 – score 80\nZo ziet een melding op je gsm eruit.",
             url="https://ntfy.sh/" + ntfy_topic())
        melding("Testmelding: zo ziet een melding eruit.\n\n"
                "• GTS Cabrio 991.1 2015, 34.859 km, €105.800 – score 80")
    else:
        main()
