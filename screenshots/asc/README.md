# App Store Connect screenshots

🚫 **NOT used by the website.** Nothing in `../` or any `.html` references these. They live here
only so they survive: they were captured in a session scratch directory that gets cleaned up, and
**App Store Connect keeps no local copy** - the live listing's screenshots exist only in ASC, so
there is nothing on this Mac to diff them against.

| file | size | where it goes |
|---|---|---|
| `ipad-13-home.png` | 2064 x 2752 | ASC, iPad 13-inch display, portrait |
| `mac-home.png` | 2880 x 1800 | ASC, macOS |
| `mac-home-raw-uncomposed.png` | 2382 x 1788 | not for upload - the raw window capture, kept so the Mac shot can be re-composed on a different background without re-running the capture |

**Captured 2026-08-28**, demo data only, per `../README.md`. The iPad capture is natively an
ASC-legal size and was uploaded unmodified. The Mac window is **2382 x 1788**, which is not an ASC
size, so it was scaled to 1620 tall and centred on a `#F2F4F7` canvas; padding it un-scaled would
have left **6px** top and bottom and read as clipped.

⚠️ **These are iPhone-shaped decisions away from the website set.** The site's gallery is
1206 x 2620 iPhone shots and these cannot substitute for them - different device, different aspect
ratio, and `index.html` hard-codes the iPhone dimensions.

---

## `mac-v2/` — restyled 2026-08-31

**Why:** the original `mac-home.png` treatment (window scaled to 1620 tall, centred on `#F2F4F7`)
was a fix for an illegal ASC image size, not a design. Next to competitors in Mac App Store search
results it read as unfinished. **Apple renders the first screenshot inline in search results, so
that image is the ad unit, not detail-page decoration.**

**Treatment:** deep navy gradient (`#061225` to `#0E2C52`) + radial brand glow + soft vignette;
window at 1732 x 1300 centred, two-layer realistic drop shadow, hairline edge highlight; SF Pro
eyebrow (letterspaced, `#7EADEB`) over a single-line SF Pro Semibold headline in white.

**Rebuild:** `python3 screenshots/asc/build-mac-v2.py` (Pillow + numpy, sources from `mac-raw/`).
Headlines live in the `SHOTS` list. The script asserts the headline cannot collide with the window,
and auto-shrinks type to keep every headline on one line so the set reads as a strip.

**Order is deliberate:** MedXPress leads, not Home. The desktop version's whole argument is that
MedXPress is a desktop form and the autofill now lives where the form does.

⚠️ **Copy constraints these headlines respect:** descriptive only, never a fitness or pass/fail
verdict; no em dashes; "pilots" not "airline pilots"; and **nothing promising which documents a
given diagnosis needs** (that claim was retracted from the CACI screen on 8/12 and must not
reappear in marketing).

🚫 The originals in `mac/` and `mac-raw/` are untouched.
