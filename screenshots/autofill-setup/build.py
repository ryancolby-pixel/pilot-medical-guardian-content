"""Build the still screenshots on autofill.html (Ryan 2026-10-18: "Also make sure any screenshots on the website
are updated. If there are no screenshots, maybe those should be added in?").

Raws (in raw/) are simulator captures on iOS 26.5, the version the page's setup video shows and the one the first
pilot to get stuck on the old instructions was running (iPadOS 26.7.1): an iPhone 17e with the status bar pinned to
9:41, and an iPad (A16). The extension is the shipping one (manifest name "Pilot Medical Guardian Autofill").

Each output is a crop of one real screen with one red mark on the control the step names. Nothing is redrawn.
Re-capture when Safari moves these controls again; the page text names the same controls.
"""
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.dirname(HERE)  # screenshots/
RED = (255, 59, 48)


def ring(im, box, width, radius=None):
    d = ImageDraw.Draw(im)
    if radius is None:
        d.ellipse(box, outline=RED, width=width)
    else:
        d.rounded_rectangle(box, radius=radius, outline=RED, width=width)


def save(im, name, width):
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(os.path.join(OUT, name + ".webp"), "WEBP", quality=88, method=6)
    print(name, im.size)


# 1. Settings > Apps > Safari > Extensions > Pilot Medical Guardian Autofill: the Allow Extension switch.
im = Image.open(os.path.join(RAW, "iphone-extension-settings.png")).convert("RGB")
ring(im, (870, 1150, 1100, 1275), 9, radius=62)
save(im.crop((0, 120, 1170, 1470)), "autofill-ios-allow-extension", 760)

# 2. iPhone: the extensions button at the left end of the address bar, then its menu.
im = Image.open(os.path.join(RAW, "iphone-address-bar.png")).convert("RGB")
ring(im, (262, 2290, 418, 2428), 9)
save(im.crop((0, 2236, 1170, 2480)), "autofill-iphone-extensions-button", 760)

im = Image.open(os.path.join(RAW, "iphone-extensions-menu.png")).convert("RGB")
ring(im, (120, 1950, 1110, 2095), 9, radius=40)
save(im.crop((0, 1560, 1170, 2532)), "autofill-iphone-extensions-menu", 760)

# 3. iPad: the puzzle piece at the right end of the address bar, and its menu.
im = Image.open(os.path.join(RAW, "ipad-extensions-menu.png")).convert("RGB")
ring(im, (1004, 52, 1120, 166), 7)
ring(im, (740, 212, 1418, 312), 7, radius=30)
save(im.crop((440, 40, 1460, 560)), "autofill-ipad-extensions-menu", 760)

# 4. The allow pop-up (iPhone; the iPad sheet has the same three buttons in the same order).
# Cut to the sheet itself (bounds measured off the raw: x 105-1064, y 673-1897), transparent outside its corners, so
# no page text shows around it.
im = Image.open(os.path.join(RAW, "iphone-allow-sheet.png")).convert("RGB")
ring(im, (150, 1540, 1020, 1690), 9, radius=75)
sheet = im.crop((105, 673, 1065, 1898)).convert("RGBA")
mask = Image.new("L", sheet.size, 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, sheet.width - 1, sheet.height - 1), radius=105, fill=255)
sheet.putalpha(mask)
save(sheet, "autofill-ios-always-allow", 600)
