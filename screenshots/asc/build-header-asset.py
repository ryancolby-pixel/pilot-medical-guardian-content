"""App Store product page header + search results asset (one universal image).

Ryan 2026-10-06. One still on the app blue, the countdown as the picture, one marketing line.
Canvas and safe area come from Apple's universal template
(creative_assets-universal_asset_template-static.psd): 5244 x 2950, and the "Art Safe Area"
layer is x 1922-3322, y 660-1620 (1400 x 960). Everything that has to be seen sits inside it;
outside it is plain blue bleed that some placements show and some crop.

Phone source: header/home-267-raw.png, a fresh iPhone 17 Pro capture (2026-10-06) with the demo
certificate set to expire Jun 30, 2027 (267 days that day), the demo Special Issuance
authorization moved past it (otherwise it caps the countdown and adds an SI line), and the
pilot on the medical pathway only (no BasicMed cards). The seeder edits were local and reverted.
The phone fades out under the MedXPress prep card so "What's next" (an SI item) never shows.

Copy is exact and nothing else may be added: the number, "Days remaining", "Class 1 medical",
"expires Jun 30, 2027", "MedXPress, filled from your own records." No price, URL, FAA approval
or fit-to-fly wording, no second feature, no em dashes.
"""
from PIL import Image, ImageDraw
import numpy as np, os


BASE = os.path.expanduser("~/pilot-medical-guardian-content/screenshots/asc/header")
SF = "/System/Library/Fonts/SFNS.ttf"
W, H = 5244, 2950
SX0, SY0, SX1, SY1 = 1922, 660, 3322, 1620          # Apple's art safe area
BLUE = (0x1C, 0x66, 0xD9)
WHITE = (255, 255, 255)


def font(size, weight):
    from PIL import ImageFont
    f = ImageFont.truetype(SF, size)
    vals = []
    for a in f.get_variation_axes():
        n = a["name"].decode() if isinstance(a["name"], bytes) else a["name"]
        vals.append({"Weight": weight, "Optical Size": min(max(96, a["minimum"]), a["maximum"])}.get(n, a["default"]))
    f.set_variation_by_axes(vals)
    return f


def phone(screen, scale):
    """Frame a raw capture as an iPhone: rounded screen in a graphite bezel."""
    sw, sh = int(screen.width * scale), int(screen.height * scale)
    scr = screen.resize((sw, sh), Image.LANCZOS).convert("RGBA")
    r_screen = int(165 * scale)                     # iPhone 17 Pro display corner, 55pt @3x
    m = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, sw - 1, sh - 1], radius=r_screen, fill=255)
    scr.putalpha(m)
    bz = max(10, int(42 * scale))                   # bezel width
    ow, oh = sw + 2 * bz, sh + 2 * bz
    body = Image.new("RGBA", (ow, oh), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    d.rounded_rectangle([0, 0, ow - 1, oh - 1], radius=r_screen + bz, fill=(24, 26, 31, 255))
    d.rounded_rectangle([3, 3, ow - 4, oh - 4], radius=r_screen + bz - 3, outline=(92, 98, 108, 255), width=3)
    body.alpha_composite(scr, (bz, bz))
    return body, bz


def main():
    raw = Image.open(os.path.join(BASE, "home-267-raw.png")).convert("RGB")
    canvas = Image.new("RGB", (W, H), BLUE)

    # ---- phone: screen top just inside the safe area; MedXPress card ends above the line ----
    card_bottom_raw = 1846                           # bottom of the MedXPress prep card in the raw
    screen_top, card_bottom_at = 700, 1430
    scale = (card_bottom_at - screen_top) / card_bottom_raw
    body, bz = phone(raw, scale)
    px = SX1 - body.width - 40
    py = screen_top - bz
    # fade the phone into the blue just under the card so nothing below it can show
    fade0, fade1 = card_bottom_at + 2 - py, card_bottom_at + 14 - py
    a = np.array(body.getchannel("A"), dtype=np.float32)
    ramp = np.ones(body.height, dtype=np.float32)
    ramp[int(fade0):] = np.clip(1 - (np.arange(int(fade0), body.height) - fade0) / (fade1 - fade0), 0, 1)
    body.putalpha(Image.fromarray((a * ramp[:, None]).astype("uint8")))
    canvas.paste(body, (px, py), body)

    # ---- type: the countdown is the picture ----
    d = ImageDraw.Draw(canvas)
    x = SX0 + 70
    big = font(360, 700)
    top = SY0 + 40
    d.text((x - 12, top), "267", font=big, fill=WHITE)
    y = top + big.getbbox("267")[3] + 30
    for text, size, weight, gap in (("Days remaining", 76, 600, 28),
                                    ("Class 1 medical", 60, 440, 14),
                                    ("expires Jun 30, 2027", 60, 440, 0)):
        f = font(size, weight)
        d.text((x, y), text, font=f, fill=WHITE)
        y += f.getbbox(text)[3] + gap

    line = "MedXPress, filled from your own records."
    lf = font(58, 600)
    d.text((x, SY1 - 48 - lf.getbbox(line)[3]), line, font=lf, fill=WHITE)
    assert d.textlength(line, font=lf) + x <= SX1, "line overruns the safe area"

    out = os.path.join(BASE, "pmg-universal-5244x2950.png")
    canvas.save(out, optimize=True)
    print("wrote", out, canvas.size)
    return canvas


if __name__ == "__main__":
    main()
