# Modbus notes – Huawei SUN2000 via SDongle

## Connection

* SDongle, Modbus TCP port **502** (older firmware: 6607), must be enabled in the FusionSolar app.
* Unit ID **1** = inverter (battery and meter values are also read through it), unit ID **100** = dongle.
* **Only one client at a time.** A second client causes timeouts and `Exception response 131 / 0`.
* The dongle sits on Wi-Fi and is not always responsive: the first request after connecting is often lost,
  and it sometimes stops answering ARP until it is pinged. It also uploads to the cloud every ~5 minutes and
  is busy during that time.
* The logger reads adjacent registers in blocks (7 requests per cycle), pauses 0.2 s between requests,
  drops and re-opens the connection after errors and resets completely after 10 minutes without data.

## Registers used

All holding registers, big-endian; 32-bit values span two registers.

| Register | Count | Type | Scale | Meaning |
|---|---|---|---|---|
| 30000 | 15 | string | – | model name |
| 32016 / 32017 | 1 / 1 | int16 | /10 V, /100 A | PV string 1 voltage / current |
| 32018 / 32019 | 1 / 1 | int16 | /10 V, /100 A | PV string 2 voltage / current |
| 32064 | 2 | int32 | W | total PV input power |
| 32080 | 2 | int32 | W | active power (inverter AC output) |
| 32087 | 1 | int16 | /10 °C | internal temperature |
| 32089 | 1 | uint16 | – | device status (`0x0200` on-grid, `0x0A00` standby: no irradiation, …) |
| 32106 | 2 | uint32 | /100 kWh | accumulated inverter yield |
| 32114 | 2 | uint32 | /100 kWh | inverter yield today |
| 37113 | 2 | int32 | W | meter active power (+ export, − import) |
| 37119 | 2 | int32 | /100 kWh | meter total exported |
| 37121 | 2 | int32 | /100 kWh | meter total imported |
| 37760 | 1 | uint16 | /10 % | battery state of charge |
| 37765 | 2 | int32 | W | battery power (+ charging, − discharging) |
| 37780 / 37782 | 2 / 2 | uint32 | /100 kWh | battery total charged / discharged |
| 37784 / 37786 | 2 / 2 | uint32 | /100 kWh | battery charged / discharged today |

Sources: [huawei_solar / huawei-solar-lib](https://github.com/wlcrs/huawei_solar),
[debacher.de register list](https://www.debacher.de/wiki/Sun2000_Modbus_Register).
The FusionCharge wallbox (firmware V100R023C10SPC120) did not answer via the dongle in our tests.

## Observations on this installation

* **String assignment:** string 1 has 16 modules (west, ~550 V), string 2 has 9 modules (east, ~290 V).
  The voltage per module (≈32–34 V at MPP) tells you which string has how many modules.
* **String power vs. total PV power:** V × I of both strings is ~7 % higher than register 32064.
  The logger uses 32064 as reference and reports only the east/west *share*.

## Why the yield differs from the FusionSolar app

Three different "PV yield" figures, example from one day:

| Figure | kWh | What it is |
|---|---|---|
| `pv_gemessen` | 10.95 | PV input power integrated over the day (DC side) |
| `pv_formel` | 10.29 | inverter yield − battery discharged + battery charged (after inverter conversion losses) |
| FusionSolar app | 9.60 | additionally minus the system's own consumption |

* `pv_gemessen` and `pv_formel` match while PV goes straight into the battery (DC → DC) and drift apart
  when energy passes the inverter (PV → AC, battery → AC): that is the conversion loss (~4 % that day).
* The app reads the same counters (battery charged identical, inverter yield identical apart from its
  ~5 min delay). Plugging the app's own counters into the formula gives 10.40 kWh, yet it shows 9.60:
  it subtracts ≈0.8 kWh per day. According to the FusionSolar manual (as quoted in
  [this issue](https://github.com/andiwirz/com.huawei.fusionsolar/issues/36)), plant yield =
  inverter yield + battery charge − battery discharge − **inverter consumption**.
* At night the app shows grid import > device consumption (e.g. 0.56 vs. 0.46 kWh after 1.5 h) and books
  the difference as negative revenue – the system's own consumption, here ~40 W on average.
* Grid import and export agree between the logger and the app (± rounding), so the meter side is consistent.
* The app's "consumption" is derived from its PV yield, so it is lower by the same amount.

**Does the Modbus polling cause it? No.** Test: app's "from grid − consumed by devices" at night.

| Night | Logger | Grid − devices | Average |
|---|---|---|---|
| Sunday, 00:00–09:19 | running (20 s) | 0.40 kWh | ≈ 43 W |
| Monday, 00:00–08:44 | **stopped** | 0.81 kWh | ≈ 93 W |

Without the logger the difference was even larger. It varies with the battery state rather than with polling:
on Monday the battery was empty all night (5 % → 7 %), so part of the grid import went into keeping the
battery at its minimum charge (≈ 0.1 kWh plus losses), and the battery's electronics stay awake.
