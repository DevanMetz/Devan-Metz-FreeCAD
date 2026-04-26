// Fridge Cup — parametric OpenSCAD model
// Mirrors the VarSet from Fridge Cup.FCStd.

// --- Parameters ---------------------------------------------------------
Length       = 100;   // longer (back) edge of the trapezoidal footprint, mm
Width        = 30;    // perpendicular depth of the trapezoid (Y), mm
Depth        = 75;    // cup height (Z), mm
Thickness    = 3;     // wall + floor thickness, mm
Fillet       = 5;     // outer corner radius, mm
Angle        = 60;    // base angle of the trapezoidal bottom face, deg
MagDiameter  = 6.2;   // magnet pocket diameter, mm
MagThickness = 2;     // magnet pocket depth, mm
MagInsetX    = 18.66; // magnet inset from the left/right edges, mm
MagInsetZ    = 10;    // magnet inset from the top/bottom edges, mm

$fn = 96;

// --- 2D footprint -------------------------------------------------------
// Trapezoid: long edge along -Y (back face, where the magnets live),
// short parallel edge along +Y. `Angle` is the interior base angle at the
// two back corners. Width/tan(Angle) is the horizontal run of each slanted side.
slant = Width / tan(Angle);

module trapezoid() {
  polygon([
    [-Length/2,         -Width/2],
    [ Length/2,         -Width/2],
    [ Length/2 - slant,  Width/2],
    [-Length/2 + slant,  Width/2],
  ]);
}

// Round the convex corners by offsetting out then back in by Fillet.
module footprint_outer() {
  offset(r =  Fillet) offset(r = -Fillet) trapezoid();
}

// Inner shape = outer shrunk uniformly by wall Thickness.
module footprint_inner() {
  offset(delta = -Thickness) footprint_outer();
}

// --- 3D body ------------------------------------------------------------
module outer_shell() {
  linear_extrude(height = Depth) footprint_outer();
}

module inner_pocket() {
  translate([0, 0, Thickness])
    linear_extrude(height = Depth) footprint_inner();
}

module magnet_pockets() {
  // Bored into the back face (-Y), one near each corner.
  for (x = [-Length/2 + MagInsetX, Length/2 - MagInsetX])
    for (z = [MagInsetZ, Depth - MagInsetZ])
      translate([x, -Width/2 - 0.01, z])
        rotate([-90, 0, 0])
          cylinder(h = MagThickness + 0.02, r = MagDiameter / 2);
}

// --- Build --------------------------------------------------------------
difference() {
  outer_shell();
  inner_pocket();
  magnet_pockets();
}
