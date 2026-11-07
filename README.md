# stained-glass-tools

Turns hand-drawn line art (e.g. a Procreate PNG export) into a full-size stained-glass
pattern with perfectly uniform lines, numbered pieces, and a clean file for a Silhouette
cutter.

## What it does

1. Flattens transparency onto white and crops to the drawing.
2. Scales the drawing so its wider side equals the finished size you ask for.
3. Reduces every line to a one-pixel centerline (skeletonize), prunes stray spurs at
   corners and joins, and bridges small gaps where a line stops just short of another.
4. Redraws every centerline at exactly the line width you specify.
5. Finds each enclosed piece, numbers it (top to bottom, left to right) and reports the
   smallest pieces so you can spot slivers before cutting.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
python3 final_pattern.py drawing.png out/myproject --size-in 18 --line-in 0.03125 --dpi 300
```

| Option | Meaning | Default |
|---|---|---|
| `--size-in` | Finished width of the drawing's wider side, in inches | 18 |
| `--line-in` | Line width in inches (1/32 = 0.03125, 1/16 = 0.0625) | 1/32 |
| `--dpi` | Output resolution | 300 |
| `--page-in` | Square page size for full-size output | size + 1 |

The console output lists any gaps it bridged, open tips it left alone, the piece count,
and the smallest piece areas.

## Outputs

| File | Use |
|---|---|
| `*_silhouette.png` | Lines only, cropped to the drawing with a 0.1" margin. Import into Silhouette and trace. |
| `*_numbered.png` / `.pdf` | Full-size numbered pattern on one page, with a 1" check square. |
| `*_numbered_tiled_letter.pdf` | The numbered pattern split across letter pages with 0.5" overlap. |
| `*_fullsize.png` / `.pdf`, `*_tiled_letter.pdf` | Same as above without numbers. |

## Tips

- **Silhouette import size:** Silhouette Studio often ignores PNG DPI. After importing
  `*_silhouette.png`, set its width to the size the script printed (artwork + 0.2")
  with the aspect ratio locked, then trace.
- **Tracing doubles lines:** the tracer outlines both edges of each line. That is right
  for cutting line shapes from vinyl, but a sketch pen will draw each line twice.
- **Printing:** print at 100% / "Actual size" and measure the 1" check square first.
- **Start clean:** export only the line-art layer from Procreate, at full canvas size,
  with no colour or sketch layers visible.

## Examples

`examples/wreath/` contains a holly wreath drawn in Procreate and the patterns produced
at 18" with 1/32" lines (41 pieces).
