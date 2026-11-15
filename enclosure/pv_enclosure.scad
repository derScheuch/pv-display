// =====================================================================
//  PV display – wall enclosure for 1.8" TFT (ST7735) + Seeed XIAO ESP32-S3
//  All dimensions in mm. Values marked  // MEASURE  are still estimates.
//
//  Printed parts:
//    teil = "front"      -> frame with display window (print front face down)
//    teil = "testblende" -> front plate only, quick test print for window and fit
//    teil = "deckel"     -> back lid with keyholes, antenna outline and button holes (print flat)
//    teil = "alles" / "explodiert" -> assembly / exploded view (preview only, do not print)
//  Export: set teil, F6 (render), F7 (save STL)
// =====================================================================

teil = "alles";              // [alles, explodiert, front, deckel, testblende]

/* [Display module] */
pcb_b        = 56.0;         // PCB width
pcb_h        = 33.5;         // PCB height (+0.5 after test print)
pcb_d        = 1.5;          // PCB thickness
glas_ab_links  = 5.5;        // free PCB area left of the glass (header pins are here)
glas_ab_rechts = 6.5;        // free PCB area right of the glass
glas_b       = pcb_b - glas_ab_links - glas_ab_rechts;   // = 44 mm
glas_h       = 33.0;         // glass height (same as PCB)
glas_d       = 3.0;          // glass thickness (total 4.5 minus PCB 1.5)
aktiv_b      = 37.0;         // active area width (after test print: 5 mm narrower on the left, right unchanged)
aktiv_h      = 29.0;         // active area height
aktiv_ab_links = 11.5;       // active area: distance from the left PCB edge (after test print)
aktiv_ab_oben  = 3.0;        // active area: distance from the top PCB edge

/* [XIAO ESP32-S3] */
// The XIAO is stuck to the back of the display, insulated with Kapton or foam tape,
// component side facing the lid, USB-C pointing down.
xiao_b       = 17.8;         // width
xiao_l       = 21.0;         // length
xiao_pcb     = 1.2;          // PCB thickness
xiao_bauteile = 3.4;         // component height on the top side (USB-C socket)           // MEASURE
taster_abstand = 5.5;        // BOOT/RESET: lateral distance from the center             // MEASURE
taster_ab_usb  = 3.0;        // BOOT/RESET: distance from the USB end                     // MEASURE

/* [Antenna] */
ant_b        = 38.0;         // adhesive antenna width
ant_h        = 18.0;         // adhesive antenna height

/* [USB cable] */
stecker_b    = 12.0;         // opening for the plug: width (with some clearance)
stecker_h    = 8.0;          // opening for the plug: height (with some clearance)

/* [Enclosure] */
wand         = 2.0;          // wall thickness
front        = 1.6;          // front bezel thickness
deckel_d     = 2.0;          // back lid thickness
spiel        = 0.3;          // clearance around the PCBs (print tolerance)
deckel_passung = 0.05;       // clearance between lid rim and enclosure (smaller = tighter; was 0.2)
raum_hinten  = 10.0;         // space behind the display (XIAO, antenna, screw heads)
ecken_r      = 3.0;          // outer corner radius
fenster_rand = 0.5;          // window slightly larger than the active area
rahmen_ausgleich = "fenster"; // [fenster, gehaeuse, aus]  equal frame top/bottom: shorten window at the bottom, or extend enclosure at the bottom, or off
schraube_d   = 3.5;          // wall screw shank diameter
kopf_d       = 7.0;          // wall screw head diameter

$fn = 48;

// ---------------------------------------------------------------- derived dimensions
innen_b = pcb_b + 2*spiel;
innen_h = pcb_h + 2*spiel;
aussen_b = innen_b + 2*wand;
// The active area is not centered on the PCB (more margin at the top than at the bottom).
// "gehaeuse": the bottom wall gets the difference added (enclosure gets taller)
// "fenster":  the window is shortened at the bottom by the difference (enclosure unchanged)
versatz = max(0, aktiv_ab_oben - (pcb_h - aktiv_ab_oben - aktiv_h));
extra_unten = rahmen_ausgleich == "gehaeuse" ? versatz : 0;
wand_u = wand + extra_unten;                         // bottom wall thickness
aussen_h = innen_h + wand + wand_u;
rahmen_t = raum_hinten + pcb_d + glas_d + front;     // depth of the front part
pcb_x = wand + spiel;                                // PCB bottom-left corner (front view)
pcb_y = wand_u + spiel;
z_pcb  = raum_hinten;                                // PCB back side (in front part coordinates)
z_glas = raum_hinten + pcb_d;                        // glass back side
z_blende = rahmen_t - front;                         // inner face of the front bezel
xiao_x = aussen_b/2 - xiao_b/2;                      // XIAO centered, USB pointing down
xiao_y = wand_u + 0.5;
xiao_z = raum_hinten - 0.1 - xiao_pcb;               // lower face of the XIAO PCB (front part coordinates, 0.1 tape)
usb_mitte = xiao_z - xiao_bauteile/2;                // height of the USB socket center (front part coordinates)
ant_x = aussen_b/2 - ant_b/2;                        // antenna centered at the top of the lid
ant_y = aussen_h - wand - 0.2 - 1.2 - 0.3 - ant_h;      // just below the lid rim

echo(str("Gehäuse außen: ", aussen_b, " x ", aussen_h, " x ", rahmen_t + deckel_d, " mm"));
// window position (inner face of the bezel), possibly shortened at the bottom
fenster_x = pcb_x + aktiv_ab_links - fenster_rand;
fenster_b = aktiv_b + 2*fenster_rand;
fenster_y0 = pcb_y + (pcb_h - aktiv_ab_oben - aktiv_h) - fenster_rand;
fenster_h0 = aktiv_h + 2*fenster_rand;
kuerzung = rahmen_ausgleich == "fenster" ? versatz : 0;
fenster_y = fenster_y0 + kuerzung;
fenster_h = fenster_h0 - kuerzung;
echo(str("Rahmen vorne: oben ", aussen_h - (fenster_y + fenster_h + front),
         " mm, unten ", fenster_y - front, " mm, Fenster ", fenster_b, " x ", fenster_h, " mm"));
if (aktiv_ab_links < glas_ab_links || aktiv_ab_links + aktiv_b > pcb_b - glas_ab_rechts)
    echo("ACHTUNG: Bild liegt nicht vollständig auf dem Glas - Maße prüfen!");

// ---------------------------------------------------------------- helper shapes
module rund_rechteck(b, h, t, r) {          // box with rounded vertical edges
    hull() for (x = [r, b-r], y = [r, h-r]) translate([x, y, 0]) cylinder(r=r, h=t);
}

// ---------------------------------------------------------------- front part
module frontteil() {
    difference() {
        rund_rechteck(aussen_b, aussen_h, rahmen_t, ecken_r);

        // cavity (open at the back)
        translate([wand, wand_u, -0.01]) cube([innen_b, innen_h, z_blende + 0.01]);

        // display window, chamfered towards the front (45°) to avoid shading
        fx = fenster_x;  fy = fenster_y;  fb = fenster_b;  fh = fenster_h;
        hull() {
            translate([fx, fy, z_blende - 0.01]) cube([fb, fh, 0.01]);
            translate([fx - front, fy - front, rahmen_t]) cube([fb + 2*front, fh + 2*front, 0.01]);
        }

        // notch for the USB plug at the bottom (open towards the back)
        translate([aussen_b/2 - stecker_b/2, -0.01, -0.01])
            cube([stecker_b, wand_u + 0.02, usb_mitte + stecker_h/2]);

        // ventilation slots at top and bottom
        for (w = [[-0.01, wand_u], [aussen_h - wand - 0.01, wand]], i = [-1.5, 1.5])
            translate([aussen_b/2 + i*12 - 4, w[0], raum_hinten - 4.5]) cube([8, w[1] + 0.02, 1.6]);
    }

    // PCB supports left and right of the glass
    // (one rib at top and bottom each, the middle stays free for the header solder joints)
    for (seite = [[pcb_x, glas_ab_links], [pcb_x + pcb_b - glas_ab_rechts + 0.5, glas_ab_rechts]])
        if (seite[1] > 1.5)
            for (y = [pcb_y, pcb_y + pcb_h - 4])
                translate([seite[0] + 0.5, y, z_glas]) cube([seite[1] - 1.5, 4, glas_d]);
}

// ---------------------------------------------------------------- back lid
module schluesselloch() {
    cylinder(d=kopf_d, h=10, center=true);
    hull() for (dy = [0, 5]) translate([0, dy, 0]) cylinder(d=schraube_d, h=10, center=true);
}

module rueckdeckel() {
    rand = 1.2;                           // wall thickness of the lid rim
    passung = deckel_passung;             // clearance between rim and enclosure
    rand_h = 3.0;                         // taller rim = more friction area
    difference() {
        union() {
            rund_rechteck(aussen_b, aussen_h, deckel_d, ecken_r);

            // lid rim (holds the lid by friction)
            translate([0, 0, deckel_d]) difference() {
                translate([wand + passung, wand_u + passung, 0])
                    cube([innen_b - 2*passung, innen_h - 2*passung, rand_h]);
                translate([wand + passung + rand, wand_u + passung + rand, -0.01])
                    cube([innen_b - 2*passung - 2*rand, innen_h - 2*passung - 2*rand, rand_h + 0.02]);
                // cut-out for the USB plug
                translate([aussen_b/2 - stecker_b/2 - 1, 0, -0.01]) cube([stecker_b + 2, wand_u + rand + 1, rand_h + 0.02]);
            }

            // posts pressing the display against the front from behind
            for (x = [pcb_x + 1, pcb_x + pcb_b - 4], y = [pcb_y + 1, pcb_y + pcb_h - 4])
                translate([x, y, deckel_d]) cube([3, 3, raum_hinten - 0.2]);
        }

        // engraved outline: stick the antenna here
        translate([0, 0, deckel_d - 0.4]) difference() {
            translate([ant_x - 0.6, ant_y - 0.6, 0]) cube([ant_b + 1.2, ant_h + 1.2, 1]);
            translate([ant_x, ant_y, -0.01]) cube([ant_b, ant_h, 1.1]);
        }

        // keyholes for wall mounting, bottom left and right
        // (place the enclosure over the screw heads and slide it down)
        for (x = [12, aussen_b - 12])
            translate([x, 7 + extra_unten, 0]) schluesselloch();

        // holes for the BOOT and RESET buttons (press with a paper clip)
        for (s = [-1, 1])
            translate([aussen_b/2 + s*taster_abstand, xiao_y + taster_ab_usb, 0])
                cylinder(d=2.5, h=10, center=true);
    }
}

// ---------------------------------------------------------------- output
module zusammenbau(abstand = 0) {
    color("SlateGray") translate([0, 0, deckel_d + abstand]) frontteil();
    color("DimGray") rueckdeckel();
    // placeholders for display, XIAO and antenna (preview only, not printed)
    color("DarkGreen") translate([pcb_x, pcb_y, deckel_d + abstand + z_pcb]) cube([pcb_b, pcb_h, pcb_d]);
    color("Black") translate([pcb_x + glas_ab_links, pcb_y, deckel_d + abstand + z_glas]) cube([glas_b, glas_h, glas_d - 0.05]);
    color("RoyalBlue") translate([pcb_x + aktiv_ab_links, pcb_y + pcb_h - aktiv_ab_oben - aktiv_h,
                                  deckel_d + abstand + z_glas + glas_d - 0.05]) cube([aktiv_b, aktiv_h, 0.05]);
    color("Purple") translate([xiao_x, xiao_y, deckel_d + abstand + xiao_z]) cube([xiao_b, xiao_l, xiao_pcb]);
    color("Silver") translate([aussen_b/2 - 4.5, xiao_y - 1, deckel_d + abstand + xiao_z - xiao_bauteile])
        cube([9, 7.5, xiao_bauteile]);                                                   // USB-C socket
    color("Goldenrod") translate([ant_x, ant_y, deckel_d]) cube([ant_b, ant_h, 0.2]);    // antenna
}

if (teil == "alles")       zusammenbau(0);
if (teil == "explodiert")  zusammenbau(25);
if (teil == "front")       translate([0, aussen_h, rahmen_t]) rotate([180, 0, 0]) frontteil();  // front face down
if (teil == "deckel")      rueckdeckel();
if (teil == "testblende")  // front plate + 3 mm rim only: quick print to test-fit the display
    translate([0, aussen_h, rahmen_t]) rotate([180, 0, 0])
        intersection() {
            frontteil();
            translate([-1, -1, rahmen_t - front - 3]) cube([aussen_b + 2, aussen_h + 2, front + 3 + 1]);
        }
