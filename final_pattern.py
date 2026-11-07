#!/usr/bin/env python3
"""Build a full-size stained-glass pattern with uniform lines.

  python3 final_pattern.py input.png out_prefix --size-in 18 --line-in 0.03125 --dpi 300

Steps: flatten alpha, crop to the drawing, upscale so the drawing's wider side
equals --size-in, smooth + threshold, skeletonize to centerlines, prune spurs,
bridge small gaps where a line stops short of another, then redraw every
centerline at exactly --line-in wide. Writes a full-size PNG and PDF (one
square page) and a tiled letter-size PDF for home printing.
"""
import argparse
from collections import deque
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi
from skimage.morphology import skeletonize, disk, dilation, remove_small_objects
import cv2
import warnings
warnings.filterwarnings("ignore")

Image.MAX_IMAGE_PIXELS = None


def neighbours(skel):
    k = np.ones((3, 3), int); k[1, 1] = 0
    return ndi.convolve(skel.astype(int), k, mode="constant") * skel


def prune(skel, max_len):
    for _ in range(3):
        nb = neighbours(skel)
        jmask = dilation(nb >= 3, disk(1))
        lab, n = ndi.label(skel & ~jmask, structure=np.ones((3, 3)))
        if n == 0:
            break
        idx = range(1, n + 1)
        sizes = ndi.sum(np.ones_like(lab), lab, idx)
        has_end = ndi.maximum(nb == 1, lab, idx)
        touches = ndi.maximum(dilation(jmask, disk(1)), lab, idx)
        kill = np.zeros(n + 1, bool)
        kill[1:] = (sizes < max_len) & (has_end > 0) & (touches > 0)
        if not kill.any():
            break
        skel = skel.copy(); skel[kill[lab]] = False
        skel = skeletonize(skel)
    return skel


def bridge_gaps(skel, max_gap, own_len):
    H, W = skel.shape
    ys, xs = np.nonzero(skel)
    canvas = skel.astype(np.uint8)
    report = []
    for y, x in zip(*np.nonzero(neighbours(skel) == 1)):
        seen = {(y, x)}; q = deque([(y, x, 0)])
        while q:  # pixels along this line's own path, to exclude
            cy, cx, d = q.popleft()
            if d >= own_len:
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    p = (cy + dy, cx + dx)
                    if p not in seen and 0 <= p[0] < H and 0 <= p[1] < W and skel[p]:
                        seen.add(p); q.append((p[0], p[1], d + 1))
        near = (np.abs(ys - y) < max_gap) & (np.abs(xs - x) < max_gap)
        cand = [(np.hypot(a - y, b - x), a, b) for a, b in zip(ys[near], xs[near])
                if (a, b) not in seen]
        cand = [c for c in cand if c[0] < max_gap]
        if cand:
            d, ty, tx = min(cand)
            cv2.line(canvas, (int(x), int(y)), (int(tx), int(ty)), 1, 2)
            report.append(("bridged", x, y, d))
        else:
            report.append(("open tip", x, y, 0))
    return skeletonize(canvas.astype(bool)), report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("prefix")
    ap.add_argument("--size-in", type=float, default=18)
    ap.add_argument("--line-in", type=float, default=1 / 32)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--page-in", type=float, default=None, help="square page size; default size+1")
    a = ap.parse_args()

    im = Image.open(a.src).convert("RGBA")
    flat = Image.alpha_composite(Image.new("RGBA", im.size, "white"), im).convert("L")
    g = np.array(flat)
    ys, xs = np.nonzero(g < 128)
    pad = 20
    crop = flat.crop((xs.min() - pad, ys.min() - pad, xs.max() + pad, ys.max() + pad))
    span = max(xs.max() - xs.min(), ys.max() - ys.min())
    scale = a.size_in * a.dpi / span
    big = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.LANCZOS)
    arr = ndi.gaussian_filter(np.array(big, float), scale * 0.6)
    ink = remove_small_objects(arr < 160, int(20 * scale * scale))
    print(f"scale x{scale:.2f}, drawing {(xs.max()-xs.min())*scale/a.dpi:.2f} x "
          f"{(ys.max()-ys.min())*scale/a.dpi:.2f} in")

    skel = skeletonize(ink)
    skel = prune(skel, int(12 * scale))
    skel, report = bridge_gaps(skel, max_gap=15 * scale, own_len=int(60 * scale))
    for r in report:
        print(f"{r[0]} at ({r[1]/scale/1:.0f},{r[2]/scale:.0f}) crop-px" + (f", gap {r[3]/a.dpi:.3f} in" if r[3] else ""))

    # exact-width redraw: everything within line/2 of a centerline
    dist = ndi.distance_transform_edt(~skel)
    half = a.line_in * a.dpi / 2
    lines = dist <= half
    # fill pinholes left inside junctions
    lab, n = ndi.label(~lines)
    sizes = ndi.sum(np.ones_like(lab), lab, range(1, n + 1))
    small = np.zeros(n + 1, bool); small[1:] = sizes < (0.1 * a.dpi) ** 2
    lines[small[lab]] = True

    # ---- pieces: find each enclosed region and a label spot inside it ----
    lab, n = ndi.label(~lines)
    border = set(np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    objs = ndi.find_objects(lab)
    pieces = []
    for i, sl in enumerate(objs, 1):
        if i in border or sl is None:
            continue
        m = lab[sl] == i
        dt = ndi.distance_transform_edt(m)
        y, x = np.unravel_index(np.argmax(dt), dt.shape)  # most interior point
        pieces.append(dict(area=m.sum() / a.dpi ** 2, y=y + sl[0].start,
                           x=x + sl[1].start, r=dt.max()))
    band = 2.5 * a.dpi  # number top-to-bottom in 2.5" bands, left-to-right within a band
    pieces.sort(key=lambda p: (int(p["y"] // band), p["x"]))
    print(f"{len(pieces)} pieces; smallest areas (sq in): " +
          ", ".join(f"{p['area']:.2f}" for p in sorted(pieces, key=lambda p: p['area'])[:4]))

    def font_at(px):
        try:
            return ImageFont.truetype("DejaVuSans-Bold.ttf", int(px))
        except OSError:
            return ImageFont.load_default()

    # ---- page layout ----
    page_in = a.page_in or a.size_in + 1
    P = round(page_in * a.dpi)
    h, w = lines.shape
    oy, ox = (P - h) // 2, (P - w) // 2

    def make_page(numbered):
        page = np.full((P, P), 255, np.uint8)
        page[oy:oy + h, ox:ox + w][lines] = 0
        img = Image.fromarray(page)
        d = ImageDraw.Draw(img)
        if numbered:
            for k, p in enumerate(pieces, 1):
                size = min(0.30 * a.dpi, p["r"] * 1.1)
                d.text((ox + p["x"], oy + p["y"]), str(k), fill=0,
                       font=font_at(max(size, 0.08 * a.dpi)), anchor="mm")
        m = int(0.3 * a.dpi)
        d.rectangle([m, P - m - a.dpi, m + a.dpi, P - m], outline=0, width=3)
        d.text((m + a.dpi + 20, P - m - int(0.2 * a.dpi)),
               f'1" check square  |  lines {a.line_in:.4f}"  |  drawing {a.size_in}" wide'
               + (f"  |  {len(pieces)} pieces" if numbered else ""),
               fill=0, font=font_at(0.14 * a.dpi))
        return img

    def tile(img, path):
        pw, ph = int(8.5 * a.dpi), int(11 * a.dpi)
        mg, ov = int(0.5 * a.dpi), int(0.5 * a.dpi)
        tw, th = pw - 2 * mg, ph - 2 * mg
        stepx, stepy = tw - ov, th - ov
        cols = int(np.ceil((P - ov) / stepx)); rows = int(np.ceil((P - ov) / stepy))
        pages = []
        for r in range(rows):
            for c in range(cols):
                t = img.crop((c * stepx, r * stepy, c * stepx + tw, r * stepy + th))
                pg = Image.new("L", (pw, ph), 255); pg.paste(t, (mg, mg))
                dd = ImageDraw.Draw(pg)
                dd.rectangle([mg, mg, mg + tw, mg + th], outline=160, width=2)
                dd.line([mg + tw - ov, mg, mg + tw - ov, mg + th], fill=190, width=2)
                dd.line([mg, mg + th - ov, mg + tw, mg + th - ov], fill=190, width=2)
                dd.text((mg, int(0.15 * a.dpi)),
                        f"Row {chr(65 + r)}  Col {c + 1}   ({len(pages) + 1} of {rows * cols})"
                        f"  - overlap 0.5\" at grey lines", fill=0, font=font_at(0.14 * a.dpi))
                pages.append(pg)
        pages[0].save(path, resolution=a.dpi, save_all=True, append_images=pages[1:])
        return rows * cols

    plain = make_page(False)
    plain.save(f"{a.prefix}_fullsize.png", dpi=(a.dpi, a.dpi))
    plain.save(f"{a.prefix}_fullsize.pdf", resolution=a.dpi)
    tile(plain, f"{a.prefix}_tiled_letter.pdf")

    numbered = make_page(True)
    numbered.save(f"{a.prefix}_numbered.png", dpi=(a.dpi, a.dpi))
    numbered.save(f"{a.prefix}_numbered.pdf", resolution=a.dpi)
    n_pages = tile(numbered, f"{a.prefix}_numbered_tiled_letter.pdf")
    print(f"tiled: {n_pages} letter pages per set")

    # ---- Silhouette: lines only, no numbers or legend, cropped to the drawing ----
    ys, xs = np.nonzero(lines)
    mg = int(0.1 * a.dpi)
    cut = np.full((ys.max() - ys.min() + 1 + 2 * mg, xs.max() - xs.min() + 1 + 2 * mg), 255, np.uint8)
    cut[mg:-mg, mg:-mg][lines[ys.min():ys.max() + 1, xs.min():xs.max() + 1]] = 0
    Image.fromarray(cut).save(f"{a.prefix}_silhouette.png", dpi=(a.dpi, a.dpi))
    print(f"silhouette png: {cut.shape[1] / a.dpi:.3f} x {cut.shape[0] / a.dpi:.3f} in incl. 0.1in margin; "
          f"artwork {(xs.max() - xs.min() + 1) / a.dpi:.3f} x {(ys.max() - ys.min() + 1) / a.dpi:.3f} in")


if __name__ == "__main__":
    main()
