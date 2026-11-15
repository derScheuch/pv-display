#!/usr/bin/env python3
"""
Huawei SUN2000 + SDongle + LUNA battery: continuous logger via Modbus TCP (e.g. on a Raspberry Pi).

What it does:
  * polls the most important values every --interval seconds (default 20)
  * appends every sample to  <dir>/YYYY-MM-DD.csv
  * measures the PV yield itself by integrating PV power over time
  * counts communication failures (failed polls, gaps)
  * writes one line per day to  <dir>/tage.csv  with all yield figures, for comparison with the app
  * serves the current values as JSON for a display (see below)
  * optionally sends an "unplug the car" push reminder via ntfy

Installation (Raspberry Pi OS):
  mkdir -p ~/huawei-logger && cd ~/huawei-logger
  python3 -m venv venv && venv/bin/pip install -r requirements.txt
  venv/bin/python huawei_logger.py            # test run, Ctrl+C to stop

Display/ESP32: the logger serves the current values as JSON at
  http://<raspi>:8765/status   (port via --http-port, 0 = off)

Note: the dongle allows only ONE Modbus connection. While the logger is running,
huawei_poll.py (e.g. from a laptop) will not get any answers.

"Unplug the car" reminder (optional, ntfy push to your phone):
  If, from one hour before sunset until sunrise, a large consumer (> 1.5 kW, probably the car)
  runs for 10 minutes and the home battery is below 80 %, the logger sends a push message.
  Location for sunset calculation: --lat/--lon (default: Hanover, Germany).
  1. Install the "ntfy" app on your phone and subscribe to a topic, e.g. pv-<random-number>
  2. Start the logger with  --ntfy-topic pv-<random-number>
  3. Test:                   huawei_logger.py --ntfy-topic pv-<random-number> --ntfy-test
"""

import argparse
import csv
import json
import logging
import os
import struct
import sys
import signal
import time
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, date

from pymodbus.client import ModbusTcpClient

logging.getLogger("pymodbus").setLevel(logging.CRITICAL)   # no flood of "Exception response ..." messages in the journal

PFLICHT = {"pv_w", "ac_w", "akku_w", "netz_w", "soc"}      # never marked as "not available"

# key: (register, count, type, divisor)
REGISTERS = {
    "status":         (32089,  1, "u16", 1),
    "pv1_u":          (32016,  1, "i16", 10),
    "pv1_i":          (32017,  1, "i16", 100),
    "pv2_u":          (32018,  1, "i16", 10),
    "pv2_i":          (32019,  1, "i16", 100),
    "pv_w":           (32064,  2, "i32", 1),
    "ac_w":           (32080,  2, "i32", 1),
    "temp":           (32087,  1, "i16", 10),
    "soc":            (37760,  1, "u16", 10),
    "akku_w":         (37765,  2, "i32", 1),
    "netz_w":         (37113,  2, "i32", 1),
    "wr_heute":       (32114,  2, "u32", 100),
    "akku_lad_heute": (37784,  2, "u32", 100),
    "akku_ent_heute": (37786,  2, "u32", 100),
    "wr_gesamt":      (32106,  2, "u32", 100),
    "akku_lad_ges":   (37780,  2, "u32", 100),
    "akku_ent_ges":   (37782,  2, "u32", 100),
    "eingespeist":    (37119,  2, "i32", 100),
    "bezogen":        (37121,  2, "i32", 100),
}

# Adjacent registers are read in a single request (easier on the dongle):
# 6 requests per cycle instead of 19. If the dongle rejects a block, it is read register by register.
def _bloecke(regs, max_luecke=8):
    items = sorted(regs.items(), key=lambda kv: kv[1][0])
    bloecke, akt = [], None
    for key, (addr, count, _, _) in items:
        if akt and addr - (akt["start"] + akt["anzahl"]) <= max_luecke:
            akt["anzahl"] = max(akt["anzahl"], addr + count - akt["start"])
            akt["keys"].append(key)
        else:
            akt = {"start": addr, "anzahl": count, "keys": [key]}
            bloecke.append(akt)
    return bloecke

BLOECKE = _bloecke(REGISTERS)
PAUSE_ZWISCHEN_ANFRAGEN = 0.2     # seconds

POLL_FIELDS = ["zeit", "ok", "status", "pv_w", "ost_proz", "west_proz", "pv1_u", "pv1_i", "pv2_u", "pv2_i",
               "ac_w", "akku_w", "soc", "netz_w", "temp",
               "wr_heute", "akku_lad_heute", "akku_ent_heute", "pv_gemessen_kwh"]

DAY_FIELDS = ["datum", "pv_gemessen_kwh", "pv_formel_kwh", "wr_ertrag_kwh", "akku_geladen_kwh",
              "akku_entladen_kwh", "abfragen_ok", "abfragen_fehler", "luecken_min", "groesste_luecke_min",
              "eingespeist_ges_kwh", "bezogen_ges_kwh", "app_ertrag_kwh"]


# ---------------------------------------------------------------- Modbus

def decode(regs, typ):
    raw = struct.pack(">" + "H" * len(regs), *regs)
    fmt = {"u16": ">H", "i16": ">h", "u32": ">I", "i32": ">i"}[typ]
    return struct.unpack(fmt, raw)[0]


class Inverter:
    def __init__(self, host, port, unit):
        self.host, self.port, self.unit = host, port, unit
        self.client = None
        self.missing = set()          # registers that do not exist on this installation
        self.einzeln = set()          # blocks (start address) the dongle refuses to return in one piece
        self.pause_bis = 0.0          # after errors: give the dongle time to drop the old connection

    def reset(self):
        """Drop the connection completely (like restarting the logger)."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None
        self.missing.clear()
        self.einzeln.clear()

    def _connect(self):
        if self.client and self.client.connected:
            return True
        if time.time() < self.pause_bis:
            return False
        self.reset()                  # always reconnect from scratch, including a fresh "not available" list
        self.client = ModbusTcpClient(self.host, port=self.port, timeout=5)
        if not self.client.connect():
            self.pause_bis = time.time() + 20
            return False
        time.sleep(1)                 # the dongle needs a moment after connecting
        return True

    def _read(self, address, count):
        try:
            rr = self.client.read_holding_registers(address, count=count, device_id=self.unit)  # pymodbus >= 3.10
        except TypeError:
            rr = self.client.read_holding_registers(address, count=count, slave=self.unit)      # older 3.x
        if rr.isError():
            if getattr(rr, "exception_code", None) == 2:
                return "missing"
            return None
        regs = getattr(rr, "registers", None)
        if not regs or len(regs) != count:          # incomplete/stray response -> treat as error
            return None
        return regs

    def _anfrage(self, address, count):
        """One request with one retry (the dongle tends to drop the first one)."""
        regs = None
        for _ in range(2):
            time.sleep(PAUSE_ZWISCHEN_ANFRAGEN)
            try:
                regs = self._read(address, count)
            except Exception:
                regs = None
            if regs is not None:
                break
            time.sleep(0.5)
        return regs

    def read_all(self):
        """Returns a dict, or None if the poll failed."""
        if not self._connect():
            return None
        data, failures = {}, 0

        def fehler():
            nonlocal failures
            failures += 1
            if failures >= 3:                       # dongle not responding properly -> drop the connection
                self.reset()
                self.pause_bis = time.time() + 20
                return True
            return False

        for blk in BLOECKE:
            keys = [k for k in blk["keys"] if k not in self.missing]
            if not keys:
                continue

            if blk["start"] not in self.einzeln and len(blk["keys"]) > 1:
                regs = self._anfrage(blk["start"], blk["anzahl"])
                if isinstance(regs, list):
                    for k in keys:
                        addr, count, typ, div = REGISTERS[k]
                        off = addr - blk["start"]
                        val = decode(regs[off:off + count], typ)
                        data[k] = val if k == "status" else val / div
                    continue
                if regs == "missing":
                    self.einzeln.add(blk["start"])  # block contains gaps -> read individually from now on
                elif fehler():
                    return None
                else:
                    continue

            for k in keys:                          # read individually
                addr, count, typ, div = REGISTERS[k]
                regs = self._anfrage(addr, count)
                if regs == "missing":
                    if k not in PFLICHT:
                        self.missing.add(k)
                        continue
                    regs = None                     # mandatory register: count as error, do not mark as missing
                if regs is None:
                    if fehler():
                        return None
                    continue
                val = decode(regs, typ)
                data[k] = val if k == "status" else val / div

        return data if "pv_w" in data else None


# ---------------------------------------------------------------- daily state

class Day:
    def __init__(self, state_file):
        self.state_file = state_file
        self.reset(date.today())
        self._load()

    def reset(self, d):
        self.datum = d.isoformat()
        self.pv_wh = 0.0
        self.ok = self.fail = 0
        self.gap_s = self.max_gap_s = 0.0
        self.last_ok_ts = None
        self.last_pv_w = None
        self.last = {}                 # last valid register values of the day
        self.basis_einsp = None        # export meter reading at the first sample of the day
        self.basis_bezug = None        # import meter reading at the first sample of the day

    def _load(self):
        try:
            with open(self.state_file) as f:
                s = json.load(f)
            if s.get("datum") == self.datum:
                self.__dict__.update({k: v for k, v in s.items() if k in self.__dict__ and k != "state_file"})
        except (OSError, ValueError):
            pass

    def save(self, force=False):
        # write to the SD card at most once per minute (reduces wear)
        if not force and time.time() - getattr(self, "_saved", 0) < 60:
            return
        self._saved = time.time()
        s = {k: v for k, v in self.__dict__.items() if k not in ("state_file", "_saved")}
        tmp = self.state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(s, f)
        os.replace(tmp, self.state_file)

    def record(self, ts, data, interval):
        if data is None:
            self.fail += 1
            return
        self.ok += 1
        pv = max(data["pv_w"], 0.0)
        if self.last_ok_ts is not None:
            dt = ts - self.last_ok_ts
            if dt <= 3 * interval:
                self.pv_wh += (pv + self.last_pv_w) / 2 * dt / 3600      # trapezoidal rule
            else:
                gap = dt - interval
                self.gap_s += gap
                self.max_gap_s = max(self.max_gap_s, gap)
                # do not interpolate across the gap -> measured value is a lower bound
        self.last_ok_ts, self.last_pv_w = ts, pv
        self.last.update(data)
        if self.basis_einsp is None and "eingespeist" in data:
            self.basis_einsp = data["eingespeist"]
        if self.basis_bezug is None and "bezogen" in data:
            self.basis_bezug = data["bezogen"]

    def energie_heute(self):
        """Daily values in kWh: yield, house consumption, grid export, grid import.
        Export/import count from the first sample of the day (on the first day: from logger start)."""
        g = self.last.get
        einsp = g("eingespeist") - self.basis_einsp if self.basis_einsp is not None and "eingespeist" in self.last else None
        bezug = g("bezogen") - self.basis_bezug if self.basis_bezug is not None and "bezogen" in self.last else None
        ertrag = None
        if all(k in self.last for k in ("wr_heute", "akku_lad_heute", "akku_ent_heute")):
            ertrag = g("wr_heute") - g("akku_ent_heute") + g("akku_lad_heute")
        verbrauch = None
        if "wr_heute" in self.last and einsp is not None and bezug is not None:
            verbrauch = g("wr_heute") + bezug - einsp        # inverter output + grid import - grid export
        return {"ertrag": ertrag, "verbrauch": verbrauch, "einspeisung": einsp, "bezug": bezug}

    def summary(self):
        g = self.last.get
        formel = None
        if all(k in self.last for k in ("wr_heute", "akku_lad_heute", "akku_ent_heute")):
            formel = g("wr_heute") - g("akku_ent_heute") + g("akku_lad_heute")
        r = lambda v, n=2: "" if v is None else round(v, n)
        return {
            "datum": self.datum,
            "pv_gemessen_kwh": r(self.pv_wh / 1000),
            "pv_formel_kwh": r(formel),
            "wr_ertrag_kwh": r(g("wr_heute")),
            "akku_geladen_kwh": r(g("akku_lad_heute")),
            "akku_entladen_kwh": r(g("akku_ent_heute")),
            "abfragen_ok": self.ok,
            "abfragen_fehler": self.fail,
            "luecken_min": r(self.gap_s / 60, 1),
            "groesste_luecke_min": r(self.max_gap_s / 60, 1),
            "eingespeist_ges_kwh": r(g("eingespeist")),
            "bezogen_ges_kwh": r(g("bezogen")),
            "app_ertrag_kwh": "",          # fill in manually from the FusionSolar app
        }


# ---------------------------------------------------------------- CSV

def append_csv(path, fields, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        if new:
            w.writeheader()
        w.writerow(row)


def ost_west(data):
    """Share of each roof side in the PV power, in percent (east + west = 100).
    PV1 = west (16 modules), PV2 = east (9 modules). No power (night): no value."""
    if not all(k in data for k in ("pv1_u", "pv1_i", "pv2_u", "pv2_i")):
        return None, None
    west = max(data["pv1_u"] * data["pv1_i"], 0.0)
    ost = max(data["pv2_u"] * data["pv2_i"], 0.0)
    summe = ost + west
    if summe <= 0:
        return None, None
    return ost / summe * 100, west / summe * 100


def energiefluss(data):
    """Estimates the current energy flows in W from PV, battery and meter power.
    Assumptions: the battery is charged from PV only; grid export comes from PV (only what the
    battery delivers beyond the house demand counts as battery -> grid); house consumption
    is covered first by grid import, the rest by battery discharge and PV.
    The house side balances exactly; the PV side contains conversion losses (a few %)."""
    if not all(k in data for k in ("pv_w", "akku_w", "netz_w", "ac_w")):
        return None
    pv = max(data["pv_w"], 0.0)
    laden, entladen = max(data["akku_w"], 0.0), max(-data["akku_w"], 0.0)
    einsp, bezug = max(data["netz_w"], 0.0), max(-data["netz_w"], 0.0)
    haus = max(data["ac_w"] - data["netz_w"], 0.0)

    netz_haus = min(bezug, haus)
    rest = haus - netz_haus                     # must come from battery or PV
    akku_haus = min(entladen, rest)
    akku_netz = min(max(entladen - akku_haus, 0.0), einsp)   # battery surplus going to the grid
    pv_haus = max(rest - akku_haus, 0.0)
    pv_akku = min(laden, pv)
    pv_netz = max(einsp - akku_netz, 0.0)
    fl = {"pv_haus": pv_haus, "pv_akku": pv_akku, "pv_netz": pv_netz,
          "netz_haus": netz_haus, "akku_haus": akku_haus, "akku_netz": akku_netz}
    fl = {k: (v if v >= 10 else 0.0) for k, v in fl.items()}   # suppress measurement noise below 10 W
    fl["haus"] = haus
    return fl


def num(v, n=2):
    if v is None:
        return ""
    return str(int(round(v))) if n == 0 else str(round(v, n)).replace(".", ",")   # decimal comma for German Excel/Numbers


def poll_row(now, data, day):
    if data is None:
        return {"zeit": now.strftime("%Y-%m-%d %H:%M:%S"), "ok": 0}
    g = data.get
    ost, west = ost_west(data)
    return {
        "zeit": now.strftime("%Y-%m-%d %H:%M:%S"), "ok": 1,
        "status": f"0x{int(g('status')):04X}" if "status" in data else "",
        "pv_w": num(g("pv_w"), 0), "ost_proz": num(ost, 0), "west_proz": num(west, 0),
        "pv1_u": num(g("pv1_u"), 1), "pv1_i": num(g("pv1_i")),
        "pv2_u": num(g("pv2_u"), 1), "pv2_i": num(g("pv2_i")),
        "ac_w": num(g("ac_w"), 0), "akku_w": num(g("akku_w"), 0), "soc": num(g("soc"), 1),
        "netz_w": num(g("netz_w"), 0), "temp": num(g("temp"), 1),
        "wr_heute": num(g("wr_heute")), "akku_lad_heute": num(g("akku_lad_heute")),
        "akku_ent_heute": num(g("akku_ent_heute")),
        "pv_gemessen_kwh": num(day.pv_wh / 1000, 3),
    }


def write_day(dir_, day):
    s = day.summary()
    s = {k: (str(v).replace(".", ",") if isinstance(v, float) else v) for k, v in s.items()}
    append_csv(os.path.join(dir_, "tage.csv"), DAY_FIELDS, s)
    print(f"[{datetime.now():%H:%M:%S}] Tageszusammenfassung {day.datum} geschrieben: "
          f"gemessen {s['pv_gemessen_kwh']} kWh, Formel {s['pv_formel_kwh']} kWh", flush=True)


# ---------------------------------------------------------------- "unplug the car" reminder

def ntfy(topic, title, message, server="https://ntfy.sh"):
    req = urllib.request.Request(
        f"{server}/{topic}", data=message.encode("utf-8"), method="POST",
        headers={"Title": title, "Priority": "high", "Tags": "electric_plug,battery"})
    try:
        urllib.request.urlopen(req, timeout=10).close()
        return True
    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] Push fehlgeschlagen: {e}", flush=True)
        return False


def sun_times(d, lat, lon):
    """Sunrise and sunset (local time) using the NOAA approximation, accurate to ~1-2 minutes."""
    import math
    rad, deg = math.radians, math.degrees
    n = d.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)                       # fractional year (at noon)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    cos_ha = (math.cos(rad(90.833)) / (math.cos(rad(lat)) * math.cos(decl))
              - math.tan(rad(lat)) * math.tan(decl))
    ha = deg(math.acos(max(-1.0, min(1.0, cos_ha))))
    noon_utc_min = 720 - 4 * lon - eqt
    offset = datetime(d.year, d.month, d.day, 12).astimezone().utcoffset()   # local UTC offset on that day (CET/CEST)
    base = datetime(d.year, d.month, d.day) + offset
    from datetime import timedelta
    return (base + timedelta(minutes=noon_utc_min - 4 * ha),
            base + timedelta(minutes=noon_utc_min + 4 * ha))


class CarWatcher:
    """Sends a reminder when a large consumer runs around/after sunset and the battery is not full."""

    def __init__(self, topic, lat, lon, vorlauf_min, last_min, soc_max, minutes, repeat_min):
        self.topic = topic
        self.lat, self.lon = lat, lon
        self.vorlauf_s = vorlauf_min * 60
        self.last_min, self.soc_max = last_min, soc_max
        self.hold_s, self.repeat_s = minutes * 60, repeat_min * 60
        self.since = None          # since when the condition has been met
        self.warnung = False       # condition met long enough (for the display)
        self.last_push = float("-inf")
        self._sun = (None, None, None)

    def sun(self, now):
        if self._sun[0] != now.date():
            self._sun = (now.date(), *sun_times(now.date(), self.lat, self.lon))
        return self._sun[1], self._sun[2]

    def dusk(self, now):
        """True from <vorlauf> minutes before sunset until sunrise."""
        aufgang, untergang = self.sun(now)
        return now < aufgang or (untergang - now).total_seconds() <= self.vorlauf_s

    def message(self, now, data, last):
        _, untergang = self.sun(now)
        rest = (untergang - now).total_seconds() / 60
        if rest > 0:
            sonne = f"In {rest:.0f} Minuten geht die Sonne unter ({untergang:%H:%M})"
        else:
            sonne = f"Die Sonne ist seit {untergang:%H:%M} weg"
        pv, akku, soc = data.get("pv_w", 0), data.get("akku_w", 0), data.get("soc", 0)
        lines = [
            f"Da läuft gerade ein dicker Verbraucher mit {fmt_kw(last)} – vermutlich das Auto.",
            f"{sonne}, die Module liefern nur noch {pv:.0f} W.",
            f"Der Hausakku steht bei {soc:.0f} %, den kriegst du heute nicht mehr voll."
            + (f" Er gibt gerade {fmt_kw(-akku)} ab." if akku < -100 else ""),
        ]
        return "\n".join(lines)

    def check(self, ts, data, now=None):
        if data is None or not all(k in data for k in ("ac_w", "netz_w", "soc")):
            return
        now = now or datetime.now()
        last = data["ac_w"] - data["netz_w"]            # house consumption incl. car
        cond = last > self.last_min and data["soc"] < self.soc_max and self.dusk(now)
        if not cond:
            self.since = None
            self.warnung = False
            return
        if self.since is None:
            self.since = ts
        self.warnung = ts - self.since >= self.hold_s
        if self.topic and self.warnung and ts - self.last_push >= self.repeat_s:
            msg = self.message(now, data, last)
            if ntfy(self.topic, "Bitte Auto abklemmen!", msg):
                self.last_push = ts
                print(f"[{now:%H:%M:%S}] Erinnerung gesendet: {msg}", flush=True)


def fmt_kw(w):
    return f"{w / 1000:.1f} kW".replace(".", ",")


# ---------------------------------------------------------------- HTTP interface for the display

STATUS = {"ok": False}
STATUS_LOCK = threading.Lock()


def update_status(ts, data, day, watcher):
    """Builds the JSON status that e.g. the ESP32 display fetches."""
    r = lambda v, n=0: None if v is None else (int(round(v)) if n == 0 else round(v, n))
    with STATUS_LOCK:
        if data is None:
            STATUS["ok"] = False                       # keep the last valid values
            return
        g = data.get
        ost, west = ost_west(data)
        last = g("ac_w") - g("netz_w") if "ac_w" in data and "netz_w" in data else None
        aufgang, untergang = watcher.sun(datetime.now())
        fl = energiefluss(data) or {}
        e = day.energie_heute()
        k = lambda v: None if v is None else round(v, 2)
        STATUS.clear()
        STATUS.update({
            "ok": True,
            "zeit": int(ts),
            "uhrzeit": datetime.fromtimestamp(ts).strftime("%H:%M:%S"),
            "pv_w": r(g("pv_w")), "ost_proz": r(ost), "west_proz": r(west),
            "fluss_w": {                                               # estimated current flows
                "pv_haus": r(fl.get("pv_haus")), "pv_akku": r(fl.get("pv_akku")),
                "pv_netz": r(fl.get("pv_netz")), "netz_haus": r(fl.get("netz_haus")),
                "akku_haus": r(fl.get("akku_haus")), "akku_netz": r(fl.get("akku_netz")),
            },
            "verbrauch_w": r(last), "netz_w": r(g("netz_w")),          # grid: + export / - import
            "akku_w": r(g("akku_w")), "soc": r(g("soc"), 1),           # battery: + charging / - discharging
            "wr_ac_w": r(g("ac_w")), "temp": r(g("temp"), 1),
            "heute_kwh": {
                "ertrag": k(e["ertrag"]), "verbrauch": k(e["verbrauch"]),
                "einspeisung": k(e["einspeisung"]), "bezug": k(e["bezug"]),
                "pv_gemessen": round(day.pv_wh / 1000, 2),
                "akku_geladen": k(g("akku_lad_heute")), "akku_entladen": k(g("akku_ent_heute")),
            },
            "sonne": {"aufgang": f"{aufgang:%H:%M}", "untergang": f"{untergang:%H:%M}"},
            "warnung_auto": watcher.warnung,
        })


class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] not in ("/", "/status", "/status.json"):
            self.send_error(404)
            return
        with STATUS_LOCK:
            st = dict(STATUS)
        if st.get("zeit"):
            st["alter_s"] = int(time.time() - st["zeit"])          # age of the values
        body = json.dumps(st, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):                                 # no access logs in the journal
        pass


def start_http(port):
    srv = ThreadingHTTPServer(("0.0.0.0", port), StatusHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Huawei SUN2000 Dauer-Logger")
    ap.add_argument("--host", default="192.168.178.65")
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--unit", type=int, default=1)
    ap.add_argument("--interval", type=int, default=20, help="Sekunden zwischen Abfragen (Standard 20)")
    ap.add_argument("--dir", default=os.path.expanduser("~/pv/log"), help="Ablageordner")
    ap.add_argument("--http-port", type=int, default=8765,
                    help="Port für den JSON-Status (Std. 8765, 0 = aus)")
    g = ap.add_argument_group("Erinnerung 'Auto abklemmen'")
    g.add_argument("--ntfy-topic", help="ntfy-Thema; ohne Angabe ist die Erinnerung aus")
    g.add_argument("--ntfy-test", action="store_true", help="nur eine Test-Nachricht senden und beenden")
    g.add_argument("--lat", type=float, default=52.37, help="Breitengrad der Anlage (Std. 52,37 = Hannover)")
    g.add_argument("--lon", type=float, default=9.73, help="Längengrad der Anlage (Std. 9,73 = Hannover)")
    g.add_argument("--vorlauf", type=float, default=60, help="'Dämmerung' ab so vielen Minuten vor Sonnenuntergang (Std. 60)")
    g.add_argument("--last-min", type=float, default=1500, help="'dicker Verbraucher' ab Verbrauch (W, Std. 1500)")
    g.add_argument("--soc-max", type=float, default=80, help="nur wenn Akku-Ladestand darunter (%%, Std. 80)")
    g.add_argument("--minuten", type=float, default=10, help="Bedingung so lange erfüllt (Std. 10)")
    g.add_argument("--wiederholen", type=float, default=30, help="Erinnerung frühestens wieder nach (min, Std. 30)")
    args = ap.parse_args()

    if args.ntfy_test:
        if not args.ntfy_topic:
            sys.exit("--ntfy-test braucht --ntfy-topic")
        ok = ntfy(args.ntfy_topic, "PV-Logger Test", "Wenn du das liest, kommen die Erinnerungen an.")
        sys.exit(0 if ok else 1)

    watcher = CarWatcher(args.ntfy_topic, args.lat, args.lon, args.vorlauf, args.last_min,
                         args.soc_max, args.minuten, args.wiederholen)
    if args.ntfy_topic:
        auf, unter = watcher.sun(datetime.now())
        print(f"Erinnerung aktiv: heute Sonnenaufgang {auf:%H:%M}, Sonnenuntergang {unter:%H:%M}", flush=True)
    os.makedirs(args.dir, exist_ok=True)
    inv = Inverter(args.host, args.port, args.unit)
    day = Day(os.path.join(args.dir, "zustand.json"))
    print(f"Logger läuft: {args.host}:{args.port}, alle {args.interval} s, Ablage {args.dir}", flush=True)
    if args.http_port:
        start_http(args.http_port)
        print(f"Status für das Display: http://<raspi>:{args.http_port}/status", flush=True)

    def stop(*_):                                  # systemctl stop -> shut down cleanly
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)

    fail_streak = 0
    letzter_erfolg = time.time()
    try:
        while True:
            start = time.time()
            now = datetime.now()

            if now.date().isoformat() != day.datum:       # day change
                write_day(args.dir, day)
                day.reset(now.date())

            data = inv.read_all()
            day.record(start, data, args.interval)
            watcher.check(start, data)
            update_status(start, data, day, watcher)
            append_csv(os.path.join(args.dir, f"{day.datum}.csv"), POLL_FIELDS, poll_row(now, data, day))
            day.save()

            if data is None:
                fail_streak += 1
                if time.time() - letzter_erfolg > 600:     # nothing for 10 min: reset everything
                    print(f"[{now:%H:%M:%S}] seit 10 min keine Daten - setze Verbindung komplett neu auf", flush=True)
                    inv = Inverter(args.host, args.port, args.unit)
                    letzter_erfolg = time.time()
                if fail_streak in (1, 30) or fail_streak % 360 == 0:
                    print(f"[{now:%H:%M:%S}] keine Antwort ({fail_streak}× in Folge)", flush=True)
            else:
                if fail_streak:
                    print(f"[{now:%H:%M:%S}] wieder verbunden nach {fail_streak} Fehlversuchen", flush=True)
                fail_streak = 0
                letzter_erfolg = time.time()

            time.sleep(max(0.0, args.interval - (time.time() - start)))
    except KeyboardInterrupt:
        day.save(force=True)
        print("\nBeendet. Bisheriger Tag (noch nicht abgeschlossen):", day.summary(), flush=True)


if __name__ == "__main__":
    main()
