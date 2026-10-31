#!/usr/bin/env python3
"""Hulpserver voor de knop "Nu zoeken" in het dashboard.

Een browser mag vanuit een HTML-bestand geen programma starten, daarom draait dit piepkleine
servertje mee (launchd, zie install.sh). Het luistert alleen op deze Mac (127.0.0.1:8911):
  GET  /status  -> {"bezig": true/false, "bijgewerkt": tijdstip van het laatste dashboard}
  POST /zoek    -> start tracker.py op de achtergrond (tenzij er al een run bezig is)
  GET/POST /profielen -> eigen zoekprofielen lezen / bewaren (zoekprofielen.json, gebruikt door tracker.py)

Alleen standaardbibliotheek, zoals tracker.py.
"""
import fcntl
import json
import subprocess
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path.home() / "Library" / "Application Support" / "porsche-tracker"
SLOT_FILE = DATA_DIR / "tracker.lock"  # zelfde slot als in tracker.py
DASHBOARD = DATA_DIR / "dashboard.html"
LOG = DATA_DIR / "tracker.log"
PROFIELEN = DATA_DIR / "zoekprofielen.json"
VELDEN = {"naam": str, "gens": list, "mdl": str, "typ": str, "van": str, "maxp": str, "man": bool, "be": bool, "kleuren": list}
POORT = 8911
# Het dashboard is een lokaal bestand (file://): de browser stuurt dan Origin "null".
# Andere websites krijgen geen toegang, zodat een willekeurige site geen runs kan starten.
TOEGELATEN = {None, "null", f"http://localhost:{POORT}", f"http://127.0.0.1:{POORT}"}
_run, _gestart = None, 0.0


def bezig():
    # net gestart: tracker.py heeft het slot misschien nog niet genomen
    if _run and _run.poll() is None and time.time() - _gestart < 15:
        return True
    try:
        with open(SLOT_FILE, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
    except OSError:
        return True


class Knop(BaseHTTPRequestHandler):
    def antwoord(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/profielen":
            try:
                return self.antwoord(200, json.loads(PROFIELEN.read_text()))
            except (OSError, ValueError):
                return self.antwoord(200, [])
        if self.path != "/status":
            return self.antwoord(404, {"fout": "onbekend"})
        bijgewerkt = (datetime.fromtimestamp(DASHBOARD.stat().st_mtime).isoformat(timespec="seconds")
                      if DASHBOARD.exists() else None)
        self.antwoord(200, {"bezig": bezig(), "bijgewerkt": bijgewerkt})

    def do_POST(self):
        global _run, _gestart
        if self.headers.get("Origin") not in TOEGELATEN:
            return self.antwoord(403, {"fout": "niet toegelaten"})
        if self.path == "/profielen":
            return self.profielen_bewaren()
        if self.path != "/zoek":
            return self.antwoord(404, {"fout": "onbekend"})
        if bezig():
            return self.antwoord(200, {"gestart": False, "bezig": True})
        with open(LOG, "a") as log:
            _gestart = time.time()
            _run = subprocess.Popen([sys.executable, str(ROOT / "tracker.py")], cwd=ROOT,
                                    stdout=log, stderr=log, stdin=subprocess.DEVNULL)
        print(f"{datetime.now().isoformat(timespec='minutes')}: manuele run gestart via dashboard", flush=True)
        self.antwoord(202, {"gestart": True, "bezig": True})

    def profielen_bewaren(self):
        """Volledige lijst als tekst (text/plain, zodat de browser geen extra CORS-vraag stuurt)."""
        lengte = int(self.headers.get("Content-Length") or 0)
        try:
            lijst = json.loads(self.rfile.read(min(lengte, 20000)))
            schoon = [{k: p[k] for k, t in VELDEN.items() if isinstance(p.get(k), t)} for p in lijst[:20]]
            if not all(p.get("naam") and len(p["naam"]) <= 40 and any(v for k, v in p.items() if k != "naam")
                       for p in schoon):
                raise ValueError("elk profiel heeft een naam en minstens één criterium nodig")
        except (ValueError, TypeError, AttributeError) as e:
            return self.antwoord(400, {"fout": str(e)})
        PROFIELEN.write_text(json.dumps(schoon, indent=1))
        self.antwoord(200, schoon)

    def log_message(self, *args):  # geen logregel per statusvraag
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", POORT), Knop).serve_forever()
