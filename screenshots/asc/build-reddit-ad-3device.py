from PIL import Image, ImageDraw, ImageFilter
import numpy as np, os
B   = os.path.expanduser("~/pilot-medical-guardian-content/screenshots")
OUT = "/private/tmp/claude-501/-Users-ryan-pilot-medical-guardian/05b0ba34-5353-4d81-bb37-b09efca5a175/scratchpad/reddit"
S = 1080
MAC   = f"{B}/asc/mac-raw/03-medxpress-prep.png"
IPAD  = f"{B}/asc/ipad/03-medxpress-prep.png"
PHONE = f"{B}/medxpress.png"
for p in (MAC, IPAD, PHONE):
    im = Image.open(p); print(f"{im.size}  {os.path.relpath(p, B)}")

def bg(w, h):
    yv = np.linspace(0.0, 1.0, h)[:, None]
    top = np.array([6, 18, 37], float); bot = np.array([14, 44, 82], float)
    t = yv ** 0.85
    a = top[None, None, :] * (1 - t[:, :, None]) + bot[None, None, :] * t[:, :, None]
    return Image.fromarray(np.repeat(a, w, axis=1).astype("uint8")).convert("RGBA")

def dev(path, w, radius):
    im = Image.open(path).convert("RGB")
    h = int(im.height * w / im.width)
    im = im.resize((w, h), Image.LANCZOS)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w-1, h-1], radius, fill=255)
    im = im.convert("RGBA"); im.putalpha(m)
    return im

def drop(canvas, im, pos, blur=26, alpha=170, dy=14):
    sh = Image.new("RGBA", canvas.size, (0,0,0,0))
    a = im.getchannel("A").point(lambda v: int(v * alpha / 255))
    lay = Image.new("RGBA", canvas.size, (0,0,0,0))
    lay.paste(Image.new("RGBA", im.size, (0,0,0,255)), (pos[0], pos[1]+dy), a)
    sh = Image.alpha_composite(sh, lay).filter(ImageFilter.GaussianBlur(blur))
    canvas = Image.alpha_composite(canvas, sh)
    canvas.alpha_composite(im, pos)
    return canvas

c = bg(S, S)
mac   = dev(MAC,   900, 18)
ipad  = dev(IPAD,  320, 20)
phone = dev(PHONE, 180, 24)
c = drop(c, mac,   ((S-900)//2, 100), blur=30, alpha=180, dy=18)
c = drop(c, ipad,  (75, 640), blur=24, alpha=195, dy=12)
c = drop(c, phone, (825, 665), blur=20, alpha=195, dy=10)
c.convert("RGB").save(f"{OUT}/reddit-ad-3device.png")
print("mac", mac.size, "ipad", ipad.size, "phone", phone.size)
