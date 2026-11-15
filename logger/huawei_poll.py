#!/usr/bin/env python3
"""
Read a Huawei SUN2000 + SDongle + LUNA battery via Modbus TCP (one-shot or in a loop).

Installation:   pip3 install pymodbus
Usage:          python3 huawei_poll.py              (poll once)
                python3 huawei_poll.py --loop 10    (every 10 s, Ctrl+C to stop)
                python3 huawei_poll.py --host 192.168.178.65 --unit 1

Note: the dongle allows only ONE Modbus connection at a time.

PV yield: the register "Daily energy yield" (32114) is the inverter yield
(AC output). With a battery it includes battery discharge and misses the
PV energy that went into the battery. PV yield is therefore calculated as
    PV yield = inverter yield - battery discharged + battery charged
(source: huawei_solar wiki "Daily Solar Yield"). Not valid if the battery
is also charged from the grid.
"""

import argparse
import struct
import sys
import time
from datetime import datetime

from pymodbus.client import ModbusTcpClient

# key: (register, register count, type, divisor)
REGISTERS = {
    "modell":        (30000, 15, "str", 1),
    "status":        (32089,  1, "u16", 1),
    "pv1_u":         (32016,  1, "i16", 10),
    "pv1_i":         (32017,  1, "i16", 100),
    "pv2_u":         (32018,  1, "i16", 10),
    "pv2_i":         (32019,  1, "i16", 100),
    "pv_leistung":   (32064,  2, "i32", 1),      # W
    "ac_leistung":   (32080,  2, "i32", 1),      # W
    "temperatur":    (32087,  1, "i16", 10),     # °C
    "wr_heute":      (32114,  2, "u32", 100),    # kWh
    "wr_gesamt":     (32106,  2, "u32", 100),    # kWh
    "soc":           (37760,  1, "u16", 10),     # %
    "akku_leistung": (37765,  2, "i32", 1),      # W, + charging / - discharging
    "akku_lad_ges":  (37780,  2, "u32", 100),    # kWh
    "akku_ent_ges":  (37782,  2, "u32", 100),    # kWh
    "akku_lad_heute":(37784,  2, "u32", 100),    # kWh
    "akku_ent_heute":(37786,  2, "u32", 100),    # kWh
    "netz":          (37113,  2, "i32", 1),      # W, + export / - import
    "eingespeist":   (37119,  2, "i32", 100),    # kWh
    "bezogen":       (37121,  2, "i32", 100),    # kWh
}

STRINGS = [("Ost", "pv2"), ("West", "pv1")]   # PV1 = 16 modules west (~550 V), PV2 = 9 modules east (~290 V)

STATUS = {
    0x0000: "Standby: Initialisierung",
    0x0001: "Standby: Isolationsprüfung",
    0x0002: "Standby: Sonneneinstrahlung prüfen",
    0x0003: "Standby: Netzprüfung",
    0x0100: "Start",
    0x0200: "Netzbetrieb",
    0x0201: "Netzbetrieb: Leistungsbegrenzung",
    0x0202: "Netzbetrieb: Eigenreduzierung",
    0x0300: "Abgeschaltet: Fehler",
    0x0301: "Abgeschaltet: Befehl",
    0x0307: "Abgeschaltet: Wenig Licht",
    0x0401: "Netzplanung",
    0x0A00: "Standby: Keine Einstrahlung",
}


def decode(regs, typ):
    raw = struct.pack(">" + "H" * len(regs), *regs)
    if typ == "str":
        s = raw.decode("ascii", errors="ignore").split("\x00")[0].strip()
        i = s.find("SUN2000", 1)          # cut off trailing bytes after the actual name
        return s[:i] if i > 0 else s
    fmt = {"u16": ">H", "i16": ">h", "u32": ">I", "i32": ">i"}[typ]
    return struct.unpack(fmt, raw)[0]


def read(client, unit, address, count, retries=3):
    """Reads holding registers, retries on errors (the dongle often drops the first request)."""
    for _ in range(retries):
        try:
            try:
                rr = client.read_holding_registers(address, count=count, device_id=unit)  # pymodbus >= 3.10
            except TypeError:
                rr = client.read_holding_registers(address, count=count, slave=unit)      # older 3.x
            regs = getattr(rr, "registers", None)
            if not rr.isError() and regs and len(regs) == count:
                return regs
            if getattr(rr, "exception_code", None) == 2:   # Illegal data address
                return None
        except Exception:
            pass
        time.sleep(1)
    return None


def read_all(client, unit):
    data = {}
    for key, (addr, count, typ, div) in REGISTERS.items():
        regs = read(client, unit, addr, count)
        if regs is None:
            continue
        val = decode(regs, typ)
        data[key] = val if typ == "str" or key == "status" else val / div
    return data


def fmt(v, dec=0, unit=""):
    s = f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")   # German number format
    return f"{s} {unit}".rstrip()


def line(name, text):
    print(f"  {name:<27} {text}")


def show(d):
    g = d.get
    print(f"\n── {datetime.now():%d.%m.%Y %H:%M:%S} " + "─" * 34)

    if "modell" in d:
        line("Modell", d["modell"])
    if "status" in d:
        line("Status", STATUS.get(d["status"], f"0x{d['status']:04X}"))
    if "temperatur" in d:
        line("Temperatur", fmt(d["temperatur"], 1, "°C"))

    print("\n  PV-Module")
    summe = 0.0
    for name, p in STRINGS:
        u, i = g(f"{p}_u"), g(f"{p}_i")
        if u is None or i is None:
            continue
        w = u * i
        summe += w
        line(f"  {name}", f"{fmt(w, 0, 'W'):>8}   ({fmt(u, 1, 'V')} × {fmt(i, 2, 'A')})")
    line("  Gesamt (Strings)", f"{fmt(summe, 0, 'W'):>8}")
    if "pv_leistung" in d:
        line("  Gesamt (Wechselrichter)", f"{fmt(d['pv_leistung'], 0, 'W'):>8}")

    print("\n  Leistung jetzt")
    if "ac_leistung" in d:
        line("  Wechselrichter AC", fmt(d["ac_leistung"], 0, "W"))
    if "akku_leistung" in d:
        a = d["akku_leistung"]
        line("  Akku", fmt(a, 0, "W") + ("  (lädt)" if a > 0 else "  (entlädt)" if a < 0 else ""))
    if "soc" in d:
        line("  Akku Ladestand", fmt(d["soc"], 1, "%"))
    if "netz" in d:
        n = d["netz"]
        line("  Netz", fmt(n, 0, "W") + ("  (Einspeisung)" if n > 0 else "  (Bezug)" if n < 0 else ""))

    print("\n  Energie heute")
    if all(k in d for k in ("wr_heute", "akku_lad_heute", "akku_ent_heute")):
        pv = d["wr_heute"] - d["akku_ent_heute"] + d["akku_lad_heute"]
        line("  PV-Ertrag (berechnet)", fmt(pv, 2, "kWh"))
    if "wr_heute" in d:
        line("  Wechselrichter-Ertrag", fmt(d["wr_heute"], 2, "kWh"))
    if "akku_lad_heute" in d:
        line("  Akku geladen", fmt(d["akku_lad_heute"], 2, "kWh"))
    if "akku_ent_heute" in d:
        line("  Akku entladen", fmt(d["akku_ent_heute"], 2, "kWh"))

    print("\n  Energie gesamt")
    if all(k in d for k in ("wr_gesamt", "akku_lad_ges", "akku_ent_ges")):
        pv = d["wr_gesamt"] - d["akku_ent_ges"] + d["akku_lad_ges"]
        line("  PV-Ertrag (berechnet)", fmt(pv / 1000, 2, "MWh"))
    if "wr_gesamt" in d:
        line("  Wechselrichter-Ertrag", fmt(d["wr_gesamt"] / 1000, 2, "MWh"))
    if "akku_lad_ges" in d:
        line("  Akku geladen", fmt(d["akku_lad_ges"], 0, "kWh"))
    if "akku_ent_ges" in d:
        line("  Akku entladen", fmt(d["akku_ent_ges"], 0, "kWh"))
    if "eingespeist" in d:
        line("  Eingespeist", fmt(d["eingespeist"], 0, "kWh"))
    if "bezogen" in d:
        line("  Bezogen", fmt(d["bezogen"], 0, "kWh"))


def main():
    ap = argparse.ArgumentParser(description="Huawei SUN2000 per Modbus TCP auslesen")
    ap.add_argument("--host", default="192.168.178.65")
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--unit", type=int, default=1, help="Slave-ID des Wechselrichters (Standard 1)")
    ap.add_argument("--loop", type=int, metavar="SEK", help="alle SEK Sekunden wiederholen")
    args = ap.parse_args()

    client = ModbusTcpClient(args.host, port=args.port, timeout=5)
    if not client.connect():
        sys.exit(f"Keine Verbindung zu {args.host}:{args.port} – Dongle wach? (ping {args.host})")
    time.sleep(1)  # the dongle needs a moment after connecting

    try:
        while True:
            show(read_all(client, args.unit))
            if not args.loop:
                break
            time.sleep(args.loop)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()


if __name__ == "__main__":
    main()
