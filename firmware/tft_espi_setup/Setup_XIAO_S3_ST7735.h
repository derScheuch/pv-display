// TFT_eSPI setup: Seeed XIAO ESP32-S3 + 1.77"/1.8" ST7735S TFT (128 x 160)
//
// Copy this file to   <Arduino>/libraries/TFT_eSPI/User_Setups/
// and select it in    <Arduino>/libraries/TFT_eSPI/User_Setup_Select.h :
//
//   //#include <User_Setup.h>
//   #include <User_Setups/Setup_XIAO_S3_ST7735.h>
//
// (A tft_setup.h in the sketch folder does NOT work with the Arduino IDE:
//  the library is compiled separately and never sees it.)

#define ST7735_DRIVER
#define TFT_WIDTH  128
#define TFT_HEIGHT 160
#define ST7735_BLACKTAB            // no pixel offset on this module; try REDTAB/GREENTAB variants if
                                   // you see garbage along the top/left edge
#define TFT_RGB_ORDER TFT_BGR      // red and blue were swapped on this module; remove if colors look wrong

// Pins (GPIO numbers, not the D-labels printed on the board)
#define TFT_SCLK  7    // D8
#define TFT_MOSI  9    // D10
#define TFT_MISO -1    // not used
#define TFT_CS    2    // D1
#define TFT_DC    3    // D2  (display pin "RS" / "A0")
#define TFT_RST   4    // D3
#define TFT_BL    1    // D0  (only if LEDA is wired to D0; with LEDA on 3V3 this is unused)
#define TFT_BACKLIGHT_ON HIGH

#define LOAD_GLCD      // font 1
#define LOAD_FONT2     // font 2
#define LOAD_FONT4     // font 4

#define SPI_FREQUENCY 27000000     // lower to 10000000 if you see glitches with long wires

#define USE_HSPI_PORT  // avoids a crash on the ESP32-S3 with ESP32 Arduino core 3.x
