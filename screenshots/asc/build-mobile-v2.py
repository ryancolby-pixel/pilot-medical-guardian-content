from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np, os

BASE = os.path.expanduser("~/pilot-medical-guardian-content/screenshots")
SF = "/System/Library/Fonts/SFNS.ttf"
WEIGHTS = {"Regular": 400, "Medium": 510, "Semibold": 590, "Bold": 700}


def sf(size, weight="Semibold", optical=96):
    f = ImageFont.truetype(SF, size)
    try:
        axes = f.get_variation_axes()
        vals = []
        for a in axes:
            n = a["name"].decode() if isinstance(a["name"], bytes) else a["name"]
            if n == "Optical Size":
                vals.append(min(max(optical, a["minimum"]), a["maximum"]))
            elif n == "Weight":
                vals.append(WEIGHTS.get(weight, 590))
            else:
                vals.append(a["default"])
        f.set_variation_by_axes(vals)
    except Exception:
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
    return f


def background(W, H, gx, gy):
    yv = np.linspace(0.0, 1.0, H)[:, None]
    top = np.array([6, 18, 37], float)
    bot = np.array([14, 44, 82], float)
    t = yv ** 0.85
    bg = top[None, None, :] * (1 - t[:, :, None]) + bot[None, None, :] * t[:, :, None]
    bg = np.repeat(bg, W, axis=1)

    xx, yy = np.meshgrid(np.arange(W), np.arange(H))
    r = np.sqrt(((xx - gx) / (W * 0.90)) ** 2 + ((yy - gy) / (H * 0.85)) ** 2)
    glow = np.clip(1.0 - r, 0, 1) ** 2.1
    bg = bg + glow[:, :, None] * np.array([44, 104, 186], float)[None, None, :]

    rv = np.sqrt(((xx - W / 2) / (W * 0.78)) ** 2 + ((yy - H / 2) / (H * 0.80)) ** 2)
    vig = np.clip(rv - 0.58, 0, 1) ** 1.7
    bg = bg * (1.0 - vig[:, :, None] * 0.5)
    return Image.fromarray(np.clip(bg, 0, 255).astype("uint8"), "RGB")


def round_corners(im, radius):
    """Screen captures are square cornered; real devices are not."""
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.size[0] - 1, im.size[1] - 1],
                                           radius=radius, fill=255)
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def hairline(alpha):
    inner = alpha.filter(ImageFilter.MinFilter(5))
    edge = np.clip(np.array(alpha, float) - np.array(inner, float), 0, 255).astype("uint8")
    return Image.fromarray(edge, "L").filter(ImageFilter.GaussianBlur(0.6))


def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def tracked(draw, x, y, text, font, fill, tracking, measure_only=False):
    total = 0.0
    for ch in text:
        if not measure_only:
            draw.text((x + total, y), ch, font=font, fill=fill)
        total += draw.textlength(ch, font=font) + tracking
    return total - tracking if text else 0.0


def measure_lines(canvas_w, headline, head_size, side_pad):
    probe = ImageDraw.Draw(Image.new("RGB", (canvas_w, 10)))
    hf = sf(head_size, "Semibold", optical=96)
    return len(wrap(probe, headline, hf, canvas_w - side_pad * 2))


def build(canvas_w, canvas_h, src_path, eyebrow, headline, out_path,
          corner, eyebrow_size, head_size, top_pad, side_pad, bottom_pad, track,
          fixed_lines=None):
    src = Image.open(src_path).convert("RGB")
    shot = round_corners(src, corner)

    # measure the headline block first so the device can sit under it
    probe = Image.new("RGB", (canvas_w, canvas_h))
    pd = ImageDraw.Draw(probe)
    hf = sf(head_size, "Semibold", optical=96)
    lines = wrap(pd, headline, hf, canvas_w - side_pad * 2)
    lh = int(head_size * 1.17)
    head_top = top_pad + int(eyebrow_size * 2.1)
    head_bottom = head_top + lh * len(lines)
    # every shot in a set must share device geometry, so reserve the worst case
    reserve = lh * (fixed_lines if fixed_lines else len(lines))
    dev_top = head_top + reserve + int(canvas_h * 0.035)

    avail_h = canvas_h - dev_top - bottom_pad
    avail_w = canvas_w - side_pad * 2
    scale = min(avail_w / shot.width, avail_h / shot.height)
    dw, dh = int(shot.width * scale), int(shot.height * scale)
    shot = shot.resize((dw, dh), Image.LANCZOS)
    dx = (canvas_w - dw) // 2
    dy = dev_top

    canvas = background(canvas_w, canvas_h, canvas_w / 2, dy + dh * 0.45).convert("RGBA")

    mask = Image.new("L", (canvas_w, canvas_h), 0)
    mask.paste(shot.getchannel("A"), (dx, dy))
    for blur, spread, off, op in ((int(canvas_w * 0.075), 6, int(canvas_h * 0.022), 0.55),
                                  (int(canvas_w * 0.026), 2, int(canvas_h * 0.008), 0.42)):
        a = mask.filter(ImageFilter.MaxFilter(spread * 2 + 1)) if spread else mask
        a = a.filter(ImageFilter.GaussianBlur(blur))
        a = a.point(lambda v, o=op: int(v * o))
        shifted = Image.new("L", (canvas_w, canvas_h), 0)
        shifted.paste(a, (0, off))
        shade = Image.new("RGBA", (canvas_w, canvas_h), (2, 8, 18, 255))
        shade.putalpha(shifted)
        canvas = Image.alpha_composite(canvas, shade)

    canvas.alpha_composite(shot, (dx, dy))

    hl = Image.new("L", (canvas_w, canvas_h), 0)
    hl.paste(hairline(shot.getchannel("A")), (dx, dy))
    hl = hl.point(lambda v: int(v * 0.30))
    hl_layer = Image.new("RGBA", (canvas_w, canvas_h), (188, 214, 250, 255))
    hl_layer.putalpha(hl)
    canvas = Image.alpha_composite(canvas, hl_layer)

    d = ImageDraw.Draw(canvas)
    ef = sf(eyebrow_size, "Bold", optical=40)
    ew = tracked(d, 0, 0, eyebrow, ef, None, track, measure_only=True)
    tracked(d, (canvas_w - ew) / 2, top_pad, eyebrow, ef, (126, 173, 235, 255), track)

    y = head_top
    for ln in lines:
        lw = d.textlength(ln, font=hf)
        d.text(((canvas_w - lw) / 2, y), ln, font=hf, fill=(255, 255, 255, 255))
        y += lh

    assert head_bottom < dev_top, "headline would collide with the device"
    canvas.convert("RGB").save(out_path, "PNG")
    return dw, dh, len(lines)


IPAD = [
    ("03-medxpress-prep.png", "MEDXPRESS PREP",     "Your answers ready before you sit down"),
    ("01-home.png",           "AT A GLANCE",        "Every date that matters, in one place"),
    ("06-special-issuance.png","SPECIAL ISSUANCE",  "See what you sent and what is open"),
    ("05-health-bp.png",      "BLOOD PRESSURE",     "Your readings beside the FAA threshold"),
    ("08-share-with-ame.png", "SHARE WITH YOUR AME","Send your AME a clean packet"),
    ("02-faa-reference.png",  "FAA REFERENCE",      "The FAA's own words, with the source"),
    ("07-my-medical.png",     "MY MEDICAL",         "Class 1, 2, 3 and BasicMed together"),
    ("04-health.png",         "HEALTH",             "Readings and labs in one timeline"),
]

IPHONE = [
    ("medxpress.png",      "MEDXPRESS PREP",   "Your answers ready before you sit down"),
    ("home.png",           "AT A GLANCE",      "Every date that matters, in one place"),
    ("si.png",             "SPECIAL ISSUANCE", "See what you sent and what is open"),
    ("health.png",         "HEALTH",           "Your readings beside the FAA threshold"),
    ("basicmed.png",       "BASICMED",         "Course and exam dates, tracked together"),
    ("faa-reference.png",  "FAA REFERENCE",    "The FAA's own words, with the source"),
    ("documents.png",      "DOCUMENTS",        "Your paperwork in one place"),
]

jobs = [
    ("ipad-v2",  2064, 2752, os.path.join(BASE, "asc", "ipad"), IPAD,
     92, 44, 96, 150, 130, 150, 8.0),
    ("iphone-v2", 1290, 2796, BASE, IPHONE,
     116, 32, 74, 130, 96, 120, 6.0),
]

for outdir, cw, ch, srcdir, shots, corner, eb, hs, tp, sp, bp, tk in jobs:
    out = os.path.join(BASE, "asc", outdir)
    os.makedirs(out, exist_ok=True)
    maxlines = max(measure_lines(cw, h, hs, sp) for _, _, h in shots)
    print("\n== %s  (%dx%d)  headline lines reserved: %d ==" % (outdir, cw, ch, maxlines))
    for i, (fn, eyebrow, headline) in enumerate(shots, start=1):
        stem = fn.split("-", 1)[1] if fn[0].isdigit() else fn
        name = "%02d-%s" % (i, stem)
        dw, dh, nl = build(cw, ch, os.path.join(srcdir, fn), eyebrow, headline,
                           os.path.join(out, name), corner, eb, hs, tp, sp, bp, tk,
                           fixed_lines=maxlines)
        print("  %-30s device %dx%d  headline lines=%d" % (name, dw, dh, nl))
print("\ndone")
