// =====================================================================
//  PV display – wall enclosure for 1.8" TFT (ST7735) + Seeed XIAO ESP32-S3
//  All dimensions in mm. Values marked  // MEASURE  are still estimates.
//
//  Printed parts:
//    teil = "front"      -> frame with display window (print front face down)
//    teil = "testblende" -> front plate only, quick test print for window and fit
//    teil = "deckel"     -> back lid with XIAO holder, antenna outline and keyholes (print flat)
//    teil = "halter_test"-> lower part of the lid with the XIAO holder only: quick test print
//    teil = "deckel_test"-> outer edge of the lid only (rim + crush ribs): quick fit test
//    teil = "alles" / "explodiert" -> assembly / exploded view (preview only, do not print)
//  Export: set teil, F6 (render), F7 (save STL)
// =====================================================================

teil = "alles";              // [alles, explodiert, front, deckel, testblende, halter_test, deckel_test]

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
// The XIAO clicks into a holder on the lid, component side towards the display, USB-C pointing down.
// Hook it in with the USB end first (socket under the bridge), then press the far end down until
// it snaps behind the two lips. To remove: push the rear bar outwards and lift the far end.
// Plugging in pushes the board against the rear bar, pulling the cable pulls it against the
// posts beside the socket - the snap lips only keep it from lifting.
xiao_b       = 17.8;         // PCB width
xiao_l       = 21.0;         // PCB length (without the USB socket)
xiao_pcb     = 1.2;          // PCB thickness                                              // MEASURE
xiao_unten_frei = 2.0;       // free space under the PCB (solder joints on the bottom side)  // MEASURE
usb_b        = 9.0;          // USB-C socket width
usb_h        = 3.2;          // USB-C socket height above the PCB                           // MEASURE
usb_ueberstand = 1.8;        // USB-C socket protrudes beyond the PCB edge
raste_ueberstand = 0.5;      // snap lip overlap on the PCB (larger = holds tighter, harder to snap)
steg_d       = 1.6;          // thickness of the flexible rear bar (thinner = softer snap)
halter_spiel = 0.15;         // clearance around the XIAO in the holder
xiao_nach_innen = 4.0;       // XIAO this far away from the USB wall (the plug then reaches into the enclosure)

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
deckel_passung = 0.0;        // clearance between lid rim and enclosure (smaller = tighter; was 0.2, then 0.05)
rand_h       = 5.0;          // height of the lid rim (was 3; max. raum_hinten - 4.8, the vents start above)
klemm_rippe  = 0.3;          // crush ribs: how far they protrude beyond the rim (0 = none)
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
// XIAO in lid coordinates (lid plate z = 0 ... deckel_d)
xiao_x0 = aussen_b/2 - xiao_b/2;                     // centered, USB pointing down
xiao_y0 = wand_u + usb_ueberstand + xiao_nach_innen; // USB end of the PCB
usb_mund = xiao_y0 - usb_ueberstand;                 // socket mouth (the plug reaches in up to here)
xiao_y1 = xiao_y0 + xiao_l;                          // far end of the PCB
xiao_z0 = deckel_d + xiao_unten_frei;                // PCB bottom side
xiao_z1 = xiao_z0 + xiao_pcb;                        // PCB top side
usb_oben = xiao_z1 + usb_h;                          // top of the USB socket
usb_mitte = xiao_unten_frei + xiao_pcb + usb_h/2;    // USB socket center (front part coordinates)
ant_x = aussen_b/2 - ant_b/2;                        // antenna centered at the top of the lid
ant_y = aussen_h - wand - 0.2 - 1.2 - 0.3 - ant_h;   // just below the lid rim (partly under the XIAO)

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

// XIAO holder on the lid (lid coordinates)
module xiao_halter() {
    s  = halter_spiel;
    ox = xiao_x0 - s - 1.2;                   // outer x of the side guides
    ix = xiao_x0 + xiao_b + s;                // inner x of the right side guide
    // --- USB end: posts beside the plug (stop when pulling the cable) + bridge over the socket.
    // The posts leave a channel as wide as the wall notch, so the plug can reach in to the socket.
    py0 = wand_u + deckel_passung;            // starts at the inner wall
    py1 = xiao_y0 - s;                        // ends in front of the PCB edge
    buegel_z = usb_oben + s;
    kanal = max(stecker_b, usb_b + 0.6) / 2 + 0.2;   // half width of the channel for the plug
    for (seite = [[ox, aussen_b/2 - kanal - ox],                       // left
                  [aussen_b/2 + kanal, ix + 1.2 - (aussen_b/2 + kanal)]]) {  // right
        translate([seite[0], py0, deckel_d - 0.01]) cube([seite[1], py1 - py0, buegel_z + 1.2 - deckel_d + 0.01]);
    }
    // bridge over the socket, only over the part behind the socket mouth (the plug stays in front of it)
    translate([ox, max(py0, usb_mund + 0.1), buegel_z]) cube([ix + 1.2 - ox, py1 - max(py0, usb_mund + 0.1), 1.2]);
    // side guides at the USB end (corners have no pads)
    for (x = [ox, ix]) translate([x, py1 - 0.01, deckel_d - 0.01]) cube([1.2, 1.5 + s, xiao_z1 + 0.5 - deckel_d]);

    // --- pedestal under the middle of the PCB (stays clear of the solder joints and of the antenna)
    sockel_y1 = min(xiao_y1 - 1, ant_y - 1.0);
    translate([xiao_x0 + 3.5, xiao_y0 + 0.5, deckel_d - 0.01]) cube([xiao_b - 7, sockel_y1 - xiao_y0 - 0.5, xiao_unten_frei + 0.01]);

    // --- far end: flexible bar spanning over the antenna (stop when plugging in, carries the snap lips)
    by0 = xiao_y1 + s;
    by1 = by0 + steg_d;
    unten = deckel_d + 0.8;                   // bar bottom: above the antenna
    oben  = xiao_z1 + 1.2;
    fuss_x0 = wand + deckel_passung + 1.2 + 0.3;         // feet outside the antenna outline
    fuss_x1 = ant_x - 0.8;
    for (fx = [[fuss_x0, fuss_x1], [aussen_b - fuss_x1, aussen_b - fuss_x0]])
        translate([fx[0], by0, deckel_d - 0.01]) cube([fx[1] - fx[0], steg_d, oben - deckel_d + 0.01]);
    translate([fuss_x0, by0, unten]) cube([aussen_b - 2*fuss_x0, steg_d, oben - unten]);
    // ledge under the far edge of the PCB
    translate([xiao_x0 + 0.5, xiao_y1 - 0.8, unten]) cube([xiao_b - 1, 0.8 + s + 0.01, xiao_z0 - unten]);
    // side guides at the far end
    for (x = [ox, ix]) translate([x, xiao_y1 - 1.4, unten]) cube([1.2, 1.4 + s + 0.01, xiao_z1 + 0.5 - unten]);
    // snap lips at the two far corners (between the pads and the U.FL / camera connector),
    // chamfered on top so the PCB pushes the bar back when pressed in
    for (lx = [xiao_x0 + 0.3, xiao_x0 + xiao_b - 2.0])
        hull() {
            translate([lx, by0 - raste_ueberstand, xiao_z1 + s]) cube([1.7, raste_ueberstand + 0.01, 0.3]);
            translate([lx, by0 - 0.01, oben - 0.2]) cube([1.7, 0.02, 0.2]);
        }
}

module rueckdeckel() {
    rand = 1.2;                           // wall thickness of the lid rim
    passung = deckel_passung;             // clearance between rim and enclosure
    difference() {
        union() {
            rund_rechteck(aussen_b, aussen_h, deckel_d, ecken_r);

            // crush ribs on the outside of the rim: they deform slightly when the lid is pushed in,
            // so the fit no longer depends on the exact print tolerance
            rx0 = wand + passung;  rx1 = wand + passung + innen_b - 2*passung;
            ry0 = wand_u + passung; ry1 = wand_u + passung + innen_h - 2*passung;
            versatz_r = 0.6 - klemm_rippe;     // rib center inside the rim face (rib d = 1.2)
            for (p = [[aussen_b*0.25, ry0 + versatz_r], [aussen_b*0.75, ry0 + versatz_r],
                      [aussen_b*0.25, ry1 - versatz_r], [aussen_b*0.75, ry1 - versatz_r],
                      [rx0 + versatz_r, (ry0 + ry1)/2], [rx1 - versatz_r, (ry0 + ry1)/2]])
                if (klemm_rippe > 0) translate([p[0], p[1], deckel_d]) {
                    cylinder(d=1.2, h=rand_h - 1);
                    translate([0, 0, rand_h - 1]) cylinder(d1=1.2, d2=0.4, h=1);   // lead-in
                }

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

            xiao_halter();

            // rest for the USB plug from the wall notch to the socket (the notch then fits the plug all around,
            // so sideways pull on the cable goes into the enclosure, not into the socket)
            auflage_h = usb_mitte - stecker_h/2 - 0.1;
            if (auflage_h > 0.3)
                translate([aussen_b/2 - stecker_b/2 + 0.2, 0.3, deckel_d - 0.01])
                    cube([stecker_b - 0.4, usb_mund - 0.3 - 0.3, auflage_h + 0.01]);
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
    color("Purple") translate([xiao_x0, xiao_y0, xiao_z0]) cube([xiao_b, xiao_l, xiao_pcb]);       // XIAO on the lid
    color("Silver") translate([aussen_b/2 - usb_b/2, xiao_y0 - usb_ueberstand, xiao_z1])
        cube([usb_b, 7.3, usb_h]);                                                       // USB-C socket
    color("Goldenrod") translate([ant_x, ant_y, deckel_d]) cube([ant_b, ant_h, 0.2]);    // antenna
}

if (usb_oben + halter_spiel + 1.2 > deckel_d + raum_hinten - 0.5)
    echo("ACHTUNG: XIAO-Halter stößt an die Displayplatine - raum_hinten vergrößern!");
echo(str("XIAO-Platine: Unterseite ", xiao_z0 - deckel_d, " mm über dem Deckel, USB-Mitte ", usb_mitte, " mm"));

if (teil == "alles")       zusammenbau(0);
if (teil == "halter_test") // lower part of the lid with the holder: test fit and snap before printing the full lid
    intersection() {
        rueckdeckel();
        translate([-1, -1, -1]) cube([aussen_b + 2, xiao_y1 + halter_spiel + steg_d + 1.5 + 1, 30]);
    }
if (teil == "explodiert")  zusammenbau(25);
if (teil == "front")       translate([0, aussen_h, rahmen_t]) rotate([180, 0, 0]) frontteil();  // front face down
if (teil == "deckel")      rueckdeckel();
if (rand_h > raum_hinten - 4.8)
    echo("ACHTUNG: Deckelrand verdeckt die Lüftungsschlitze - rand_h verkleinern!");
if (teil == "deckel_test") // only the outer edge of the lid with rim and crush ribs: quick fit test
    intersection() {
        rueckdeckel();
        difference() {
            translate([-1, -1, -1]) cube([aussen_b + 2, aussen_h + 2, 30]);
            translate([wand + 3.5, wand_u + 3.5, -2]) cube([aussen_b - 2*wand - 7, aussen_h - wand - wand_u - 7, 40]);
        }
    }
if (teil == "testblende")  // front plate + 3 mm rim only: quick print to test-fit the display
    translate([0, aussen_h, rahmen_t]) rotate([180, 0, 0])
        intersection() {
            frontteil();
            translate([-1, -1, rahmen_t - front - 3]) cube([aussen_b + 2, aussen_h + 2, front + 3 + 1]);
        }
