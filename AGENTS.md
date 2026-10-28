# porsche-tracker

Zoekt 2x per dag (08:00 en 18:00, via launchd) naar 2dehands Porsche 911 GTS en Turbo (S), Cabriolet en Targa (991/992)
op AutoScout24 (BE/NL/DE), 2dehands.be en Belgische dealersites (Lampe, AE Cars, DCT, Bavaria Motors, Autofest), en schrijft een dashboard met score + geschatte Vlaamse BIV.

- `tracker.py` – ophalen, filteren, BIV, score, dashboard, Mac-melding (alleen stdlib, Python 3.9)
- `bronnen/<dealer>.py` – één module per dealersite: `NAAM` + `fetch(get)` → lijst auto-dicts (zelfde velden als in tracker.py). Nieuwe dealer = nieuw bestand, wordt automatisch opgepikt. Alleen Belgische dealers.
- Dubbels (zelfde auto op meerdere sites, ook 2x op AutoScout24) worden samengevoegd via `zelfde_auto()`: één kaart, laagste prijs, alle sites in `te_koop_op`.
- `config.json` – criteria, scoregewichten, BIV-parameters (q/c jaarlijks nakijken, indexatie 1 juli/1 jan)
- `dashboard_template.html` – dashboard; `/*__DATA__*/null` wordt vervangen door de data
- `install.sh` – kopieert naar `~/Library/Application Support/porsche-tracker` en plant de launchd-taak
  (macOS laat geplande taken niet in ~/Documents). **Na elke wijziging opnieuw `./install.sh` draaien.**
- `dashboard.html` – symlink naar het gegenereerde dashboard; log: `~/Library/Application Support/porsche-tracker/tracker.log`

Melding (+ dashboard opent) bij een nieuwe auto met score ≥ `melding_vanaf_score` en BIV ≤ `max_biv`,
of bij een prijsdaling ≥ `melding_bij_prijsdaling_pct`. Mobile.de zit er niet in (bot-blokkering).
