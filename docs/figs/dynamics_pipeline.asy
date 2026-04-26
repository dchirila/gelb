// Asymptote source for the "Dynamics pipeline" figure — a modern
// take on Figure 7 of the author's PhD thesis, updated to GeLB's
// current pull-scheme semantics and syntax.
//
// Layout (left → right):
//
//   ┌──────────┐     ┌───────────────────────────┐     ┌──────────┐
//   │  INPUT   │     │  PIPELINE (vertical)      │     │  OUTPUT  │
//   │  REGION  │  →  │  1. upstream_dfs           │     │  REGION  │
//   │          │     │  2. Macro                   │     │          │
//   │  3×3 of  │     │  3. Feq                     │  →  │  1 cell, │
//   │  D2Q9    │     │  4. BGK collision           │     │  9 DFs   │
//   │  cells,  │     │  5. f.out[x,y|:] = fOut     │     │          │
//   │  centre  │     │                             │     │  written │
//   │  high-   │     │  with type-annotated        │     │          │
//   │  lighted │     │  arrows between stages      │     │          │
//   └──────────┘     └───────────────────────────┘     └──────────┘
//
// Each macro cell in the input / output regions shows the D2Q9
// velocity set as 9 green dots in a 3 × 3 mini-grid.
//
// Render with scripts/render_figs.sh dynamics_pipeline.asy.

settings.render     = 0;
settings.prc        = false;
settings.outformat  = "eps";
unitsize(1cm);

// ============================================================
//  Palette
// ============================================================

pen bg_input         = rgb("fff4e0");      // very light amber
pen bg_pipeline      = rgb("f7f8fb");      // very light neutral
pen bg_output        = rgb("e8f4ec");      // very light green
pen region_edge      = gray(0.55) + 0.4pt;

pen cell_line        = gray(0.55) + 0.3pt;
pen cell_highlight   = rgb("d97706") + 1.0pt;   // amber
pen cell_highlight_f = rgb("fde3b6");

pen df_fill          = rgb("1db954");           // LBM-green dot
pen df_edge          = black + 0.3pt;
pen df_written_fill  = rgb("d97706");           // amber for post-write
pen df_written_edge  = rgb("6b3d02") + 0.4pt;

pen kernel_fill      = white;
pen kernel_edge      = rgb("2f6bd6") + 0.8pt;   // blue
pen kernel_title_pen = fontsize(9.5pt) + rgb("111111");
pen kernel_code_pen  = fontsize(8.5pt) + rgb("444444");

pen arrow_pen        = rgb("2a2a2a") + 1.1pt;
pen arrow_big_pen    = rgb("2a2a2a") + 1.5pt;
pen type_pen         = fontsize(8pt) + rgb("2a2a2a");
pen title_pen        = fontsize(11pt) + rgb("111111");
pen sub_pen          = fontsize(8.5pt) + rgb("555555");

// ============================================================
//  Helpers
// ============================================================

// Draw a single macro cell (one lattice site) at bottom-left
// corner `tl`, side `s`. Each cell carries its D2Q9 set as 9
// dots in a 3 × 3 mini-grid.
//   highlighted  – true → amber fill, thicker edge (centre cell
//                  of the input region, or the output cell).
//   written      – true → DF dots are amber (post-collision);
//                  else green (pre-collision state).
void draw_macro_cell(pair tl, real s,
                     bool highlighted = false,
                     bool written     = false)
{
    pair br = tl + (s, s);
    path cell = tl -- (br.x, tl.y) -- br -- (tl.x, br.y) -- cycle;
    pen fill_pen = highlighted ? cell_highlight_f : white;
    pen edge_pen = highlighted ? cell_highlight   : cell_line;
    filldraw(cell, fill_pen, edge_pen);

    // 3 × 3 mini-grid of D2Q9 DF dots.
    real dot_r = 0.08;
    real step  = s / 4.0;
    pen dot_f  = written ? df_written_fill : df_fill;
    pen dot_e  = written ? df_written_edge : df_edge;
    for (int di = 0; di < 3; ++di) {
        for (int dj = 0; dj < 3; ++dj) {
            pair c = tl + (step * (di + 1), step * (dj + 1));
            filldraw(circle(c, dot_r), dot_f, dot_e);
        }
    }
}

// A rounded kernel box with bold title + monospaced code line.
void draw_kernel(pair centre, real w, real h,
                 string title, string code)
{
    pair tl = centre - (w / 2, h / 2);
    pair br = centre + (w / 2, h / 2);
    path p = tl -- (br.x, tl.y) -- br -- (tl.x, br.y) -- cycle;
    filldraw(p, kernel_fill, kernel_edge);

    label(title, centre + (0, 0.18), kernel_title_pen);
    label(Label("\texttt{" + code + "}", kernel_code_pen),
          centre + (0, -0.18));
}

// ============================================================
//  Input Region — 3 × 3 macro-cell stencil
// ============================================================

real region_pad   = 0.45;      // padding inside region backgrounds
real cell_size    = 1.25;      // side of one macro cell
real cell_gap     = 0.18;      // gap between macro cells

real input_x0 = 0.0;
real input_y0 = 0.0;
real input_w  = 3 * cell_size + 2 * cell_gap + 2 * region_pad;
// Taller than the input grid alone — needs to fit the 5-stage
// pipeline on the centre column without spilling below the page.
real input_h  = 8.5;

// Background & border.
filldraw(
    (input_x0, input_y0) --
    (input_x0 + input_w, input_y0) --
    (input_x0 + input_w, input_y0 + input_h) --
    (input_x0, input_y0 + input_h) -- cycle,
    bg_input, region_edge);

// Title + caption.
label("Input region",
      (input_x0 + input_w / 2, input_y0 + input_h - 0.35),
      title_pen);

label(Label("\shortstack{stencil neighbourhood\\9 cells $\times$ 9 DFs}",
            sub_pen),
      (input_x0 + input_w / 2, input_y0 + 0.45));

// 3 × 3 grid of macro cells. The centre cell is highlighted —
// conceptually, it's the cell being updated; the 8 neighbours
// plus itself form the pull-scheme stencil.
real grid_x0 = input_x0 + region_pad;
real grid_y0 = input_y0 + region_pad + 1.0;       // +1 for caption space

for (int mi = 0; mi < 3; ++mi) {
    for (int mj = 0; mj < 3; ++mj) {
        pair tl = (grid_x0 + mi * (cell_size + cell_gap),
                   grid_y0 + mj * (cell_size + cell_gap));
        draw_macro_cell(tl, cell_size, highlighted = (mi == 1 && mj == 1));
    }
}

// (No explicit "(x, y)" callout here — the amber-highlighted
// border on the centre cell is sufficient visual signal, and
// the thesis uses axis labels rather than in-grid annotations.)

// ============================================================
//  Pipeline — 5 vertical kernel stages + type-annotated arrows
// ============================================================

real pipe_x0 = input_x0 + input_w + 1.8;
real pipe_w  = 6.8;
real pipe_h  = input_h;          // match input region height
real pipe_y0 = input_y0;

// Background & border.
filldraw(
    (pipe_x0, pipe_y0) --
    (pipe_x0 + pipe_w, pipe_y0) --
    (pipe_x0 + pipe_w, pipe_y0 + pipe_h) --
    (pipe_x0, pipe_y0 + pipe_h) -- cycle,
    bg_pipeline, region_edge);

label("Dynamics pipeline",
      (pipe_x0 + pipe_w / 2, pipe_y0 + pipe_h - 0.35),
      title_pen);

// Kernel stage definitions.
string stage_titles[] = {
    "1. Read stencil",
    "2. Compute moments",
    "3. Compute equilibrium",
    "4. BGK collision",
    "5. Write result"
};
string stage_code[] = {
    "upstream\_dfs(f, x, y, \{EX, EY\})",
    "Macro(fIn)",
    "Feq(rho, ux, uy)",
    "fIn - OMEGA * (fIn - fEq)",
    "f.out[x, y | :] = fOut"
};
string type_between[] = {
    "\texttt{array[real, 9] fIn}",
    "\texttt{real rho, ux, uy}",
    "\texttt{array[real, 9] fEq}",
    "\texttt{array[real, 9] fOut}"
};

int NSTAGES = 5;
real stage_w = pipe_w - 1.0;
real stage_h = 0.95;
real type_gap = 0.55;             // vertical gap between stages (for arrow + label)

// Sanity-check that the 5 stages + 4 gaps fit within the pipeline
// container minus the title band. If this assertion fires in a
// future edit, bump input_h (line above) to match.
real pipe_title_band = 0.9;
real pipe_bottom_pad = 0.5;
real available_h     = pipe_h - pipe_title_band - pipe_bottom_pad;
real needed_h        = NSTAGES * stage_h + (NSTAGES - 1) * type_gap;
assert(needed_h <= available_h, "pipeline stages do not fit — bump input_h");
real pipe_top_start  = pipe_y0 + pipe_h - pipe_title_band - stage_h / 2;
real stage_pitch     = stage_h + type_gap;

pair stage_centres[];
for (int k = 0; k < NSTAGES; ++k) {
    stage_centres.push((pipe_x0 + pipe_w / 2,
                        pipe_top_start - k * stage_pitch));
    draw_kernel(stage_centres[k], stage_w, stage_h,
                stage_titles[k], stage_code[k]);
}

// Type-annotated arrows between stages.
for (int k = 0; k < NSTAGES - 1; ++k) {
    pair tail = stage_centres[k]   - (0, stage_h / 2);
    pair head = stage_centres[k+1] + (0, stage_h / 2);
    draw(tail -- head, arrow_pen, arrow=Arrow(size=5));
    // Type label, offset slightly to the right of the arrow.
    label(Label(type_between[k], type_pen),
          ((tail.x + head.x) / 2 + stage_w / 2 + 0.25,
           (tail.y + head.y) / 2),
          E);
}

// ============================================================
//  Output Region — the single cell being written
// ============================================================

real out_w  = cell_size + 2 * region_pad + 1.2;
real out_h  = input_h;
real out_x0 = pipe_x0 + pipe_w + 1.8;
real out_y0 = input_y0;

filldraw(
    (out_x0, out_y0) --
    (out_x0 + out_w, out_y0) --
    (out_x0 + out_w, out_y0 + out_h) --
    (out_x0, out_y0 + out_h) -- cycle,
    bg_output, region_edge);

label("Output region",
      (out_x0 + out_w / 2, out_y0 + out_h - 0.35),
      title_pen);

label(Label("\shortstack{1 cell $\times$ 9 DFs\\written}", sub_pen),
      (out_x0 + out_w / 2, out_y0 + 0.45));

// Single macro cell with post-write (amber) DFs. Vertically
// aligned with the last pipeline stage so the exit arrow can run
// cleanly horizontal.
pair out_cell_tl = (out_x0 + out_w / 2 - cell_size / 2,
                    stage_centres[NSTAGES - 1].y - cell_size / 2);
draw_macro_cell(out_cell_tl, cell_size,
                highlighted = true, written = true);

// ============================================================
//  Connecting arrows: Input → Pipeline, Pipeline → Output
// ============================================================

// Input region → first stage. From the right edge of the input
// region to the left edge of the first kernel.
pair in_exit     = (input_x0 + input_w,       stage_centres[0].y);
pair pipe_entry  = stage_centres[0] - (stage_w / 2, 0);
draw(in_exit{E} .. {E}pipe_entry,
     arrow_big_pen, arrow=Arrow(size=7));

// Last stage → output region. From the right edge of stage 5 to
// the left edge of the output cell.
pair pipe_exit   = stage_centres[NSTAGES - 1] + (stage_w / 2, 0);
pair out_entry   = (out_x0, stage_centres[NSTAGES - 1].y);
draw(pipe_exit{E} .. {E}out_entry,
     arrow_big_pen, arrow=Arrow(size=7));

// Strap-line beneath the figure.
label(Label(
    "\textit{One iteration of the Dynamic phase for a D2Q9 pull-scheme BGK collision.}",
    fontsize(8pt) + gray(0.35)),
    (pipe_x0 + pipe_w / 2, input_y0 - 0.8));
