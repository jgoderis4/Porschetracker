# Porsche GTS/Turbo tracker

Persoonlijke tool die 2x per dag zoekt naar tweedehands **Porsche 911 GTS en Turbo (S)**, als Cabriolet of Targa
(991/992), en de beste kandidaten rangschikt.

- **Bronnen:** AutoScout24 (BE/NL/DE/LU), 2dehands.be en Belgische dealers (Lampe, AE Cars, DCT, Bavaria Motors, Autofest)
- **Dashboard:** alle auto's met een score, de geschatte Vlaamse BIV, een all-in prijs (incl. importkosten), dagen te koop,
  prijshistoriek en een marktgrafiek per generatie. Favorieten, verbergen en eigen notities per auto.
- **Bronbewaking:** waarschuwing als een site plots veel minder advertenties geeft (site gewijzigd?)
- **Dubbels samengevoegd:** dezelfde auto op meerdere sites wordt één kaart met de laagste prijs
- **Meldingen:** een venster op de Mac en een pushmelding op de gsm (via [ntfy](https://ntfy.sh)) bij een nieuwe topper of een prijsdaling

## Installeren (macOS)

Vereist alleen de Python 3 die bij macOS zit. Geen extra pakketten.

```bash
./install.sh
```

Dit kopieert de code naar `~/Library/Application Support/porsche-tracker` en plant een launchd-taak om 08:00 en 18:00.
Na elke wijziging aan de code of `config.json` voer je `./install.sh` opnieuw uit. Verwijderen kan met `./install.sh --uninstall`.

## Meldingen op je gsm

1. Installeer de app **ntfy** (iOS/Android).
2. Abonneer je op het kanaal uit `~/Library/Application Support/porsche-tracker/ntfy_topic.txt`.
   Dat bestand wordt bij de eerste melding aangemaakt. Houd de naam geheim: wie hem kent, kan meelezen.
3. Test met `python3 tracker.py --test-melding`.

## Aanpassen

- **Zoekcriteria, scoregewichten en BIV-parameters:** `config.json`
- **Nieuwe dealersite:** een nieuw bestand in `bronnen/`, met `NAAM` en `fetch(get)`

Meer technische uitleg en de gemaakte keuzes staan in [AGENTS.md](AGENTS.md).
