"""App Store SEARCH RESULTS asset: same design as the header, type only, sized for the search preview.

Ryan 2026-10-07, after ASC's preview of the header in search: "at search size, 267 survives and everything else
disappears. The phone is a blur. The MedXPress line is gone." So search gets its own file and the header keeps its phone
(`build-header-asset.py`, unchanged). In ASC: uncheck "Use header asset in search results" and upload this on the
Search Results tab, which accepts 5244 x 2950, 3840 x 2560 or 1920 x 1280.

Spec, exact: blue field #1C66D9, white type. 267, large. Under it: Days remaining / Class 1 medical / expires Jun 30, 2027.
Under the date, ONE line: "MedXPress, filled from your own records." No phone, no Mac, no second feature, no price, URL,
FAA approval, fit-to-fly wording or em dash.

Layout is drawn into a content box, then placed on each canvas:
  - universal 5244 x 2950: the box is Apple's art safe area (x 1922-3322, y 660-1620), outside it plain blue bleed.
  - 3840 x 2560 and 1920 x 1280 (3:2): the box fills the canvas inside a margin, so the type is as large as the slot
    allows. The safe area is about 3:2 too (1400 x 960), which is why one layout serves all three.
The MedXPress line is sized to span the box width on one line, and everything else is sized from it, so the smallest
type on the asset is that line, at about 4% of the asset's width.
"""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = os.path.expanduser("~/pilot-medical-guardian-content/screenshots/asc/search")
SF = "/System/Library/Fonts/SFNS.ttf"
BLUE = (0x1C, 0x66, 0xD9)
WHITE = (255, 255, 255)
LINE = "MedXPress, filled from your own records."


def font(size, weight):
    f = ImageFont.truetype(SF, max(8, int(size)))
    vals = []
    for a in f.get_variation_axes():
        n = a["name"].decode() if isinstance(a["name"], bytes) else a["name"]
        vals.append({"Weight": weight, "Optical Size": min(max(96, a["minimum"]), a["maximum"])}.get(n, a["default"]))
    f.set_variation_by_axes(vals)
    return f


def draw_stack(canvas, box):
    """Left-aligned stack, vertically centred in `box` (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    d = ImageDraw.Draw(canvas)
    mx = round(bw * 0.06)
    width = bw - 2 * mx

    # The one-line MedXPress line sets the scale: as large as fits the width.
    s = 400
    while d.textlength(LINE, font=font(s, 600)) > width:
        s -= 1
    line_f = font(s, 600)
    rows = [("Days remaining", font(s * 1.30, 600), s * 0.45),
            ("Class 1 medical", font(s * 1.06, 440), s * 0.32),
            ("expires Jun 30, 2027", font(s * 1.06, 440), s * 0.70),
            (LINE, line_f, 0)]
    rows_h = sum(f.getbbox(t)[3] - f.getbbox(t)[1] + g for t, f, g in rows)

    # 267 takes the height that is left, never wider than the column.
    gap_after_big = s * 0.75
    avail = bh * 0.84 - rows_h - gap_after_big
    big_s = 3000
    while True:
        bf = font(big_s, 700)
        bb = bf.getbbox("267")
        if bb[3] - bb[1] <= avail and d.textlength("267", font=bf) <= width:
            break
        big_s -= 2
    bb = bf.getbbox("267")
    total = (bb[3] - bb[1]) + gap_after_big + rows_h
    y = y0 + (bh - total) / 2
    x = x0 + mx
    d.text((x - bb[0] * 0.5, y - bb[1]), "267", font=bf, fill=WHITE)
    y += (bb[3] - bb[1]) + gap_after_big
    for text, f, gap in rows:
        b = f.getbbox(text)
        d.text((x, y - b[1]), text, font=f, fill=WHITE)
        assert x + d.textlength(text, font=f) <= x1 - mx + 1, f"{text!r} overruns the box"
        y += (b[3] - b[1]) + gap
    assert y <= y1, "stack overruns the box"
    return {"line_px": s, "big_px": big_s, "box": box}


def build(w, h, box, name):
    c = Image.new("RGB", (w, h), BLUE)
    info = draw_stack(c, box)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    c.save(path, optimize=True)
    print(f"wrote {name} {c.size} line {info['line_px']}px ({info['line_px'] / (box[2] - box[0]):.1%} of box width), 267 at {info['big_px']}px")
    return c


def main():
    build(5244, 2950, (1922, 660, 3322, 1620), "pmg-search-universal-5244x2950.png")
    m = 2560 * 0.05
    big = build(3840, 2560, (round(m), round(m), round(3840 - m), round(2560 - m)), "pmg-search-3840x2560.png")
    big.resize((1920, 1280), Image.LANCZOS).save(os.path.join(OUT, "pmg-search-1920x1280.png"), optimize=True)
    print("wrote pmg-search-1920x1280.png (1920, 1280)")
    # What a search tile shows at phone size: roughly 340pt wide, so 340 px at 1x and 1020 px at 3x.
    big.resize((340, round(340 * 2560 / 3840)), Image.LANCZOS).save(os.path.join(OUT, "preview-search-340pt-1x.png"))
    big.resize((1020, 680), Image.LANCZOS).save(os.path.join(OUT, "preview-search-340pt-3x.png"))


if __name__ == "__main__":
    main()
