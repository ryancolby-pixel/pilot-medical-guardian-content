# LinkedIn company-page cover, 1128x191. Spec: Ryan 2026-09-06.
#   Solid navy (same ramp as build-reddit-ad-poster.py), iPhone Home with the 130 on the
#   right, left kept empty so LinkedIn's logo tile can sit on it.
#   NO jet photo. NO second device. NO "Download now". NO second logo on the left.
#
# 🚨 TWO NUMBERS HERE WERE MEASURED, NOT GUESSED, AND BOTH WERE WRONG WHEN GUESSED:
#   LOGO_RIGHT — the page's logo tile runs to x=318 of 1128, NOT the ~200 first assumed.
#                Text at x=240 rendered directly underneath it and was unreadable.
#                Measured off the live page, scaling the rendered banner back to 1128.
#   CARD_TOP/BOT — the countdown card sits at 0.370-0.501 of the source image height.
#                First estimated at ~0.353 and the 130 clipped off the bottom edge.
#                Found by scanning the source for the card's light-blue pixel rows.
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np, os

W, H       = 1128, 191
LOGO_RIGHT = 318          # measured; text must start clear of this
CARD_TOP, CARD_BOT = 0.370, 0.501
CARD_H     = 70           # how tall the countdown card renders in the band
SRC  = os.path.expanduser("~/pilot-medical-guardian-content/screenshots/iphone-new/home.png")
OUT  = os.path.expanduser("~/pilot-medical-guardian-content/screenshots/asc/linkedin")
TXT  = "Your FAA medical, in one place"     # same line as the Reddit poster
SFP  = "/System/Library/Fonts/SFNS.ttf"
WT   = {"Regular":400,"Medium":510,"Semibold":590,"Bold":700}

def sf(s, w="Bold", o=96):
    f = ImageFont.truetype(SFP, s)
    try:
        v = []
        for a in f.get_variation_axes():
            n = a["name"].decode() if isinstance(a["name"], bytes) else a["name"]
            if   n == "Optical Size": v.append(min(max(o, a["minimum"]), a["maximum"]))
            elif n == "Weight":       v.append(WT.get(w, 700))
            else:                     v.append(a["default"])
        f.set_variation_by_axes(v)
    except Exception: pass
    return f

def bg():                                    # identical ramp to the Reddit poster
    yv = np.linspace(0, 1, H)[:, None]; t = yv ** 0.85
    a = (np.array([6,18,37], float)[None,None,:] * (1-t[:,:,None])
       + np.array([14,44,82], float)[None,None,:] * t[:,:,None])
    return Image.fromarray(np.repeat(a, W, axis=1).astype("uint8")).convert("RGBA")

def rounded(im, r):
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0,0,im.size[0]-1,im.size[1]-1], r, fill=255)
    im = im.convert("RGBA"); im.putalpha(m); return im

src   = Image.open(SRC).convert("RGB")
sc    = CARD_H / ((CARD_BOT - CARD_TOP) * src.height)
PW,PH = int(src.width*sc), int(src.height*sc)
phone = rounded(src.resize((PW,PH), Image.LANCZOS), int(58*sc))
py    = -154                                  # pushes the app title fully off the top edge,
                                              # which also removes the redundant second logo
px    = W - PW - 44
TEXT_X = LOGO_RIGHT + 34
GAP    = px - 24 - TEXT_X

size = 36
while size > 18:
    if ImageDraw.Draw(Image.new("RGB",(10,10))).textbbox((0,0), TXT, font=sf(size,"Semibold",64))[2] <= GAP:
        break
    size -= 1

def build(headline, name):
    img = bg()
    sh = Image.new("RGBA", (PW+56, PH+56), (0,0,0,0))
    ImageDraw.Draw(sh).rounded_rectangle([28,28,PW+27,PH+27], int(58*sc), fill=(0,0,0,130))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)), (px-28, py-28+10))
    img.alpha_composite(phone, (px, py))
    if headline:
        d = ImageDraw.Draw(img); f = sf(size, "Semibold", 64)
        bb = d.textbbox((0,0), headline, font=f)
        d.text((TEXT_X, (H-(bb[3]-bb[1]))//2 - bb[1]), headline, font=f, fill=(255,255,255))
    os.makedirs(OUT, exist_ok=True)
    p = f"{OUT}/{name}.png"; img.convert("RGB").save(p); print("  ", p)

print(f"  logo clears x={LOGO_RIGHT} | text {TEXT_X}..{TEXT_X+GAP} at {size}px | device x={px}")
build(None, "banner-A-phone-only")
build(TXT,  "banner-B-headline")
