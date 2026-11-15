// PV energy-flow display for ESP32 + ST7735 TFT (160 x 128), values from the logger (Raspberry Pi).
// Four circles (PV top, battery left, grid right, house bottom) connected by lanes
// on which dots move from source to destination while energy is flowing.
// Libraries: TFT_eSPI (pins in the TFT_eSPI setup file), ArduinoJson (v7)
//
// Setup: if the ESP32 cannot find its Wi-Fi (or none is stored yet), it opens
// the access point "PV-Anzeige". Connect to it (phone/laptop); the setup page opens
// automatically (otherwise http://192.168.4.1). SSID and logger URL are pre-filled with the stored
// values; leave the password empty to keep the stored one.
// Re-run setup while running: hold the BOOT button for 3 seconds.
// Change only the logger URL while running: http://pv-anzeige.local (or the ESP32's IP).

#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>
#include <SPI.h>

// ---------------------------------------------------------------- settings
const char* AP_NAME     = "PV-Anzeige";                            // access point for setup
const char* HOSTNAME    = "pv-anzeige";                            // while running: http://pv-anzeige.local
const char* URL_DEFAULT = "http://192.168.178.111:8765/status";    // default shown on the setup page
const int   CONFIG_PIN  = 0;                                       // BOOT button (XIAO ESP32-S3: GPIO0)
const int   PORTAL_TIMEOUT_S = 300;                                // setup portal stays open max. 5 min, then reboot
const int   DREHUNG = 3;      // display orientation: 1 = landscape, 3 = landscape rotated by 180°
String statusUrl, wlanSsid, wlanPass;                              // loaded from flash (Preferences)
bool einrichtungAngefordert = false;
unsigned long letzteAbfrage = 0;
const unsigned long ABFRAGE_MS = 10000;                           // fetch data every 10 s
const unsigned long FRAME_MS   = 40;                              // animation ~25 frames/s
const int AKTUELL_S = 60;     // older data: red frame, animation stops, values stay visible
const int WEG_S     = 120;    // older data: hide the values in the circles (daily totals stay)
#define DEBUG 1                                                   // 1 = print values to Serial

// ---------------------------------------------------------------- colors
#define C_PV      TFT_YELLOW
#define C_AKKU    TFT_GREEN
#define C_NETZ    0xFB2C          // light red
#define C_HAUS    0x5D1F          // light blue
#define C_TEXT    TFT_WHITE
#define C_BAHN    0x2945          // dark grey: lane without flow
#define C_GRAU    0x8410
#define C_EINSP   0xFD20          // orange

TFT_eSPI tft = TFT_eSPI();

// ---------------------------------------------------------------- data
struct PVData {
  bool ok = false;
  int alter = 9999;
  int pv = 0, soc = 0, verbrauch = 0, netz = 0;
  int ostProz = -1, westProz = -1;
  int pvHaus = 0, pvAkku = 0, pvNetz = 0, akkuHaus = 0, akkuNetz = 0, netzHaus = 0;
  float ertragHeute = -1, verbrauchHeute = -1, bezugHeute = -1, einspHeute = -1;
  bool warnungAuto = false;
  String uhrzeit = "";
};
PVData pv;

// ---------------------------------------------------------------- geometry
// circles
const int R = 24;
const int PV_X = 80,   PV_Y = 24;
const int AK_X = 24,   AK_Y = 64;
const int NE_X = 136,  NE_Y = 64;
const int HA_X = 80,   HA_Y = 104;

// lanes as axis-parallel polylines, each 2 px wide, 3 px apart from the neighboring lane
struct Pt { int16_t x, y; };
struct Bahn {
  Pt p[3];
  uint8_t n;          // number of points
  uint16_t farbe;     // color of the source
  int* wert;          // points to the flow value in pv
  float phase;        // animation position
  int laenge;         // total length in px
};

Bahn bahnen[] = {
  // PV -> house: straight down
  {{{80, PV_Y + R}, {80, HA_Y - R}}, 2, C_PV, &pv.pvHaus},
  // PV -> battery: down, then left
  {{{76, PV_Y + R}, {76, 60}, {AK_X + R, 60}}, 3, C_PV, &pv.pvAkku},
  // PV -> grid: down, then right
  {{{84, PV_Y + R}, {84, 60}, {NE_X - R, 60}}, 3, C_PV, &pv.pvNetz},
  // battery -> house: right, then down
  {{{AK_X + R, 68}, {76, 68}, {76, HA_Y - R}}, 3, C_AKKU, &pv.akkuHaus},
  // grid -> house: left, then down
  {{{NE_X - R, 68}, {84, 68}, {84, HA_Y - R}}, 3, C_NETZ, &pv.netzHaus},
  // battery -> grid: straight across (should be 0)
  {{{AK_X + R, 64}, {NE_X - R, 64}}, 2, C_AKKU, &pv.akkuNetz},
};
const int N_BAHNEN = sizeof(bahnen) / sizeof(bahnen[0]);

const int ABSTAND = 10;   // px between two dots on a lane
const int PUNKT   = 3;    // length of a dot in px

void initBahnen() {
  for (int i = 0; i < N_BAHNEN; ++i) {
    Bahn& b = bahnen[i];
    b.laenge = 0;
    for (int k = 1; k < b.n; ++k)
      b.laenge += abs(b.p[k].x - b.p[k - 1].x) + abs(b.p[k].y - b.p[k - 1].y);
    b.phase = 0;
  }
}

// set the pixel at position d along the lane (2 px wide) to color c
void bahnPixel(const Bahn& b, int d, uint16_t c) {
  if (d < 0 || d >= b.laenge) return;
  for (int k = 1; k < b.n; ++k) {
    int dx = b.p[k].x - b.p[k - 1].x, dy = b.p[k].y - b.p[k - 1].y;
    int len = abs(dx) + abs(dy);
    if (d <= len) {
      int x = b.p[k - 1].x + (dx > 0 ? d : dx < 0 ? -d : 0);
      int y = b.p[k - 1].y + (dy > 0 ? d : dy < 0 ? -d : 0);
      tft.drawPixel(x, y, c);
      if (dx == 0) tft.drawPixel(x + 1, y, c);   // vertical: width to the right
      else         tft.drawPixel(x, y + 1, c);   // horizontal: width downwards
      return;
    }
    d -= len;
  }
}

uint16_t gedimmt(uint16_t c) {           // darken a color to ~40 %
  uint8_t r = (c >> 11) & 0x1F, g = (c >> 5) & 0x3F, bl = c & 0x1F;
  return ((r * 2 / 5) << 11) | ((g * 2 / 5) << 5) | (bl * 2 / 5);
}

void zeichneBahn(const Bahn& b, bool mitWerten) {
  uint16_t c = (mitWerten && *b.wert > 0) ? gedimmt(b.farbe) : C_BAHN;
  for (int d = 0; d < b.laenge; ++d) bahnPixel(b, d, c);
}

// draw (bright) or erase (lane color) the dots of a lane at the given phase
void punkte(const Bahn& b, float phase, bool zeigen) {
  uint16_t c = zeigen ? b.farbe : gedimmt(b.farbe);
  for (int start = (int)phase % ABSTAND; start < b.laenge; start += ABSTAND)
    for (int k = 0; k < PUNKT; ++k) bahnPixel(b, start + k, c);
}

// speed grows with power (square root, so small flows stay visible)
float tempo(int w) {
  float t = 0.25 + sqrt((float)w) / 40.0;     // 100 W ~ 0.5 px/frame, 3 kW ~ 1.6 px/frame
  return t > 2.5 ? 2.5 : t;
}

// ---------------------------------------------------------------- text

String kurz(int w) {                        // 590W / 1,2kW
  w = abs(w);
  if (w < 1000) return String(w) + "W";
  String s = String(w / 1000.0, w < 10000 ? 1 : 0) + "kW";
  s.replace('.', ',');
  return s;
}

void kreis(int x, int y, uint16_t farbe, const String& oben, const String& unten, bool aktiv) {
  tft.fillCircle(x, y, R, TFT_BLACK);
  tft.drawCircle(x, y, R, aktiv ? farbe : gedimmt(farbe));
  tft.drawCircle(x, y, R - 1, aktiv ? farbe : gedimmt(farbe));
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(aktiv ? farbe : C_GRAU, TFT_BLACK);
  tft.drawString(oben, x, unten.length() ? y - 9 : y, 1);   // small label (centered if there is no value)
  tft.setTextColor(aktiv ? C_TEXT : C_GRAU, TFT_BLACK);
  tft.drawString(unten, x, y + 5, 2);         // large value (font 2, 16 px)
}

// ---------------------------------------------------------------- screens

void tageswert(int y, float kwh, uint16_t farbe) {
  if (kwh < 0) return;                         // no value (yet)
  String t = String(kwh, 1) + "kWh";
  t.replace('.', ',');
  tft.setTextColor(farbe, TFT_BLACK);
  tft.drawString(t, 3, y, 1);
}

// aktuell = data is fresh (otherwise red frame), mitWerten = show values in the circles
void zeigeFluss(bool aktuell, bool mitWerten) {
  tft.fillScreen(TFT_BLACK);
  for (int i = 0; i < N_BAHNEN; ++i) zeichneBahn(bahnen[i], mitWerten);

  if (mitWerten) {
    int akku = pv.akkuHaus + pv.akkuNetz + pv.pvAkku;
    String netzText = pv.netz > 5 ? "Netz +" : pv.netz < -5 ? "Netz -" : "Netz";
    kreis(PV_X, PV_Y, C_PV,   "PV",                 kurz(pv.pv),        pv.pv > 10);
    kreis(AK_X, AK_Y, C_AKKU, String(pv.soc) + "%", kurz(akku),         akku > 10);
    kreis(NE_X, NE_Y, C_NETZ, netzText,             kurz(pv.netz),      abs(pv.netz) > 10);
    kreis(HA_X, HA_Y, C_HAUS, "Haus",               kurz(pv.verbrauch), pv.verbrauch > 10);

    tft.setTextColor(C_GRAU, TFT_BLACK);       // top: like on a map, west left, east right
    if (pv.ostProz >= 0) {
      tft.setTextDatum(TL_DATUM); tft.drawString("West " + String(pv.westProz) + "%", 3, 3, 1);
      tft.setTextDatum(TR_DATUM); tft.drawString("Ost " + String(pv.ostProz) + "%", 157, 3, 1);
    }
  } else {                                     // too old: empty circles only
    kreis(PV_X, PV_Y, C_PV,   "PV",   "", false);
    kreis(AK_X, AK_Y, C_AKKU, "Akku", "", false);
    kreis(NE_X, NE_Y, C_NETZ, "Netz", "", false);
    kreis(HA_X, HA_Y, C_HAUS, "Haus", "", false);
  }

  // bottom left: daily totals (always), one line each in the matching color
  tft.setTextDatum(TL_DATUM);
  tageswert(94,  pv.ertragHeute,    C_PV);       // yield
  tageswert(102, pv.verbrauchHeute, C_HAUS);     // house consumption
  tageswert(110, pv.bezugHeute,     C_NETZ);     // from the grid
  tageswert(118, pv.einspHeute,     C_EINSP);    // to the grid

  // bottom right: timestamp of the values, red when stale
  tft.setTextColor(aktuell ? C_GRAU : TFT_RED, TFT_BLACK);
  tft.setTextDatum(BR_DATUM); tft.drawString(pv.uhrzeit.substring(0, 5), 157, 125, 1);

  if (!aktuell) {                              // red frame, 2 px
    tft.drawRect(0, 0, 160, 128, TFT_RED);
    tft.drawRect(1, 1, 158, 126, TFT_RED);
  }
}

void animiere() {
  for (int i = 0; i < N_BAHNEN; ++i) {
    Bahn& b = bahnen[i];
    if (*b.wert <= 0) continue;
    punkte(b, b.phase, false);                                  // erase old dots
    b.phase += tempo(*b.wert);
    if (b.phase >= 1000) b.phase -= 1000;
    punkte(b, b.phase, true);                                   // draw new dots
  }
}

void zeigeWarnung() {
  tft.fillScreen(TFT_RED);
  tft.setTextColor(TFT_WHITE, TFT_RED);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("Bitte Auto", 80, 34, 4);
  tft.drawString("abklemmen!", 80, 62, 4);
  tft.drawString("Akku " + String(pv.soc) + " %  -  gibt " + kurz(pv.akkuHaus) + " ab", 80, 96, 2);
  tft.drawString(pv.uhrzeit, 80, 116, 1);
}

// ---------------------------------------------------------------- Wi-Fi + data

// ---------------------------------------------------------------- persistent settings

Preferences prefs;
WebServer server(80);
DNSServer dns;
bool tftBereit = false;

void ladeEinstellungen() {
  prefs.begin("pvanzeige", true);
  wlanSsid  = prefs.getString("ssid", "");
  wlanPass  = prefs.getString("pass", "");
  statusUrl = prefs.getString("url", URL_DEFAULT);
  einrichtungAngefordert = prefs.getString("portal", "") == "1";
  prefs.end();
}

void speichere(const char* key, const String& wert) {
  prefs.begin("pvanzeige", false);
  prefs.putString(key, wert);
  prefs.end();
}

String html(const String& s) {          // escape special characters for HTML fields
  String r = s;
  r.replace("&", "&amp;"); r.replace("\"", "&quot;"); r.replace("'", "&#39;");
  r.replace("<", "&lt;");  r.replace(">", "&gt;");
  return r;
}

const char* SEITE_KOPF =
  "<!DOCTYPE html><html><head><meta charset='utf-8'>"
  "<meta name='viewport' content='width=device-width,initial-scale=1'><title>PV-Anzeige</title>"
  "<style>body{font-family:sans-serif;max-width:420px;margin:20px auto;padding:0 12px;background:#111;color:#eee}"
  "h1{color:#fd0;font-size:1.4em}label{display:block;margin-top:14px;color:#aaa}"
  "input{width:100%;padding:8px;font-size:1em;box-sizing:border-box;margin-top:4px}"
  "button{margin-top:20px;padding:10px 18px;font-size:1em;background:#fd0;border:0;border-radius:4px}"
  "small{color:#888}</style></head><body>";

// ---------------------------------------------------------------- Display

void initTft() {                       // initialize the display only AFTER starting Wi-Fi
  if (tftBereit) return;
  tft.init();
  tft.setRotation(DREHUNG);
  tft.fillScreen(TFT_BLACK);
  tftBereit = true;
}

void zeigeText(const char* titel, const String& z1, const String& z2, const String& z3, const String& z4) {
  initTft();
  tft.fillScreen(TFT_BLACK);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(TFT_YELLOW, TFT_BLACK); tft.drawString(titel, 80, 14, 2);
  tft.setTextColor(C_TEXT, TFT_BLACK);     tft.drawString(z1, 80, 42, 2);
  tft.setTextColor(TFT_GREEN, TFT_BLACK);  tft.drawString(z2, 80, 62, 2);
  tft.setTextColor(C_TEXT, TFT_BLACK);     tft.drawString(z3, 80, 82, 2);
  tft.setTextColor(TFT_GREEN, TFT_BLACK);  tft.drawString(z4, 80, 104, 2);
}

// ---------------------------------------------------------------- setup portal (own access point)

String netzListe;                       // <option> list of the networks found

void portalSeite() {
  String p = SEITE_KOPF;
  p += "<h1>PV-Anzeige einrichten</h1><form method='post' action='/speichern'>";
  p += "<label>WLAN-Name</label><input name='ssid' list='netze' value='" + html(wlanSsid) + "'>";
  p += "<datalist id='netze'>" + netzListe + "</datalist>";
  p += "<label>WLAN-Passwort</label><input name='pass' type='password' placeholder='";
  p += wlanPass.length() ? "leer lassen = unverändert" : "Passwort";
  p += "'>";
  p += "<label>Logger-Adresse</label><input name='url' value='" + html(statusUrl) + "'>";
  p += "<small>z. B. http://192.168.178.111:8765/status</small>";
  p += "<br><button type='submit'>Speichern und neu starten</button></form></body></html>";
  server.send(200, "text/html; charset=utf-8", p);
}

void portalSpeichern() {
  String ssid = server.arg("ssid"); ssid.trim();
  String pass = server.arg("pass");
  String url  = server.arg("url");  url.trim();
  if (ssid.length()) speichere("ssid", ssid);
  if (pass.length()) speichere("pass", pass);          // empty = keep the old password
  if (url.length())  speichere("url", url);
  server.send(200, "text/html; charset=utf-8",
              String(SEITE_KOPF) + "<h1>Gespeichert</h1><p>Die Anzeige startet neu und verbindet sich mit <b>"
              + html(ssid) + "</b>.</p></body></html>");
  Serial.println("Einstellungen gespeichert, Neustart");
  delay(1500);
  ESP.restart();
}

// opens the setup access point; does not return (reboots after saving or timeout)
void starteEinrichtung() {
  Serial.println("Starte Einrichtung ...");
  WiFi.disconnect(true);
  WiFi.mode(WIFI_AP_STA);
  int n = WiFi.scanNetworks();                         // networks for the selection list
  netzListe = "";
  for (int i = 0; i < n; ++i) netzListe += "<option value='" + html(WiFi.SSID(i)) + "'>";
  WiFi.softAP(AP_NAME);
  delay(200);
  dns.start(53, "*", WiFi.softAPIP());                 // all host names -> setup page

  zeigeText("Einrichtung", "Mit dem WLAN", AP_NAME, "verbinden, dann", "192.168.4.1");
  Serial.printf("Einrichtung: WLAN '%s', http://192.168.4.1\n", AP_NAME);

  server.on("/", HTTP_GET, portalSeite);
  server.on("/speichern", HTTP_POST, portalSpeichern);
  server.onNotFound([]() {                             // captive-portal checks from phones -> open setup page
    server.sendHeader("Location", "http://192.168.4.1/", true);
    server.send(302, "text/plain", "");
  });
  server.begin();

  unsigned long start = millis();
  while (millis() - start < (unsigned long)PORTAL_TIMEOUT_S * 1000UL) {
    dns.processNextRequest();
    server.handleClient();
    delay(5);
  }
  Serial.println("Einrichtung abgelaufen, Neustart");
  ESP.restart();                                       // Wi-Fi is retried afterwards
}

// ---------------------------------------------------------------- normal operation

// page on the home network: change only the logger URL
void betriebSeite() {
  String p = SEITE_KOPF;
  p += "<h1>PV-Anzeige</h1>";
  p += "<p><small>WLAN: " + html(WiFi.SSID()) + " &middot; IP: " + WiFi.localIP().toString() + "</small></p>";
  p += "<form method='post' action='/url'><label>Logger-Adresse</label>";
  p += "<input name='url' value='" + html(statusUrl) + "'>";
  p += "<button type='submit'>Übernehmen</button></form>";
  p += "<p><small>WLAN ändern: BOOT-Taste an der Anzeige 3 Sekunden drücken.</small></p></body></html>";
  server.send(200, "text/html; charset=utf-8", p);
}

void betriebUrl() {
  String url = server.arg("url"); url.trim();
  if (url.length()) {
    statusUrl = url;
    speichere("url", url);
    Serial.println("Neue Logger-Adresse: " + url);
    letzteAbfrage = millis() - ABFRAGE_MS;             // fetch immediately from the new URL
  }
  server.sendHeader("Location", "/", true);
  server.send(303, "text/plain", "");
}

// connects to the stored Wi-Fi, otherwise opens the setup portal
void wlanStarten() {
  ladeEinstellungen();
  if (einrichtungAngefordert) {                        // requested via BOOT button
    speichere("portal", "");
    starteEinrichtung();
  }
  if (!wlanSsid.length()) starteEinrichtung();         // never configured

  WiFi.setHostname(HOSTNAME);
  WiFi.mode(WIFI_STA);
  WiFi.begin(wlanSsid.c_str(), wlanPass.c_str());
  zeigeText("PV-Anzeige", "Verbinde mit", wlanSsid, "", "");   // display after Wi-Fi start

  for (int i = 0; i < 100 && WiFi.status() != WL_CONNECTED; ++i) delay(200);   // max. 20 s
  if (WiFi.status() != WL_CONNECTED) starteEinrichtung();

  Serial.print("Verbunden mit "); Serial.print(WiFi.SSID());
  Serial.print(", IP "); Serial.println(WiFi.localIP());
  Serial.println("Logger-Adresse: " + statusUrl);

  MDNS.begin(HOSTNAME);                                // http://pv-anzeige.local
  server.on("/", HTTP_GET, betriebSeite);
  server.on("/url", HTTP_POST, betriebUrl);
  server.begin();
  zeigeText("PV-Anzeige", "Verbunden", WiFi.localIP().toString(), "Einstellungen:", String(HOSTNAME) + ".local");
  delay(2500);
}

// while running: restore a lost connection
bool setupWifi() {
  if (WiFi.status() == WL_CONNECTED) return true;
  Serial.println("WLAN weg, verbinde neu ...");
  WiFi.reconnect();
  for (int i = 0; i < 50 && WiFi.status() != WL_CONNECTED; ++i) delay(200);
  return WiFi.status() == WL_CONNECTED;
}

// BOOT button held for 3 s -> open setup portal
void pruefeTaste() {
  static unsigned long gedruecktSeit = 0;
  if (digitalRead(CONFIG_PIN) == LOW) {
    if (!gedruecktSeit) gedruecktSeit = millis();
    if (millis() - gedruecktSeit > 3000) {             // remember the request and reboot -> setup portal
      Serial.println("Einrichtung per Taste angefordert, Neustart");
      zeigeText("Einrichtung", "", "startet ...", "", "");
      speichere("portal", "1");
      delay(500);
      ESP.restart();
    }
  } else {
    gedruecktSeit = 0;
  }
}

bool getStatus() {
  if (!setupWifi()) return false;
  HTTPClient http;
  http.setTimeout(5000);
  http.begin(statusUrl);
  int code = http.GET();
  if (code != 200) { Serial.printf("HTTP-Fehler %d\n", code); http.end(); return false; }

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, http.getStream());
  http.end();
  if (err) { Serial.print("JSON-Fehler: "); Serial.println(err.c_str()); return false; }
  if (doc["zeit"].isNull()) { Serial.println("Logger hat noch keine Daten"); return false; }  // keep the old values

  pv.ok          = doc["ok"] | false;
  pv.alter       = doc["alter_s"] | 9999;
  pv.pv          = doc["pv_w"] | 0;
  pv.soc         = (int)round(doc["soc"] | 0.0);
  pv.verbrauch   = doc["verbrauch_w"] | 0;
  pv.netz        = doc["netz_w"] | 0;                 // + export / - import
  pv.ostProz     = doc["ost_proz"].isNull()  ? -1 : doc["ost_proz"].as<int>();
  pv.westProz    = doc["west_proz"].isNull() ? -1 : doc["west_proz"].as<int>();
  pv.pvHaus      = doc["fluss_w"]["pv_haus"]   | 0;
  pv.pvAkku      = doc["fluss_w"]["pv_akku"]   | 0;
  pv.pvNetz      = doc["fluss_w"]["pv_netz"]   | 0;
  pv.akkuHaus    = doc["fluss_w"]["akku_haus"] | 0;
  pv.akkuNetz    = doc["fluss_w"]["akku_netz"] | 0;
  pv.netzHaus    = doc["fluss_w"]["netz_haus"] | 0;
  JsonVariant h = doc["heute_kwh"];
  pv.ertragHeute    = h["ertrag"].isNull()      ? -1 : h["ertrag"].as<float>();
  pv.verbrauchHeute = h["verbrauch"].isNull()   ? -1 : h["verbrauch"].as<float>();
  pv.bezugHeute     = h["bezug"].isNull()       ? -1 : h["bezug"].as<float>();
  pv.einspHeute     = h["einspeisung"].isNull() ? -1 : h["einspeisung"].as<float>();
  pv.warnungAuto = doc["warnung_auto"] | false;
  pv.uhrzeit     = String(doc["uhrzeit"] | "");

#if DEBUG
  Serial.printf("PV %d W | Haus %d W | Netz %d W | Akku %d %% | PV>H %d PV>A %d PV>N %d A>H %d A>N %d N>H %d\n",
                pv.pv, pv.verbrauch, pv.netz, pv.soc, pv.pvHaus, pv.pvAkku, pv.pvNetz,
                pv.akkuHaus, pv.akkuNetz, pv.netzHaus);
#endif
  return true;
}

// ---------------------------------------------------------------- main loop

bool hatDaten = false;
unsigned long datenStand = 0;                // millis() timestamp at which the values were measured
unsigned long letzterFrame = 0;
bool animieren = false;

int datenAlter() {                           // age of the displayed values in seconds
  return hatDaten ? (millis() - datenStand) / 1000 : 99999;
}

void setup() {
  Serial.begin(115200);
  pinMode(CONFIG_PIN, INPUT_PULLUP);
  initBahnen();
  wlanStarten();               // Wi-Fi first (setup if needed), then display
  initTft();
  letzteAbfrage = millis() - ABFRAGE_MS;   // fetch immediately
}

void loop() {
  server.handleClient();       // settings page on the home network
  pruefeTaste();
  unsigned long jetzt = millis();

  if (jetzt - letzteAbfrage >= ABFRAGE_MS) {
    letzteAbfrage = jetzt;
    if (getStatus()) {                       // logger reachable: take the age of the values from the logger
      hatDaten = true;
      datenStand = jetzt - (unsigned long)pv.alter * 1000UL;
    }                                        // otherwise: keep the old values, they simply keep aging
    int alter = datenAlter();
    bool aktuell = alter <= AKTUELL_S;
    Serial.printf("Datenalter %d s\n", alter);

    if (aktuell && pv.warnungAuto) { animieren = false; zeigeWarnung(); }
    else {
      zeigeFluss(aktuell, alter <= WEG_S);
      animieren = aktuell;
    }
  }

  if (animieren && jetzt - letzterFrame >= FRAME_MS) {
    letzterFrame = jetzt;
    animiere();
  }
}
