# Porsche GTS/Turbo tracker (porsche-tracker)

Zoekt 2x per dag (08:00 en 18:00, via launchd) naar 2dehands Porsche 911 GTS en Turbo (S), Cabriolet en Targa (991/992)
op AutoScout24 (BE/NL/DE/LU), 2dehands.be en Belgische dealersites (Lampe, AE Cars (WordPress-API), DCT, Bavaria Motors, Autofest), en schrijft een dashboard met score + geschatte Vlaamse BIV.

- `tracker.py` – ophalen, filteren, BIV, score, dashboard, Mac-melding (alleen stdlib, Python 3.9)
- `bronnen/<dealer>.py` – één module per dealersite: `NAAM` + `fetch(get)` → lijst auto-dicts (zelfde velden als in tracker.py). Nieuwe dealer = nieuw bestand, wordt automatisch opgepikt. Alleen Belgische dealers.
- Dubbels (zelfde auto op meerdere sites, ook 2x op AutoScout24) worden samengevoegd via `zelfde_auto()`: één kaart, laagste prijs, alle sites in `te_koop_op`.
- `config.json` – criteria, scoregewichten, BIV-parameters (q/c jaarlijks nakijken, indexatie 1 juli/1 jan)
- `dashboard_template.html` – dashboard; `/*__DATA__*/null` wordt vervangen door de data
- **Planning**: launchd start `tracker.py --gepland` elke 15 min; `run_nodig()` draait alleen als het laatste vaste moment
  (08:00/18:00, `RUN_UREN`) nog niet gelukt is (`laatste_geslaagde_run` in state.json) en `internet()` werkt.
  Zo wordt een run ingehaald als de Mac sliep of net wakker werd zonder wifi. Alle bronnen mislukt = geen foutmelding, nieuwe poging.
- `install.sh` – kopieert naar `~/Library/Application Support/porsche-tracker` en plant de launchd-taak
  (macOS laat geplande taken niet in ~/Documents). **Na elke wijziging opnieuw `./install.sh` draaien.**
- **Bronbewaking** (`bron_bewaking()`): aantal advertenties per bron wordt bijgehouden in state.json; valt een grote bron
  (mediaan ≥ 3) terug onder 40% van normaal, dan komt er een waarschuwing (dashboard + melding). Kleine dealers geven zelf een fout.
- **All-in prijs** = vraagprijs + BIV + `import_kosten` (per land, config.json). Marktprijs en korting rekenen met vraagprijs + import.
- **Dagen online** = sinds de tracker de advertentie eerst zag; vanaf `lang_online_dagen` een kleine bonus (onderhandelingsruimte).
- **Marktgrafiek**: `markt_punt()` bewaart per dag de mediaan-vraagprijs per model|generatie in state.json → dashboard
  (`perPeriode()` toont per 14 dagen de mediaan van de dagpunten; opslag blijft per dag).
- **Verkochte auto's**: een auto die niet meer gevonden wordt op een site die wél werkte, verdwijnt meteen uit het
  dashboard en gaat 60 dagen naar `verkocht` in state.json (komt hij terug, dan is hij niet "nieuw" → geen dubbele melding).
  Lag de site plat (fout of bronbewaking), dan blijft de auto staan met de gegevens van de vorige run (tag "SITE OFFLINE").
  Advertenties met "verkocht/sold/gereserveerd" in de titel worden overgeslagen.
- **Favorieten / verbergen / notities** staan alleen in de browser (localStorage `porsche-mijn`), niet in Python:
  verborgen auto's geven dus nog wel meldingen.
- **Knop "Nu zoeken"** (dashboard): `knop.py` is een stdlib-hulpserver op 127.0.0.1:8911 (eigen launchd-agent, KeepAlive)
  die `tracker.py` start. Alleen Origin `null` (file://) of geen Origin mag een run starten. Een slot (`tracker.lock`, flock)
  voorkomt dat een geplande en manuele run tegelijk lopen; het slot gaat los na het schrijven van het dashboard,
  zodat een open meldingsvenster niets blokkeert. Draait de hulpserver niet, dan is de knop verborgen.
- `dashboard.html` – symlink naar het gegenereerde dashboard; log: `~/Library/Application Support/porsche-tracker/tracker.log`

Melding (venster met geluid + knop "Open dashboard"; macOS-notificaties worden vanuit scripts tegengehouden) bij een nieuwe auto met score ≥ `melding_vanaf_score` en BIV ≤ `max_biv`,
of bij een prijsdaling ≥ `melding_bij_prijsdaling_pct` (melding toont oude prijs + bedrag via `daling()`;
het dashboard toont dalingen van de laatste 7 dagen in een blok bovenaan, klik = naar de kaart).
Daarnaast een pushmelding naar de gsm via ntfy.sh (`push()` in tracker.py, één melding per auto, tik = advertentie).
De geheime kanaalnaam staat in `~/Library/Application Support/porsche-tracker/ntfy_topic.txt` (nooit in de repo).
Testen: `python3 tracker.py --test-melding` (Mac-venster + gsm).
Manueel pushen: knop "📲 Push" op elke kaart in het dashboard stuurt de auto (+ optionele opmerking) naar het kanaal;
het kanaal komt via `ntfy_topic` in de payload alleen in het lokale, gegenereerde dashboard (niet in het template/git).

## Kost, bod, verkoopsnelheid, samenvatting, vergelijken
- **Kost per jaar** (`totale_kost()`): afschrijving over `kost_jaren` volgens de waardecurve van het model
  (prijs × r(a+jaren)/r(a)) + BIV + import + verkeersbelasting + `onderhoud_per_jaar`, gedeeld door de jaren. Geen verzekering.
- **Verkeersbelasting** (`verkeersbelasting()`): tarief per fiscale pk uit config.json (jaarlijks op 1 juli indexeren!)
  + 10% opdeciem; vanaf bouwjaar 2021 CO2/euronorm-correctie. 3.0 l = 15 pk, 3.7/3.8 l = 19 pk.
- **Bod** (`biedvoorstel()`): plafond = min(vraagprijs, marktprijs − import); startbod = plafond − ruimte (config `bod`).
- **Verkoopsnelheid** (`verkoopsnelheid()`): elke verdwenen auto gaat (blijvend, max 1000) naar `verkoop_historiek` in
  state.json; mediaan dagen per model|generatie(|bak). Auto's die er al stonden bij `gestart` tellen niet mee.
- **Weekoverzicht** (`samenvatting()`): push bij de eerste run na 17u op `samenvatting_dag` (zondag);
  nu testen: `python3 tracker.py --samenvatting` (stuurt echt naar het kanaal).
- **Vergelijken**: knop op de kaart, max 3, alleen in het geheugen van de pagina (niet bewaard).

## Keuzes & bewust niet

Bewuste beslissingen: niet "verbeteren" zonder dat te vragen.

- **Draait lokaal op de Mac (launchd), niet in de cloud.** Een online PWA (GitHub Actions + Supabase + Vercel) is
  overwogen, maar lokaal volstaat; bovendien blokkeren AutoScout24/2dehands vaak datacenter-IP's.
  Nadeel dat we aanvaarden: de Mac moet om 08:00/18:00 aanstaan (of draait de run zodra hij wakker wordt).
- **Gsm-meldingen via ntfy.sh, geen Web Push/PWA.** Geen account, geen server, geen extra pakketten nodig.
- **Alleen Python-stdlib (3.9)**: geen `pip install`, zodat het met `/usr/bin/python3` blijft draaien.
- **Geen Mobile.de, Porsche Finder of Elferspot**: bot-blokkering (Porsche Finder: Vercel Security Checkpoint;
  Elferspot: Bunny Shield + `Crawl-delay: 10`; getest okt. 2026). Niet proberen te omzeilen.
  Porsche Approved-wagens staan meestal ook op AutoScout24; voor Elferspot: hun eigen e-mailalert ("save search").
- **Alleen Belgische dealersites** in `bronnen/`; buitenlands aanbod komt via AutoScout24.
- **Mac-melding is een dialoogvenster**, geen notificatie: notificaties vanuit scripts worden stil tegengehouden.
- **Repo is openbaar**: nooit geheimen committen (ntfy-kanaal, sleutels); die staan in Application Support.

## Waardecurve en prognose
- `marktstaal()` haalt 1x per dag alle GTS/Turbo cabrio's+targa's vanaf 2014 op AutoScout24 op, zonder prijs-/km-filter,
  per periode (2014–16, 2017–20, 2021–24) wegens de limiet van 10 pagina's. 992.2 (541/711 pk) blijft eruit.
- `waardecurve()` past per model r(a) = f + (1-f)·e^(-k·a) toe (restwaarde t.o.v. `nieuwprijs` × `opties_factor`),
  ijkt per generatie op de mediaan van vandaag en geeft verloop sinds nieuw + prognose 5 jaar (band: k×1.4/f×0.9 tot k×0.6/f×1.1).
  Het verloop is afgeleid uit prijzen per leeftijd vandaag (cross-sectioneel), niet uit echte historische prijzen.
- Verborgen auto's (dashboard, localStorage) komen vanzelf terug als hun prijs lager is dan bij het verbergen (`verborgen_prijs`).
