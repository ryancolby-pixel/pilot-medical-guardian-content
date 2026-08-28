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
