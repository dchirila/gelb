# Terse listings for the paper

Print-compact versions of the parent programs, formatted so that **no
line wraps in the typeset paper**: every line is at most 68 characters
(the paper's listing style holds ~70 at `\footnotesize` with
`columns=fullflexible`). Relative to the fully-commented originals one
directory up: comment blocks are condensed and reflowed, long trailing
comments are shortened or moved onto their own line before the code,
and a handful of over-long code statements are split across two lines
— but the **code is token-identical** to the originals.

Verified mechanically: (1) comment/whitespace-stripped token streams of
terse and original are identical, (2) no line exceeds 68 characters,
(3) all four terse files compile unchanged with `gelbc`. The paper sets
`breaklines=false`, so any future over-long line shows up as an
"Overfull \hbox" warning at paper-compile time instead of silently
wrapping.

| File | Lines (terse / full) |
|------|----------------------|
| `taylor_green_vortex_2d_bgk.gelb` | 70 / 76 |
| `rayleigh_benard_2d_bgk.gelb` | 121 / 164 |
| `flow_past_cylinder_2d_bgk_zouhe.gelb` | 155 / 179 |
| `flow_past_madeira_2d_bgk_zouhe.gelb` | 197 / 212 (47 generated spans in both) |

The paper's printed listings are byte-identical copies of these files
(the Madeira one with its 47 generated `nodes` span statements elided).
If a parent program changes, apply the same code change to the terse
twin (splitting any line longer than 68 characters) and re-run the
three checks; the Madeira spans are copied verbatim from the generated
parent file.
