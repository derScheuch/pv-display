# Logger

Python scripts that read a Huawei SUN2000 inverter (plus LUNA battery and smart meter) via Modbus TCP
through the SDongle.

| File | Purpose |
|---|---|
| `huawei_poll.py` | One-shot (or looping) readout in the terminal – for testing and quick checks |
| `huawei_logger.py` | Continuous logger: CSV files, daily summary, energy flows, JSON status for the display, push reminder |
| `huawei-logger.service` | systemd unit to run the logger in the background |
| `requirements.txt` | Python dependencies (`pymodbus`) |

## Prerequisites

* **Modbus TCP enabled on the SDongle.** FusionSolar app → device commissioning → connect to the inverter →
  *Settings → Communication configuration → Dongle parameter settings → Modbus TCP* → **Enable (unrestricted)**.
* The dongle's IP address (router device list, name like `SDongleA-…`). Give it a fixed IP in the router.
* Python 3.9+.

## Installation (Raspberry Pi OS)

```bash
mkdir -p ~/huawei-logger && cd ~/huawei-logger
# copy huawei_logger.py, huawei_poll.py, requirements.txt and huawei-logger.service here
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 1. Test the connection

```bash
venv/bin/python huawei_poll.py --host 192.168.178.65
```

You should see model, status, string voltages, PV power, battery and meter values. Typical problems:

| Symptom | Cause / fix |
|---|---|
| `Connection refused` | Modbus TCP not enabled on the dongle |
| `No route to host`, `arp -n <ip>` shows `(incomplete)` | the Wi-Fi dongle is dozing; `ping` it a few times, then retry |
| first request times out, later ones work | normal – the dongle often drops the first request; the scripts retry |
| `Exception response 131 / 0` | another Modbus client is connected, or the dongle is busy (cloud upload). The logger recovers automatically |

The inverter answers on unit ID **1**, the dongle itself on unit ID **100**.

### 2. Run the logger manually

```bash
venv/bin/python huawei_logger.py --host 192.168.178.65 --dir ~/huawei-logger/log
```

Check the JSON status from another machine: `http://<pi-ip>:8765/status`

### 3. Run it as a service

Edit `User`, `WorkingDirectory` and the paths in `huawei-logger.service`, then:

```bash
sudo cp huawei-logger.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now huawei-logger

systemctl status huawei-logger        # running?
journalctl -u huawei-logger -f        # live log
sudo systemctl restart huawei-logger  # after updating the script
sudo systemctl stop huawei-logger     # e.g. to use huawei_poll.py
```

If systemd reports `Failed at step EXEC`, the venv probably belongs to root
(`sudo chown -R <user>:<user> ~/huawei-logger`) or is broken (delete and recreate it).

## Options (`huawei_logger.py`)

| Option | Default | Meaning |
|---|---|---|
| `--host` | `192.168.178.65` | SDongle IP |
| `--port` | `502` | Modbus TCP port |
| `--unit` | `1` | inverter unit ID |
| `--interval` | `20` | seconds between polls |
| `--dir` | `~/pv/log` | output folder |
| `--http-port` | `8765` | port of the JSON status (0 = off) |
| `--ntfy-topic` | – | ntfy topic for the push reminder (off if not set) |
| `--ntfy-test` | – | send a test push and exit |
| `--lat` / `--lon` | Hanover | location for sunrise/sunset |
| `--vorlauf` | `60` | "dusk" starts this many minutes before sunset |
| `--last-min` | `1500` | "large consumer" threshold in W |
| `--soc-max` | `80` | only remind if battery SOC is below this (%) |
| `--minuten` | `10` | condition must hold this many minutes without interruption |
| `--wiederholen` | `30` | repeat the reminder at most every N minutes |

Tip: a dishwasher or oven can trigger the reminder for a few minutes. `--minuten 30` filters those out –
a car charges for hours.

## Output

### `log/YYYY-MM-DD.csv` – one row per poll

Semicolon-separated, decimal comma (opens directly in German Excel/Numbers).

| Column | Meaning |
|---|---|
| `zeit` | timestamp |
| `ok` | 1 = values present, 0 = dongle did not answer |
| `status` | inverter state (`0x0200` = on-grid, `0x0A00` = standby/no irradiation, …) |
| `pv_w` | total PV input power (W) |
| `ost_proz` / `west_proz` | share of the east / west string in % (string 2 = east, string 1 = west) |
| `pv1_u`, `pv1_i`, `pv2_u`, `pv2_i` | string voltages (V) and currents (A) |
| `ac_w` | inverter AC output (W) – from PV and battery |
| `akku_w` | battery power (W): + charging, − discharging |
| `soc` | battery state of charge (%) |
| `netz_w` | grid power at the meter (W): + export, − import |
| `temp` | inverter temperature (°C) |
| `wr_heute` | inverter yield today (kWh, register 32114) |
| `akku_lad_heute` / `akku_ent_heute` | battery charged / discharged today (kWh) |
| `pv_gemessen_kwh` | PV energy integrated by the logger since midnight (kWh) |

House consumption is not a column; compute it as `ac_w − netz_w`.

### `log/tage.csv` – one row per day (written after midnight)

| Column | Meaning |
|---|---|
| `datum` | date |
| `pv_gemessen_kwh` | PV energy integrated from power samples (gaps not interpolated → lower bound) |
| `pv_formel_kwh` | PV yield = inverter yield − battery discharged + battery charged |
| `wr_ertrag_kwh` | inverter yield (AC) |
| `akku_geladen_kwh` / `akku_entladen_kwh` | battery charged / discharged |
| `abfragen_ok` / `abfragen_fehler` | successful / failed polls |
| `luecken_min` / `groesste_luecke_min` | total / longest communication gap (minutes) |
| `eingespeist_ges_kwh` / `bezogen_ges_kwh` | meter totals export / import at the end of the day |
| `app_ertrag_kwh` | empty – fill in the FusionSolar value by hand for comparison |

### JSON status – `GET http://<host>:8765/status`

```json
{
  "ok": true, "zeit": 1794235000, "uhrzeit": "13:27:40", "alter_s": 4,
  "pv_w": 590, "ost_proz": 41, "west_proz": 59,
  "fluss_w": { "pv_haus": 210, "pv_akku": 379, "pv_netz": 0,
               "netz_haus": 0, "akku_haus": 0, "akku_netz": 0 },
  "verbrauch_w": 210, "netz_w": 0, "akku_w": 379, "soc": 39.0,
  "wr_ac_w": 210, "temp": 43.0,
  "heute_kwh": { "ertrag": 7.0, "verbrauch": 4.54, "einspeisung": 0.55, "bezug": 2.56,
                 "pv_gemessen": 6.96, "akku_geladen": 4.57, "akku_entladen": 0.1 },
  "sonne": { "aufgang": "07:32", "untergang": "16:38" },
  "warnung_auto": false
}
```

* `ok` – last poll successful; `alter_s` – age of the values in seconds
* `fluss_w` – estimated flows in W (pv→house, pv→battery, pv→grid, grid→house, battery→house,
  battery→grid). The house side balances exactly; the PV side contains a few % conversion losses.
  Flows below 10 W are reported as 0.
* `heute_kwh` – daily totals. Import/export/consumption start counting at the logger's first sample of the day.
* `warnung_auto` – the "car is probably charging from the battery" condition is currently met

## Push reminder with ntfy

1. Install the **ntfy** app on your phone and subscribe to a hard-to-guess topic (anyone who knows the
   topic can read it), e.g. `pv-<random-number>`.
2. Test: `venv/bin/python huawei_logger.py --ntfy-topic pv-<random-number> --ntfy-test`
3. Add `--ntfy-topic pv-<random-number>` to `ExecStart` in the service file.
