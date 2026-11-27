"""Homepage hero: Mac + iPad + iPhone on the Home screen (same day, same demo data, same countdown).
Sources: screenshots/hero-raw/*.png (captured 2026-11-27 from iOS 2.5.1 / Mac 1.4.1, 246 days on all three).
Output: screenshots/devices-home.webp (2400x1350, transparent) and -800/-1200/-1600 resizes, used by index.html's hero srcset. Run from the repo root."""
from PIL import Image, ImageDraw, ImageFilter
import numpy as np, os

R = "screenshots/hero-raw"
W, H = 2400, 1350
BASE = 1250  # shared bottom line for the iPad and iPhone

def bg():
    yv = np.linspace(0.0, 1.0, H)[:, None]
    top = np.array([246, 248, 251], float); bot = np.array([232, 238, 246], float)
    a = top[None, None, :] * (1 - yv[:, :, None]) + bot[None, None, :] * yv[:, :, None]
    return Image.fromarray(np.repeat(a, W, axis=1).astype("uint8")).convert("RGBA")

def rounded(im, radius):
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius, fill=255)
    im = im.convert("RGBA"); im.putalpha(m); return im

def screen(path, w):
    im = Image.open(path).convert("RGB")
    return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)

def framed(path, w, bezel, r_out, r_in):
    s = rounded(screen(path, w), r_in)
    body = Image.new("RGBA", (s.width + 2 * bezel, s.height + 2 * bezel), (0, 0, 0, 0))
    ImageDraw.Draw(body).rounded_rectangle([0, 0, body.width - 1, body.height - 1], r_out, fill=(22, 24, 28, 255))
    ImageDraw.Draw(body).rounded_rectangle([2, 2, body.width - 3, body.height - 3], r_out - 2, outline=(70, 74, 82, 255), width=2)
    body.alpha_composite(s, (bezel, bezel))
    return body

def place(canvas, im, pos, blur=34, alpha=95, dy=22):
    lay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    a = im.getchannel("A").point(lambda v: int(v * alpha / 255))
    lay.paste(Image.new("RGBA", im.size, (16, 22, 34, 255)), (pos[0], pos[1] + dy), a)
    canvas = Image.alpha_composite(canvas, lay.filter(ImageFilter.GaussianBlur(blur)))
    canvas.alpha_composite(im, pos)
    return canvas

c = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # transparent (11/27): the devices float on the hero band in light and dark
mac = rounded(screen(f"{R}/mac-home.png", 1240), 20)
c = place(c, mac, (70, (H - mac.height) // 2 - 20))
ipad = framed(f"{R}/ipad-home.png", 560, 20, 46, 28)
c = place(c, ipad, (1235, BASE - ipad.height))
phone = framed(f"{R}/iphone-home.png", 380, 15, 72, 58)
c = place(c, phone, (1895, BASE - phone.height + 10))
c.save("screenshots/devices-home.webp", "WEBP", quality=88, method=6)
for w in (800, 1200, 1600):  # srcset sizes; index.html lists these plus the 2400w original
    c.resize((w, round(H * w / W)), Image.LANCZOS).save(f"screenshots/devices-home-{w}.webp", "WEBP", quality=88, method=6)
c.convert("RGB").save(os.path.join(os.environ.get("TMPDIR", "/tmp"), "devices-home-check.jpg"), quality=80)
print("wrote screenshots/devices-home.webp (+800/1200/1600)", c.size)
