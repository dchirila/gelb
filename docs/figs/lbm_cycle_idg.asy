// Asymptote source for the GeLB compile-cycle diagram.
//
// Matches the visual language of Figure 1 of the author's PhD
// thesis: a single isometric-looking lattice of green node dots
// with three labelled boxes above (Initializer, Dynamic, Gauge)
// connected to the lattice by curved arrows. The Dynamic phase
// carries a small self-loop arrow to indicate that it iterates
// each time step, while Initializer and Gauge are one-shot /
// periodic.
//
// Render with the sibling script:
//     scripts/render_figs.sh lbm_cycle_idg.asy
// which finishes the .eps → .pdf → .svg pipeline (the embedded
// Asymptote-driven gs invocation is broken on the TeXLive macOS
// build; the wrapper script routes around it).

settings.render     = 0;
settings.prc        = false;
settings.outformat  = "eps";
size(17cm, 0);

unitsize(1cm);

// ---------- palette ----------

pen lattice_line   = gray(0.4) + 0.3pt + dashed;
pen node_fill      = rgb("1db954");       // bright LBM-green, matches the thesis
pen node_edge      = black + 0.5pt;
pen tick_pen       = black + 0.7pt;
pen box_edge       = black + 1.0pt;
pen box_fill       = white;
pen arrow_pen      = black + 1.25pt;
pen label_pen      = fontsize(11pt) + black;
pen title_pen      = fontsize(11pt) + black;

// ---------- lattice in 3-D-ish (2-D page with a skew) ----------
//
// We do the perspective manually in 2-D so that the lattice sits
// cleanly in page space — much easier to anchor the phase boxes
// and curved arrows to specific lattice points than it would be
// inside an orthographic `three` scene.

int  NX      = 5;
int  NY      = 4;
real step    = 1.0;
pair skew    = (0.45, 0.28);   // each +y unit offsets the page by this

pair project(real x, real y) {
    return (x * step + y * skew.x, y * skew.y);
}

// Draw the dashed grid.
for (int i = 0; i <= NX; ++i) {
    draw(project(i, 0) -- project(i, NY), lattice_line);
}
for (int j = 0; j <= NY; ++j) {
    draw(project(0, j) -- project(NX, j), lattice_line);
}

// One node dot per cell centre, with a small tick whose direction
// hints at the D2Q9 velocity set stored at that site.
real node_r = 0.11;
for (int i = 0; i < NX; ++i) {
    for (int j = 0; j < NY; ++j) {
        pair c = project(i + 0.5, j + 0.5);
        filldraw(circle(c, node_r), node_fill, node_edge);
        draw(c -- c + (0.7 * node_r, 0.7 * node_r), tick_pen);
    }
}

// ---------- phase boxes floating above the lattice ----------
//
// Positioned in page space so the three boxes line up on a
// common baseline regardless of the lattice skew. Y is picked so
// they sit just above the back (high-y) edge of the lattice.

real box_y    = skew.y * NY + 1.6;
real box_w    = 1.7;
real box_h    = 0.65;

void draw_phase_box(pair centre, string txt) {
    path p = box(centre + (-box_w/2, -box_h/2),
                 centre + ( box_w/2,  box_h/2));
    filldraw(p, box_fill, box_edge);
    label(txt, centre, label_pen);
}

// Spread the three boxes evenly across the full page-space width
// of the lattice so they don't overlap. The horizontal span of
// the skewed lattice runs from x = 0 to x = NX*step + NY*skew.x.
real lattice_span_x = NX * step + NY * skew.x;
pair box_init  = (0.15 * lattice_span_x, box_y);
pair box_dyn   = (0.50 * lattice_span_x, box_y);
pair box_gauge = (0.85 * lattice_span_x, box_y);

draw_phase_box(box_init,  "Initializer");
draw_phase_box(box_dyn,   "Dynamic");
draw_phase_box(box_gauge, "Gauge");

// ---------- arrows between boxes and lattice ----------
//
// Thick curved 2-D Bezier arcs connect each phase box to the
// region of the lattice it touches. The Dynamic phase gets a
// tiny self-loop arrow above its box to indicate iteration.

// Initializer — writes onto the lattice (once, at t = 0).
pair init_tail = box_init  + (0,        -box_h/2);
pair init_head = project(1.0, 2.5) + (0, 0.18);
path init_arrow = init_tail{dir(-70)} .. {dir(-110)}init_head;
draw(init_arrow, arrow_pen, arrow=Arrow(size=7));

// Dynamic — reads from the lattice, writes back (every step).
pair dyn_down_tail = box_dyn + (-0.5, -box_h/2);
pair dyn_down_head = project(NX/2 - 0.3, 2.0) + (0, 0.18);
path dyn_down = dyn_down_tail{dir(-100)} .. {dir(-120)}dyn_down_head;
draw(dyn_down, arrow_pen, arrow=Arrow(size=7));

pair dyn_up_tail = project(NX/2 + 0.3, 2.0) + (0, 0.18);
pair dyn_up_head = box_dyn + (0.5, -box_h/2);
path dyn_up = dyn_up_tail{dir(80)} .. {dir(60)}dyn_up_head;
draw(dyn_up, arrow_pen, arrow=Arrow(size=7));

// Dynamic self-loop — small curved arrow over the top of the box.
pair loop_start = box_dyn + (-box_w/3, box_h/2);
pair loop_top   = box_dyn + (0,        box_h/2 + 0.7);
pair loop_end   = box_dyn + (box_w/3,  box_h/2);
path dyn_loop = loop_start{dir(90)}
                .. loop_top
                .. {dir(-90)}loop_end;
draw(dyn_loop, arrow_pen, arrow=Arrow(size=7));

// Gauge — reads from the lattice (every --write-every N steps).
pair gauge_tail = project(NX - 1.0, 2.5) + (0, 0.18);
pair gauge_head = box_gauge + (0,           -box_h/2);
path gauge_arrow = gauge_tail{dir(80)} .. {dir(100)}gauge_head;
draw(gauge_arrow, arrow_pen, arrow=Arrow(size=7));
