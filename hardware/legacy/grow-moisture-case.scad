// Grow Moisture Monitor case
// ESP32 DevKit (30-pin, ~51.5 x 28.3 mm) + 0.96" SSD1306 OLED (~27.3 x 27.8 mm)
// + 4 sensor cables in one end, USB in the other.
//
// HOW TO USE
//   1. Measure your boards with calipers and fix the values marked MEASURE.
//   2. Set part = "box" -> F6 render -> File > Export > STL. Repeat with part = "lid".
//   3. Print both at 0.2 mm layers, 20% infill, no supports.
//      Box: open side up. Lid: top face down (OLED posts pointing up).
//
// LAYOUT (looking down, lid off)
//   x=0 end: USB opening        |  ESP32 board  |  OLED area  |  x=L end: sensor cable slot
//   The ESP32 sits on ledges at both short ends, components up, header pins down,
//   with room underneath for Dupont jumpers. Stick it down with foam tape on the ledges.
//   The OLED screws to 4 posts under the lid, glass facing the window.

part = "both";        // "box", "lid", or "both" (preview only)

// ---------- general ----------
wall   = 2.0;
floor_t = 2.0;
lid_t  = 2.0;
fit    = 0.3;          // clearance for lid rim (raise to 0.4 if too tight)

// interior size
L = 92;                // length (x)
W = 42;                // width  (y)
H = 30;                // height (z) floor-top to lid-underside

// ---------- ESP32 (MEASURE) ----------
esp_len   = 51.5;      // board length
esp_wid   = 28.3;      // board width
esp_x0    = 1.0;       // gap from USB-end wall
ledge_top = 20.0;      // height of board underside (room for pins + Dupont housings below)
ledge_d   = 3.0;       // how far the ledges reach under each board end

// USB opening (centered on the board's USB jack)
usb_w  = 13;           // fits most micro-USB / USB-C plug overmolds
usb_h  = 9;
usb_zc = ledge_top + 1.6 + 1.5;   // jack center: board top + half jack height

// ---------- OLED (MEASURE) ----------
oled_pcb_x = 27.3;
oled_pcb_y = 27.8;
oled_hole_dx = 23.3;   // center-to-center of mounting holes, x
oled_hole_dy = 23.5;   // center-to-center of mounting holes, y
oled_hole_d  = 1.7;    // pilot for M2 self-tapping screws
oled_standoff = 2.2;   // glass thickness: gap between lid and OLED PCB
win_w = 25.0;          // viewing window
win_h = 14.0;
win_off_y = 1.5;       // shift window toward the glass side if needed (+/-)
oled_cx = 58 + oled_pcb_x/2;   // OLED center position inside the box
oled_cy = W/2;

// ---------- sensor cable slot (x = L end) ----------
slot_w = 28;
slot_h = 10;
slot_z = 4;            // bottom of slot above floor

// ---------- lid screws ----------
post = 6;              // corner post size
screw_pilot = 2.5;     // M3 self-tap pilot in box posts
screw_clear = 3.4;     // M3 clearance in lid

// ---------- mounting ears for zip ties ----------
ear_len = 12;
ear_t   = 3;
tie_w = 5; tie_l = 3;

$fn = 40;

OL = L + 2*wall;
OW = W + 2*wall;
OH = H + floor_t;

module box() {
  difference() {
    union() {
      // shell
      difference() {
        cube([OL, OW, OH]);
        translate([wall, wall, floor_t]) cube([L, W, H + 1]);
      }
      // corner posts
      for (px = [wall, wall + L - post], py = [wall, wall + W - post])
        translate([px, py, floor_t]) cube([post, post, H]);
      // ESP32 ledges
      esp_y0 = (W - esp_wid)/2;
      // USB end: two pads under the corners only, so the plug can pass between
      for (py = [0, W - 12])
        translate([wall, wall + py, floor_t]) cube([esp_x0 + ledge_d, 12, ledge_top]);
      // antenna end: full width
      translate([wall + esp_x0 + esp_len - ledge_d, wall + post, floor_t])
        cube([ledge_d + 1, W - 2*post, ledge_top]);
      // zip-tie ears
      for (ex = [-ear_len, OL])
        translate([ex, OW/2 - 9, 0]) cube([ear_len, 18, ear_t]);
    }
    // USB opening
    translate([-1, wall + W/2 - usb_w/2, floor_t + usb_zc - usb_h/2])
      cube([wall + 2, usb_w, usb_h]);
    // sensor cable slot
    translate([OL - wall - 1, wall + W/2 - slot_w/2, floor_t + slot_z])
      cube([wall + 2, slot_w, slot_h]);
    // lid screw pilots
    for (px = [wall + post/2, wall + L - post/2], py = [wall + post/2, wall + W - post/2])
      translate([px, py, floor_t + H - 12]) cylinder(d = screw_pilot, h = 13);
    // vent slots on the long wall by the ESP32
    for (i = [0:4])
      translate([wall + 8 + i*8, -1, floor_t + H - 10]) cube([3, wall + 2, 7]);
    // zip-tie slots in the ears
    for (ex = [-ear_len/2, OL + ear_len/2])
      translate([ex - tie_l/2, OW/2 - tie_w/2, -1]) cube([tie_l, tie_w, ear_t + 2]);
  }
}

module lid() {
  rim_h = 1.5;
  difference() {
    union() {
      cube([OL, OW, lid_t]);
      // locating rim that drops inside the walls
      translate([wall + fit, wall + fit, lid_t])
        difference() {
          cube([L - 2*fit, W - 2*fit, rim_h]);
          translate([1.2, 1.2, -1]) cube([L - 2*fit - 2.4, W - 2*fit - 2.4, rim_h + 2]);
          // notch the rim around the corner posts
          for (cx = [-1, L - 2*fit - post - fit], cy = [-1, W - 2*fit - post - fit])
            translate([cx, cy, -1]) cube([post + 2*fit + 1, post + 2*fit + 1, rim_h + 2]);
        }
      // OLED standoffs
      for (sx = [-1, 1], sy = [-1, 1])
        translate([wall + oled_cx + sx*oled_hole_dx/2, wall + oled_cy + sy*oled_hole_dy/2, lid_t])
          cylinder(d = 4.5, h = oled_standoff);
    }
    // OLED window, chamfered so the edges don't shadow the screen
    translate([wall + oled_cx, wall + oled_cy + win_off_y, -0.01])
      hull() {
        translate([0, 0, lid_t]) cube([win_w, win_h, 0.02], center = true);
        cube([win_w + 2*lid_t, win_h + 2*lid_t, 0.02], center = true);
      }
    // OLED screw pilots
    for (sx = [-1, 1], sy = [-1, 1])
      translate([wall + oled_cx + sx*oled_hole_dx/2, wall + oled_cy + sy*oled_hole_dy/2, -1])
        cylinder(d = oled_hole_d, h = lid_t + oled_standoff + 2);
    // corner screw holes (countersunk on top face)
    for (px = [wall + post/2, wall + L - post/2], py = [wall + post/2, wall + W - post/2])
      translate([px, py, 0]) {
        translate([0, 0, -1]) cylinder(d = screw_clear, h = lid_t + 2);
        translate([0, 0, -0.01]) cylinder(d1 = 6.5, d2 = screw_clear, h = 1.6);
      }
  }
}

if (part == "box") box();
else if (part == "lid") lid();
else {
  box();
  // lid shown flipped into place above the box
  translate([0, 0, OH + 25]) mirror([0, 0, 1]) lid();
}
