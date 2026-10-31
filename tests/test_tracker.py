"""Tests voor tracker.py (alleen standaardbibliotheek).

Draaien:  python3 -m unittest discover tests
De simulatietests draaien volledige runs op nepdata in een tijdelijke map: er wordt niets opgehaald,
niets aan je echte gegevens veranderd en geen enkele melding verstuurd.
"""
import json
import socket
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tracker as t  # noqa: E402


def auto(i, prijs, km=40000, jaar=2015, pk=430, titel="911 Carrera GTS Cabriolet – GTS", manueel=True, land="BE"):
    return {"id": i, "bron": "AutoScout24", "titel": titel, "prijs": prijs, "km": km, "jaar": jaar, "maand": 6,
            "pk": pk, "manueel": manueel, "co2": None, "land": land, "plaats": "Gent", "verkoper": "x",
            "dealer": True, "foto": None, "url": "https://x/" + i}


# genoeg andere auto's zodat de marktprijs berekend wordt (vanaf 8), duidelijk verschillend van de testauto's
VULLING = [auto(f"as-v{n}", 100000 + n * 4000, 15000 + n * 9000, 2017 + n % 3, pk=450) for n in range(9)]


class Herkenning(unittest.TestCase):
    def herken(self, titel, pk, jaar):
        c = {"titel": titel, "pk": pk, "jaar": jaar}
        c["model"] = t.model(c)
        return c["model"], c["model"] and t.generatie(c)

    def test_model_en_generatie(self):
        gevallen = [("911 Carrera GTS Cabriolet", 408, 2011, ("GTS", "997.2")),
                    ("911 Turbo Cabriolet 997", 480, 2008, ("Turbo", "997.1")),
                    ("911 Turbo Cabrio", 500, 2010, ("Turbo", "997.2")),
                    ("911 Turbo S Cabriolet", 530, 2011, ("Turbo S", "997.2")),
                    ("911 Carrera 4 GTS Cabriolet", 430, 2015, ("GTS", "991.1")),
                    ("911 Targa 4 GTS", 450, 2018, ("GTS", "991.2")),
                    ("911 Carrera 4 GTS Cabriolet", 480, 2022, ("GTS", "992")),
                    ("911 Turbo Cabriolet", 520, 2014, ("Turbo", "991.1")),
                    ("911 Turbo S Cabriolet", 580, 2017, ("Turbo S", "991.2")),
                    ("911 Turbo S Cabriolet", 650, 2021, ("Turbo S", "992"))]
        for titel, pk, jaar, verwacht in gevallen:
            self.assertEqual(self.herken(titel, pk, jaar), verwacht, titel)

    def test_geen_echte_gts_of_turbo(self):
        for titel, pk, jaar in [("911 Carrera 3.0 Turbo Cabrio", 420, 2017), ("911 Carrera S 3.8 Turbo-look", 385, 2009),
                                ("911 Turbo Cabriolet", None, 2009)]:
            self.assertEqual(self.herken(titel, pk, jaar), (None, None), titel)

    def test_zelfde_auto(self):
        a = {"model": "GTS", "jaar": 2015, "km": 40000, "prijs": 110000}
        self.assertTrue(t.zelfde_auto(a, dict(a, km=40300, prijs=105000)))   # afgerond, andere site goedkoper
        self.assertFalse(t.zelfde_auto(a, dict(a, km=48000)))                # andere km
        self.assertFalse(t.zelfde_auto(a, dict(a, prijs=90000)))             # >10% verschil
        self.assertFalse(t.zelfde_auto(a, dict(a, jaar=2016)))


class Vlaggen(unittest.TestCase):
    def test_tekst(self):
        gevallen = [("Unfallfrei, kein Unfallschaden, scheckheftgepflegt, Sport Chrono, PCCB",
                     [], ["PCCB", "Sport Chrono", "onderhoudshistoriek"]),
                    ("Vorschäden: keine. Unfallschaden: nein", [], []),
                    ("US Import - instandgesetzter Vorschaden (Carfax)", ["ongeval", "US-import"], []),
                    ("Carfax report vorhanden", [], []),
                    ("geen hagelschade. eerste eigenaar, sportuitlaat", [], ["sportuitlaat", "1e eigenaar"]),
                    ("no accident damage, PDCC, bucket seats", [], ["PDCC", "kuipstoelen"]),
                    ("verkocht zonder keuring", ["zonder keuring/export"], [])]
        for tekst, rood, groen in gevallen:
            v = t.vlaggen(tekst.lower())
            self.assertEqual((v["rood"], v["groen"]), (rood, groen), tekst)

    def test_vaste_velden(self):
        v = t.vlaggen("", {"hadAccident": True, "damageConditions": ["x"], "noOfPreviousOwners": 6,
                           "originalMarket": "Verenigde Staten", "hasFullServiceHistory": True})
        self.assertEqual(v["rood"], ["ongeval", "schade gemeld", "import uit Verenigde Staten", "6 vorige eigenaars"])
        self.assertEqual(v["groen"], ["onderhoudshistoriek"])
        self.assertEqual(t.vlaggen("", {"originalMarket": "Duitsland", "noOfPreviousOwners": 1})["groen"], ["1e eigenaar"])


class Kleur(unittest.TestCase):
    def test_kleur_uit(self):
        for tekst, groep in [("wit", "wit"), ("Lava Orange", "oranje"), ("GT Silver Metallic", "zilver"),
                             ("Kreide", "grijs"), ("Carrara White, Leder schwarz", "wit"), ("benzine", None), ("", None),
                             ("Racing Yellow", "geel"), ("Basaltschwarz", "zwart"), ("Guards Red", "rood")]:
            self.assertEqual(t.kleur_uit(tekst), groep, tekst)


class Berekeningen(unittest.TestCase):
    def test_biv_daalt_met_leeftijd(self):
        c = {"model": "GTS", "generatie": "991.2", "manueel": False, "co2": None, "jaar": datetime.now().year - 1, "maand": 1}
        jong = t.biv(c)[0]
        oud = t.biv(dict(c, jaar=2008, generatie="997.2"))[0]
        self.assertGreater(jong, oud)
        self.assertEqual(oud, round(t.CONFIG["biv"]["minimum"]))

    def test_past_bij_zoekprofiel(self):
        c = {"generatie": "997.2", "model": "GTS", "type": "Cabrio", "jaar": 2011, "prijs": 80000, "manueel": True, "land": "DE"}
        p = {"naam": "x", "gens": ["997.1", "997.2"], "man": True, "maxp": "90000"}
        self.assertTrue(t.past_bij(c, p))
        self.assertFalse(t.past_bij(dict(c, manueel=False), p))
        self.assertFalse(t.past_bij(dict(c, prijs=95000), p))
        self.assertFalse(t.past_bij(c, dict(p, be=True)))
        self.assertTrue(t.past_bij(dict(c, kleur="wit"), dict(p, kleuren=["wit", "grijs"])))
        self.assertFalse(t.past_bij(dict(c, kleur="zwart"), dict(p, kleuren=["wit", "grijs"])))


class Planning(unittest.TestCase):
    def test_run_nodig(self):
        nu = datetime(2026, 10, 31, 9, 40)
        self.assertFalse(t.run_nodig({"laatste_geslaagde_run": "2026-10-31T09:04"}, nu))
        self.assertTrue(t.run_nodig({"laatste_geslaagde_run": "2026-10-30T18:05"}, nu))   # 08:00 gemist
        self.assertTrue(t.run_nodig({"laatste_geslaagde_run": "2026-10-30T07:00"}, datetime(2026, 10, 31, 7, 0)))  # 18u gisteren
        self.assertTrue(t.run_nodig({"laatste_geslaagde_run": "2026-10-31T09:04", "herkansen_om": "2026-10-31T09:34"}, nu))
        self.assertFalse(t.run_nodig({"laatste_geslaagde_run": "2026-10-31T09:04", "herkansen_om": "2026-10-31T10:00"}, nu))


class OpnieuwProberen(unittest.TestCase):
    def setUp(self):
        self.orig = (t.urllib.request.urlopen, t.time.sleep)
        self.gewacht = []
        t.time.sleep = self.gewacht.append

    def tearDown(self):
        t.urllib.request.urlopen, t.time.sleep = self.orig

    def antwoorden(self, *reeks):
        it = iter(reeks)

        class R:
            def __init__(s, x): s.x = x
            def __enter__(s): return s
            def __exit__(s, *a): pass
            def read(s): return s.x.encode()

        def urlopen(req, timeout):
            x = next(it)
            if isinstance(x, Exception):
                raise x
            return R(x)
        t.urllib.request.urlopen = urlopen

    def test_tijdelijke_fouten(self):
        self.antwoorden(socket.timeout("timed out"), urllib.error.HTTPError("u", 429, "", {"Retry-After": "45"}, None), "ok")
        self.assertEqual(t.get("https://x"), "ok")
        self.assertEqual(self.gewacht, [10, 45])

    def test_echte_fout_meteen(self):
        self.antwoorden(urllib.error.HTTPError("u", 404, "", {}, None))
        with self.assertRaises(urllib.error.HTTPError):
            t.get("https://x")
        self.assertEqual(self.gewacht, [])


class Simulatie(unittest.TestCase):
    """Volledige runs op nepdata: bronnen, marktstaal, meldingen en detailpagina's zijn vervangen."""

    def setUp(self):
        self.map = tempfile.TemporaryDirectory()
        d = Path(self.map.name)
        self.orig = {k: getattr(t, k) for k in ("STATE_FILE", "DASHBOARD", "NTFY_TOPIC_FILE", "PROFIELEN_FILE", "push",
                                                "melding", "marktstaal", "dealer_bronnen", "fetch_2dehands",
                                                "fetch_autoscout", "as_detailpagina")}
        t.STATE_FILE, t.DASHBOARD, t.NTFY_TOPIC_FILE, t.PROFIELEN_FILE = (d / "state.json", d / "dash.html",
                                                                         d / "topic.txt", d / "prof.json")
        self.meldingen = []
        t.push = lambda titel, *a, **k: self.meldingen.append(titel)
        t.melding = lambda *a, **k: None
        t.marktstaal = lambda oud, vandaag: {"datum": vandaag, "punten": []}
        t.dealer_bronnen = lambda: []
        t.fetch_2dehands = lambda: []
        t.as_detailpagina = lambda c: {"open": True, **t.vlaggen("sport chrono", {"noOfPreviousOwners": 1})}

    def tearDown(self):
        for k, v in self.orig.items():
            setattr(t, k, v)
        self.map.cleanup()

    def run_met(self, autos, fout=False):
        def bron():
            if fout:
                raise TimeoutError("The read operation timed out")
            return [dict(a) for a in autos]
        t.fetch_autoscout = bron
        t.main()
        return json.loads(t.STATE_FILE.read_text())

    def zet_terug_in_de_tijd(self, auto_id, dagen_geleden="2026-10-01T08:00"):
        s = json.loads(t.STATE_FILE.read_text())
        s["verkocht"][auto_id]["weg_sinds"] = dagen_geleden
        for h in s["verkoop_historiek"]:
            h["weg_sinds"] = dagen_geleden
        t.STATE_FILE.write_text(json.dumps(s))

    def test_nieuw_verkocht_en_opnieuw_te_koop(self):
        s = self.run_met([auto("as-A", 110000)] + VULLING)
        a = s["auto"]["as-A"]["laatst"]
        self.assertTrue(a["nieuw"])
        self.assertEqual(a["vlaggen"]["groen"], ["Sport Chrono", "1e eigenaar"])
        self.assertEqual(self.meldingen, [])  # eerste run ooit: geen meldingen

        s = self.run_met(VULLING)  # weg op een site die werkte: verkocht
        self.assertNotIn("as-A", s["auto"])
        self.assertIn("as-A", s["verkocht"])
        self.assertEqual(len(s["verkoop_historiek"]), 1)

        self.zet_terug_in_de_tijd("as-A")
        t.PROFIELEN_FILE.write_text(json.dumps([{"naam": "Manuele 991.1", "gens": ["991.1"], "man": True}]))
        s = self.run_met([auto("as-B", 103000, 40300)] + VULLING)  # nieuwe advertentie, €7.000 goedkoper
        a = s["auto"]["as-A"]["laatst"]
        self.assertFalse(a["nieuw"])
        self.assertEqual([p for _, p in a["prijshistoriek"]], [110000, 103000])
        self.assertEqual(a["opnieuw"]["prijs"], 110000)
        self.assertEqual(s["verkoop_historiek"], [])  # het was dus geen verkoop
        self.assertEqual(len(self.meldingen), 1)
        self.assertTrue(self.meldingen[0].startswith("🎯 Manuele 991.1 · Prijsdaling −€7.000"), self.meldingen[0])

    def test_site_plat_en_herkansing(self):
        self.run_met([auto("as-A", 110000)] + VULLING)
        s = self.run_met([], fout=True)
        a = s["auto"]["as-A"]["laatst"]
        self.assertTrue(a["bron_offline"])           # niet als verkocht beschouwd
        self.assertEqual(s["verkocht"], {})
        self.assertIsNotNone(s["herkansen_om"])      # over 30 min opnieuw
        self.assertEqual(self.meldingen, [])         # nog geen foutmelding
        s = self.run_met([auto("as-A", 110000)] + VULLING)
        self.assertFalse(s["auto"]["as-A"]["laatst"]["bron_offline"])
        self.assertIsNone(s["herkansen_om"])

    def test_dashboard_bevat_gegevens(self):
        self.run_met([auto("as-A", 110000)] + VULLING)
        regel = next(r for r in t.DASHBOARD.read_text().split("\n") if r.startswith("const DATA = "))
        data = json.loads(regel[len("const DATA = "):].rstrip().rstrip(";"))
        self.assertEqual(len(data["autos"]), 10)
        self.assertIn("marktprijs", data["autos"][0])


if __name__ == "__main__":
    unittest.main()
