// Display wiring test: draws continuously so that, while bending the wires,
// you immediately see which line has a loose contact. No Wi-Fi, display only.
//
// The display is NOT re-initialized automatically (that caused a short white
// flash by itself). After a fault: briefly press the BOOT button (B) on the XIAO;
// the display is re-initialized and the "Neustarts" (restarts) counter goes up.
//
// What you see -> which line:
//  * screen suddenly turns WHITE and stays white until you press B -> RES (pin 5) or VCC (pin 2)
//  * backlight flickers or goes off (screen dark)             -> LEDA (pin 8) or GND (pin 1)
//  * single wrong pixels, stripes or wrong colors that
//    disappear again on the next pass                        -> SCK (pin 3) or SDA (pin 4)
//  * graphics end up in the wrong place / line patterns       -> RS (pin 6)
//  * screen FREEZES (moving bar and counter stop),
//    but does not turn white (also SCK/SDA if fully lost)     -> CS (pin 7)
// The serial monitor shows that the XIAO itself keeps running.

#include <TFT_eSPI.h>
#include <SPI.h>

TFT_eSPI tft = TFT_eSPI();
const int   DREHUNG = 3;      // display orientation: 1 = landscape, 3 = landscape rotated by 180°

unsigned long zaehler = 0, neustarts = 0;
unsigned long letzteFarbe = 0;
const int TASTE = 0;               // BOOT button on the XIAO ESP32-S3
int balkenX = 0, farbIndex = 0;
const uint16_t farben[] = {TFT_RED, TFT_GREEN, TFT_BLUE, TFT_YELLOW, TFT_CYAN, TFT_MAGENTA};

void grundbild() {
  tft.fillScreen(TFT_BLACK);
  // color bars at the top: make color errors (SDA/SCK) visible
  for (int i = 0; i < 6; ++i) tft.fillRect(i * 27, 0, 27, 14, farben[i]);
  // frame: makes offsets (RS) visible
  tft.drawRect(0, 16, 160, 112, TFT_WHITE);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
  tft.drawString("Zaehler", 6, 22, 2);
  tft.drawString("Neustarts", 6, 92, 2);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("Wackeltest gestartet");
  pinMode(TASTE, INPUT_PULLUP);
  tft.init();
  tft.setRotation(DREHUNG);
  grundbild();
}

void loop() {
  unsigned long jetzt = millis();

  // BOOT button pressed: re-initialize the display (after a loose contact)
  if (digitalRead(TASTE) == LOW) {
    tft.init();
    tft.setRotation(DREHUNG);
    grundbild();
    ++neustarts;
    Serial.println("Display per Taste neu gestartet");
    while (digitalRead(TASTE) == LOW) delay(10);   // wait until released
  }

  // big counter, runs continuously (if it stops -> screen frozen)
  ++zaehler;
  tft.setTextDatum(TR_DATUM);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawString("   " + String(zaehler), 152, 40, 4);
  tft.setTextColor(TFT_GREEN, TFT_BLACK);
  tft.drawString("   " + String(neustarts), 152, 92, 2);

  // moving bar across the screen
  tft.fillRect(balkenX, 72, 12, 12, TFT_BLACK);
  balkenX = (balkenX + 4) % 148;
  tft.fillRect(balkenX, 72, 12, 12, farben[farbIndex]);

  // bar color changes every second
  if (jetzt - letzteFarbe > 1000) {
    letzteFarbe = jetzt;
    farbIndex = (farbIndex + 1) % 6;
    Serial.printf("laeuft: Zaehler %lu, Neustarts %lu\n", zaehler, neustarts);
  }

  delay(20);
}
