from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np, os, sys
B   = os.path.expanduser("~/pilot-medical-guardian-content/screenshots")
OUT = "/private/tmp/claude-501/-Users-ryan-pilot-medical-guardian/05b0ba34-5353-4d81-bb37-b09efca5a175/scratchpad/reddit"
S, SF = 1080, "/System/Library/Fonts/SFNS.ttf"
MAC, PHONE = f"{B}/asc/mac-raw/03-medxpress-prep.png", f"{B}/medxpress.png"
WEIGHTS = {"Semibold": 590, "Bold": 700}

def sf(size, weight="Bold", optical=96):
    f = ImageFont.truetype(SF, size)
    try:
        vals = []
        for a in f.get_variation_axes():
            n = a["name"].decode() if isinstance(a["name"], bytes) else a["name"]
            if n == "Optical Size": vals.append(min(max(optical, a["minimum"]), a["maximum"]))
            elif n == "Weight":     vals.append(WEIGHTS.get(weight, 700))
            else:                   vals.append(a["default"])
        f.set_variation_by_axes(vals)
    except Exception: pass
    return f

def bg():
    yv = np.linspace(0.0, 1.0, S)[:, None]
    top = np.array([6, 18, 37], float); bot = np.array([14, 44, 82], float)
    t = yv ** 0.85
    a = top[None, None, :] * (1 - t[:, :, None]) + bot[None, None, :] * t[:, :, None]
    return Image.fromarray(np.repeat(a, S, axis=1).astype("uint8")).convert("RGBA")

def dev(path, w, r):
    im = Image.open(path).convert("RGB"); h = int(im.height * w / im.width)
    im = im.resize((w, h), Image.LANCZOS)
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0,0,w-1,h-1], r, fill=255)
    im = im.convert("RGBA"); im.putalpha(m); return im

def drop(c, im, pos, blur, alpha, dy):
    lay = Image.new("RGBA", c.size, (0,0,0,0))
    lay.paste(Image.new("RGBA", im.size, (0,0,0,255)), (pos[0], pos[1]+dy),
              im.getchannel("A").point(lambda v: int(v*alpha/255)))
    c = Image.alpha_composite(c, lay.filter(ImageFilter.GaussianBlur(blur)))
    c.alpha_composite(im, pos); return c

def build(text, out):
    c = bg(); d = ImageDraw.Draw(c)
    f = sf(62)
    while d.textlength(text, font=f) > S - 130 and f.size > 40:
        f = sf(f.size - 2)
    w = d.textlength(text, font=f)
    d.text(((S - w) / 2, 74), text, font=f, fill=(255, 255, 255, 255))
    c = drop(c, dev(MAC, 900, 18), (90, 218), 30, 180, 18)
    c = drop(c, dev(PHONE, 232, 26), (788, 552), 24, 200, 12)
    c.convert("RGB").save(f"{OUT}/{out}")
    print(f"{out}: '{text}'  font {f.size}px  width {int(w)}")

build("Everything in one place", "reddit-ad-2device-textA.png")
build("Your FAA medical, in one place", "reddit-ad-2device-textB.png")
