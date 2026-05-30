# Website screenshots — capture spec

Drop four portrait iPhone PNGs in **this folder**, then enable the gallery in
`index.html` (delete the `<!--` / `-->` lines around the "See it in action"
section). Until the files exist, the section stays commented out so the live
site never shows broken images.

## Settings — identical across all four
- **Device:** one iPhone, **portrait**. Cleanest: iOS Simulator (iPhone 16 Pro)
  for a clean status bar. A real iPhone is fine too.
- **Appearance:** **Light mode** (recommended). Pick one and use it for all four.
- **Capture:** Simulator `⌘S` (saves to Desktop) or device Side + Volume Up.
- **Format:** full-screen PNG, no crop required.
- **Privacy on every shot:** demo data only — no real name, no real provider, no
  condition tied to a real person, and **no red sync-error banner** in frame.

Tip: **About → Erase All Data** first, run onboarding with a demo profile, then
seed only what each shot needs so no real data sneaks in.

## The four files

| File | Screen | What to show |
|------|--------|--------------|
| `home.png` | Home tab | Renewal countdown reading healthy (demo exam date ~3-4 months out so it shows e.g. "expires in 130 days"), "What's next" card, green freshness chip. |
| `medxpress.png` | My Records → MedXPress Prep | A couple demo meds (e.g. Lisinopril 10mg, Vitamin D) + 1-2 demo visits (e.g. "Dr. Smith, Family Medicine"), showing the organized Item 17/19 sections + readiness summary. |
| `si.png` | Special Issuance → a demo SI detail | Use **Hypertension** as the demo condition (common, non-stigmatizing). Show the requirements checklist with a few items, a reminder set, and the "X of Y submitted to FAA" line. |
| `health.png` | Health tab | Expand **Blood Pressure** — it draws the orange dashed FAA threshold line (155 mmHg) + the citation footer. Enter a few demo readings comfortably below the line. |

Set covers: orientation → headline autofill → Special Issuance → data
credibility. Doing only three? Drop `health.png` and remove its `<figure>` block.
