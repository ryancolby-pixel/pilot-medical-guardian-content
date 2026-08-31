from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np, os, shutil

SRC = os.path.expanduser("~/pilot-medical-guardian-content/screenshots/asc/mac-raw")
OUT = os.path.expanduser("~/pilot-medical-guardian-content/screenshots/asc/mac-v2")
W, H = 2880, 1800
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


def background(gx, gy):
    """Deep navy gradient, radial brand glow behind the window, soft vignette."""
    yv = np.linspace(0.0, 1.0, H)[:, None]
    top = np.array([6, 18, 37], float)
    bot = np.array([14, 44, 82], float)
    t = yv ** 0.85
    bg = top[None, None, :] * (1 - t[:, :, None]) + bot[None, None, :] * t[:, :, None]
    bg = np.repeat(bg, W, axis=1)

    xx, yy = np.meshgrid(np.arange(W), np.arange(H))
    r = np.sqrt(((xx - gx) / (W * 0.80)) ** 2 + ((yy - gy) / (H * 1.00)) ** 2)
    glow = np.clip(1.0 - r, 0, 1) ** 2.1
    bg = bg + glow[:, :, None] * np.array([44, 104, 186], float)[None, None, :]

    rv = np.sqrt(((xx - W / 2) / (W * 0.74)) ** 2 + ((yy - H / 2) / (H * 0.80)) ** 2)
    vig = np.clip(rv - 0.58, 0, 1) ** 1.7
    bg = bg * (1.0 - vig[:, :, None] * 0.5)

    return Image.fromarray(np.clip(bg, 0, 255).astype("uint8"), "RGB")


def hairline(alpha):
    """Thin highlight tracing the window edge so it lifts off the dark ground."""
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


SHOTS = [
    ("03-medxpress-prep.png", "MEDXPRESS PREP",   "Your answers ready before you sit down"),
    ("01-home.png",           "AT A GLANCE",      "Every date that matters, in one place"),
    ("04-item18.png",         "ITEM 18",          "Answer it once, keep it every renewal"),
    ("07-hypertension.png",   "SPECIAL ISSUANCE", "See what you sent and what is open"),
    ("05-health.png",         "HEALTH",           "Your readings beside the FAA threshold"),
    ("02-faa-reference.png",  "FAA REFERENCE",    "The FAA's own words, with the source"),
    ("06-certificate.png",    "MY MEDICAL",       "Class 1, 2, 3 and BasicMed together"),
]

WIN_H = 1424
TOP_Y = 318
BOTTOM_CROP = 0.06  # every Mac shot measured >=6.2% empty below its last ink

# wipe first: a reorder leaves stale files behind that would ship
if os.path.isdir(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT, exist_ok=True)

for idx, (fname, eyebrow, headline) in enumerate(SHOTS, start=1):
    src = Image.open(os.path.join(SRC, fname)).convert("RGBA")
    src = src.crop((0, 0, src.width, int(src.height * (1 - BOTTOM_CROP))))
    scale = WIN_H / src.height
    win_w = int(round(src.width * scale))
    win = src.resize((win_w, WIN_H), Image.LANCZOS)
    wx = (W - win_w) // 2
    wy = TOP_Y

    canvas = background(W / 2, wy + WIN_H * 0.52).convert("RGBA")

    mask = Image.new("L", (W, H), 0)
    mask.paste(win.getchannel("A"), (wx, wy))

    for blur, spread, off, op in ((110, 8, 60, 0.55), (38, 2, 22, 0.42)):
        a = mask.filter(ImageFilter.MaxFilter(spread * 2 + 1)) if spread else mask
        a = a.filter(ImageFilter.GaussianBlur(blur))
        a = a.point(lambda v, o=op: int(v * o))
        shifted = Image.new("L", (W, H), 0)
        shifted.paste(a, (0, off))
        shade = Image.new("RGBA", (W, H), (2, 8, 18, 255))
        shade.putalpha(shifted)
        canvas = Image.alpha_composite(canvas, shade)

    canvas.alpha_composite(win, (wx, wy))

    hl = Image.new("L", (W, H), 0)
    hl.paste(hairline(win.getchannel("A")), (wx, wy))
    hl = hl.point(lambda v: int(v * 0.30))
    hl_layer = Image.new("RGBA", (W, H), (188, 214, 250, 255))
    hl_layer.putalpha(hl)
    canvas = Image.alpha_composite(canvas, hl_layer)

    d = ImageDraw.Draw(canvas)

    ef = sf(38, "Bold", optical=40)
    tr = 7.5
    ew = tracked(d, 0, 0, eyebrow, ef, None, tr, measure_only=True)
    tracked(d, (W - ew) / 2, 108, eyebrow, ef, (126, 173, 235, 255), tr)

    size = 92
    hf = sf(size, "Semibold", optical=96)
    while d.textlength(headline, font=hf) > 2240 and size > 60:
        size -= 2
        hf = sf(size, "Semibold", optical=96)
    lw = d.textlength(headline, font=hf)
    d.text(((W - lw) / 2, 168), headline, font=hf, fill=(255, 255, 255, 255))
    assert 168 + size * 1.25 < TOP_Y, "headline would collide with the window"

    out = canvas.convert("RGB")
    name = "%02d-%s" % (idx, fname.split("-", 1)[1])
    out.save(os.path.join(OUT, name), "PNG")
    print("wrote %-26s %s  window %dx%d at (%d,%d)" % (name, out.size, win_w, WIN_H, wx, wy))

print("done ->", OUT)
