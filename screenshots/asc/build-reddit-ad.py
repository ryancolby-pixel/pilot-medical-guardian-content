from PIL import Image, ImageDraw, ImageFilter
import numpy as np, os

SRC = os.path.expanduser("~/pilot-medical-guardian-content/screenshots/asc/iphone-69-v2/01-medxpress.png")
OUT = "/private/tmp/claude-501/-Users-ryan-pilot-medical-guardian/05b0ba34-5353-4d81-bb37-b09efca5a175/scratchpad/reddit"
S = 1080

def bg(w, h):
    yv = np.linspace(0.0, 1.0, h)[:, None]
    top = np.array([6, 18, 37], float); bot = np.array([14, 44, 82], float)
    t = yv ** 0.85
    a = top[None, None, :] * (1 - t[:, :, None]) + bot[None, None, :] * t[:, :, None]
    return Image.fromarray(np.repeat(a, w, axis=1).astype("uint8"))

src = Image.open(SRC).convert("RGB")
crop = src.crop((145, 1380, 1145, 2560))          # Item 17 through the Item 18 card, deeper
target_w = 900
card = crop.resize((target_w, int(crop.height * target_w / crop.width)), Image.LANCZOS)

x, top = (S - target_w) // 2, 126
# round the TOP corners only; let the card bleed off the bottom edge so it reads as deliberate
mask = Image.new("L", card.size, 0)
d = ImageDraw.Draw(mask)
d.rounded_rectangle([0, 0, card.width - 1, card.height - 1], 28, fill=255)
d.rectangle([0, card.height - 60, card.width, card.height], fill=255)
card.putalpha(mask)

canvas = bg(S, S).convert("RGBA")
sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(sh).rounded_rectangle([x, top + 16, x + target_w, S + 40], 28, fill=(0, 0, 0, 160))
canvas = Image.alpha_composite(canvas, sh.filter(ImageFilter.GaussianBlur(28)))
canvas.alpha_composite(card, (x, top))
canvas.convert("RGB").save(f"{OUT}/reddit-ad-1080.png")
print("crop", crop.size, "-> card", card.size, "at", (x, top), "| bleeds", card.height + top - S, "px past bottom")
