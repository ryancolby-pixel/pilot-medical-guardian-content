from PIL import Image, ImageDraw, ImageFilter
import numpy as np, os
ICON = os.path.expanduser("~/pilot-medical-guardian/PilotMedicalGuardian/PilotMedicalGuardian/Assets.xcassets/AppIcon.appiconset/AppIcon.png")
OUT  = "/private/tmp/claude-501/-Users-ryan-pilot-medical-guardian/05b0ba34-5353-4d81-bb37-b09efca5a175/scratchpad/reddit"
S = 1080

yv = np.linspace(0.0, 1.0, S)[:, None]
top = np.array([6, 18, 37], float); bot = np.array([14, 44, 82], float)
t = yv ** 0.85
a = top[None, None, :] * (1 - t[:, :, None]) + bot[None, None, :] * t[:, :, None]
c = Image.fromarray(np.repeat(a, S, axis=1).astype("uint8")).convert("RGBA")

D = 620                                        # icon fills ~57% -> still reads at 70px
ic = Image.open(ICON).convert("RGB").resize((D, D), Image.LANCZOS)
m = Image.new("L", (D, D), 0)
ImageDraw.Draw(m).rounded_rectangle([0, 0, D-1, D-1], int(D * 0.2237), fill=255)  # iOS squircle-ish
ic = ic.convert("RGBA"); ic.putalpha(m)
x = y = (S - D) // 2

sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
sh.paste(Image.new("RGBA", (D, D), (0, 0, 0, 190)), (x, y + 26), m)
c = Image.alpha_composite(c, sh.filter(ImageFilter.GaussianBlur(34)))
c.alpha_composite(ic, (x, y))
c.convert("RGB").save(f"{OUT}/reddit-ad-thumb.png")
print("thumb 1080x1080, icon", D, "at", (x, y))
