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

10/7 (Ryan): the MedXPress line moved from the safe area's bottom edge to directly under "expires Jun 30, 2027",
one line, in the text column beside the phone.

Copy is exact and nothing else may be added: the number, "Days remaining", "Class 1 medical",
"expires Jun 30, 2027", "MedXPress, filled from your own records." No price, URL, FAA approval
or fit-to-fly wording, no second feature, no em dashes.
"""
from PIL import Image, ImageDraw
import numpy as np, os


BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "header")  # this checkout, never a hard-coded one
SF = "/System/Library/Fonts/SFNS.ttf"
W, H = 5244, 2950
SX0, SY0, SX1, SY1 = 1922, 660, 3322, 1620          # Apple's art safe area
BLUE = (0x1C, 0x66, 0xD9)
WHITE = (255, 255, 255)

# 2026-11-13 re-capture for iOS 2.4.0: Home lost its logo, so the 10/06 raw no longer matched the app.
# iPhone 17 sim (same 1206x2622 as the 17 Pro), demo data, certificate-only pathway chosen on My
# Medical (no seeder edit this time), 9:41. The number and date are the ones the captured screen
# shows that day; they must always match the phone in the picture.
RAW = "home-260-raw.png"           # 10/06 source kept beside it: home-267-raw.png
CARD_BOTTOM_RAW = 1509             # bottom of the MedXPress prep card in RAW (10/06 raw: 1846)
PHONE_SCALE = (1430 - 700) / 1846  # the 10/06 phone size, so the text column keeps its width
DAYS, EXPIRES = "260", "expires Jul 31, 2027"


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
    raw = Image.open(os.path.join(BASE, RAW)).convert("RGB")
    canvas = Image.new("RGB", (W, H), BLUE)

    # ---- phone: screen top just inside the safe area; MedXPress card ends above the line ----
    screen_top = 700
    scale = PHONE_SCALE                              # same phone size as the 10/06 asset
    card_bottom_at = screen_top + round(CARD_BOTTOM_RAW * scale)
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
    d.text((x - 12, top), DAYS, font=big, fill=WHITE)
    y = top + big.getbbox(DAYS)[3] + 30
    for text, size, weight, gap in (("Days remaining", 76, 600, 28),
                                    ("Class 1 medical", 60, 440, 14),
                                    (EXPIRES, 60, 440, 0)):
        f = font(size, weight)
        d.text((x, y), text, font=f, fill=WHITE)
        y += f.getbbox(text)[3] + gap

    # Ryan 2026-10-07: "Put it directly under 'expires Jun 30, 2027,' still small, still one line. The phone stays
    # on the right." It sat on the safe area's bottom edge, under the phone, where a tight crop loses it. It now
    # sits in the text column, so it must fit between the column's left edge and the phone: the largest size up to
    # the old 58 that does.
    line = "MedXPress, filled from your own records."
    limit = px - 60 - x                              # stop short of the phone's bezel
    size = 58
    while d.textlength(line, font=font(size, 600)) > limit:
        size -= 1
    lf = font(size, 600)
    y += 36
    d.text((x, y), line, font=lf, fill=WHITE)
    assert d.textlength(line, font=lf) <= limit, "line runs into the phone"
    assert y + lf.getbbox(line)[3] <= SY1, "line falls below the safe area"
    print("MedXPress line:", size, "px at y", y, "width", round(d.textlength(line, font=lf)), "of", limit)

    out = os.path.join(BASE, "pmg-universal-5244x2950.png")
    canvas.save(out, optimize=True)
    print("wrote", out, canvas.size)
    return canvas


if __name__ == "__main__":
    main()
