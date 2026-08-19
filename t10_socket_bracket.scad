// T10 Twist-Lock Socket Bracket — Standoff Box, Front Mount
//
// The bracket is a hollow box. The flat mounting tabs press against the panel
// face and are screwed in from the front. The socket face is on the far end of
// the box, entirely in front of the panel. Socket wires live inside the box
// and exit through the open back. No holes needed in the panel.
//
// Print orientation: front face DOWN on the bed (socket holes facing bed).
// No supports required.
//
// Install:
//  1. Screw mounting tabs to panel front — heads accessible from front.
//  2. Insert T10 sockets into the front-face holes, push in, twist ~90° to lock.

// ── Tune these ───────────────────────────────────────────────────────────────
socket_spacing  = 30;    // center-to-center between the two sockets (mm)
socket_hole_dia = 14.2;  // twist-lock hole diameter (opened up for fit)
notch_width     = 4.2;   // tab-insertion notch width
notch_depth     = 3.0;   // notch radial depth past socket hole edge

standoff        = 28;    // panel face → socket face; must clear full socket body
front_thick     = 2.5;   // front face thickness — socket tabs grip the inside face
wall            = 2.5;   // side/top/bottom wall thickness

body_w          = 56;    // box body width  (covers both sockets with margin)
body_h          = 32;    // box body height

tab_extend      = 24;    // how far each mounting tab sticks out past the box body
tab_h           = 20;    // mounting tab height (narrower than body)
tab_thick       = 3.5;   // mounting tab thickness
mount_hole_dia  = 4.5;   // M4 clearance hole
// ─────────────────────────────────────────────────────────────────────────────

socket_r = socket_hole_dia / 2;
half_sp  = socket_spacing / 2;

module socket_cutout() {
    cylinder(h = front_thick + 0.2, r = socket_r, $fn = 48);
    for (a = [0, 180])
        rotate([0, 0, a])
        translate([socket_r - 0.1, -notch_width / 2, -0.1])
        cube([notch_depth + 0.2, notch_width, front_thick + 0.4]);
}

module square_tab(w, h, thick) {
    translate([-w/2, -h/2, 0])
    cube([w, h, thick]);
}

module bracket() {
    difference() {
        union() {
            // Hollow box body (Z=0: open back against panel; Z=standoff: socket face)
            translate([-body_w/2, -body_h/2, 0])
            cube([body_w, body_h, standoff]);

            // Left mounting tab
            translate([-(body_w/2 + tab_extend/2), 0, 0])
            square_tab(tab_extend, tab_h, tab_thick);

            // Right mounting tab
            translate([body_w/2 + tab_extend/2, 0, 0])
            square_tab(tab_extend, tab_h, tab_thick);
        }

        // Hollow — keeps left/right side walls + front face; removes top/bottom walls
        translate([-(body_w/2 - wall), -body_h/2 - 0.1, -0.1])
        cube([body_w - 2*wall, body_h + 0.2, standoff - front_thick + 0.1]);

        // Socket twist-lock holes in the front face
        for (x = [-half_sp, half_sp])
            translate([x, 0, standoff - front_thick - 0.1])
            socket_cutout();

        // M4 mounting holes centered in each tab
        for (x = [-(body_w/2 + tab_extend/2), body_w/2 + tab_extend/2])
            translate([x, 0, -0.1])
            cylinder(h = tab_thick + 0.2, r = mount_hole_dia / 2, $fn = 32);
    }
}

bracket();
