from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import numpy as np, os

SRC = os.path.expanduser("~/pilot-medical-guardian-content/screenshots/asc/mac-raw")
OUT = os.path.expanduser("~/pilot-medical-guardian-content/screenshots/asc/email")
W, H = 2000, 1250

def background(gx, gy):
    yv = np.linspace(0.0, 1.0, H)[:, None]
    top = np.array([6, 18, 37], float); bot = np.array([14, 44, 82], float)
    t = yv ** 0.85
    bg = top[None, None, :] * (1 - t[:, :, None]) + bot[None, None, :] * t[:, :, None]
    bg = np.repeat(bg, W, axis=1)
    xx, yy = np.meshgrid(np.arange(W), np.arange(H))
    r = np.sqrt(((xx - gx) / (W * 0.85)) ** 2 + ((yy - gy) / (H * 0.95)) ** 2)
    bg = bg + (np.clip(1.0 - r, 0, 1) ** 2.1)[:, :, None] * np.array([44, 104, 186], float)
    rv = np.sqrt(((xx - W/2) / (W * 0.76)) ** 2 + ((yy - H/2) / (H * 0.80)) ** 2)
    bg = bg * (1.0 - (np.clip(rv - 0.58, 0, 1) ** 1.7)[:, :, None] * 0.5)
    return Image.fromarray(np.clip(bg, 0, 255).astype("uint8"), "RGB")

def rounded(im, radius):
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, im.size[0]-1, im.size[1]-1], radius=radius, fill=255)
    o = im.convert("RGBA"); o.putalpha(m); return o

def hairline(alpha):
    inner = alpha.filter(ImageFilter.MinFilter(5))
    e = np.clip(np.array(alpha, float) - np.array(inner, float), 0, 255).astype("uint8")
    return Image.fromarray(e, "L").filter(ImageFilter.GaussianBlur(0.6))

# back -> front. The front window must stay fully legible; the two behind are depth cues.
# (file, brightness, blur px) - back layers are DEPTH, not content to read
STACK = [("05-health.png", 0.88, 5.5), ("03-medxpress-prep.png", 0.94, 2.6), ("01-home.png", 1.00, 0.0)]
BASE_W = 1120
STEP_X, STEP_Y = 300, 78

canvas = background(W * 0.5, H * 0.52).convert("RGBA")
n = len(STACK)
total_w = BASE_W + STEP_X * (n - 1)
first_h = int(BASE_W / (2382 / 1788))
total_h = first_h + STEP_Y * (n - 1)
x0 = (W - total_w) // 2
y0 = (H - total_h) // 2

for i, (fname, dim, blur_px) in enumerate(STACK):
    src = Image.open(os.path.join(SRC, fname)).convert("RGB")
    w = BASE_W; h = int(w / (src.width / src.height))
    shot = rounded(src.resize((w, h), Image.LANCZOS), 22)
    if dim < 1.0 or blur_px:            # out-of-focus depth, so nobody tries to READ them
        a = shot.getchannel("A")
        rgb = shot.convert("RGB")
        if blur_px: rgb = rgb.filter(ImageFilter.GaussianBlur(blur_px))
        rgb = ImageEnhance.Brightness(rgb).enhance(dim)
        rgb = ImageEnhance.Color(rgb).enhance(0.80)
        shot = rgb.convert("RGBA"); shot.putalpha(a)
    x = x0 + STEP_X * (n - 1 - i); y = y0 + STEP_Y * i

    mask = Image.new("L", (W, H), 0); mask.paste(shot.getchannel("A"), (x, y))
    for blur, spread, off, op in ((92, 7, 52, 0.60), (30, 2, 18, 0.45)):
        a = mask.filter(ImageFilter.MaxFilter(spread*2+1)).filter(ImageFilter.GaussianBlur(blur))
        a = a.point(lambda v, o=op: int(v * o))
        sh = Image.new("L", (W, H), 0); sh.paste(a, (0, off))
        lay = Image.new("RGBA", (W, H), (2, 8, 18, 255)); lay.putalpha(sh)
        canvas = Image.alpha_composite(canvas, lay)

    canvas.alpha_composite(shot, (x, y))

    hl = Image.new("L", (W, H), 0); hl.paste(hairline(shot.getchannel("A")), (x, y))
    hl = hl.point(lambda v: int(v * 0.34))
    lay = Image.new("RGBA", (W, H), (188, 214, 250, 255)); lay.putalpha(hl)
    canvas = Image.alpha_composite(canvas, lay)

os.makedirs(OUT, exist_ok=True)
p = os.path.join(OUT, "mac-email.png")
canvas.convert("RGB").save(p, "PNG", optimize=True)
print("wrote", p, canvas.size, f"{os.path.getsize(p)/1024:.0f} KB")
