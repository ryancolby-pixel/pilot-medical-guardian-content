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

## Step by step (recommended device: iOS Simulator)

**Use the iOS Simulator (iPhone 16 Pro), not your real iPhone.** Two reasons: a
clean status bar (always 9:41, full signal/battery — looks professional), and
**zero risk of your real medical data landing in a public screenshot.** (On a
real device you'd have to erase your actual records to avoid showing real
conditions/meds — don't.)

**One-time setup**
1. Open the app project in Xcode.
2. In the toolbar run-destination menu (top, next to the scheme), choose
   **iPhone 16 Pro** (a Simulator, not your iPad).
3. Press **⌘R**; wait for the Simulator to boot and the app to launch.
4. Set Light mode: Simulator menu bar → **Features → Toggle Appearance** until
   light (or in the simulated phone, Settings → Display & Brightness → Light).
5. If any data exists, open **About (ⓘ) → Erase All Data**.
6. Run onboarding with demo info — name "Demo Pilot" (or blank), any DOB, Class 1.
- **Screenshot key:** with the Simulator focused, press **⌘S** (or menu →
  File → Save Screen). PNG lands on your Desktop.

**`home.png`** — My Medical tab → add a certificate (Class 1, exam date ~7 months
ago so the countdown shows a healthy ~150 days, not expired/red) → tap Home tab → ⌘S.

**`medxpress.png`** — My Records → Medications → add "Lisinopril" 10mg once daily
+ "Vitamin D". My Records → Doctor Visits → add "Dr. Smith", Family Medicine,
recent date, reason "Annual physical". My Records → MedXPress Prep → ⌘S.

**`si.png`** — Special Issuance tab → Add a condition → Hypertension. (Optional:
set a reminder on one item, mark one document submitted.) Open the Hypertension
detail → ⌘S.

**`health.png`** — Health tab → Add a reading → Blood Pressure → add 3 readings on
different dates (e.g. 118/78, 121/80, 119/79). Tap Blood Pressure to expand its
chart (orange dashed 155 mmHg line + citation appear) → ⌘S.

**`documents.png`** (the My Documents shot — leans on the docs + Share-with-AME
workflow) — My Records → **My Documents**. Tap **+** and add 3 sample documents so
the list + the blue **"Share with my AME"** button + a **"General · 3"** section all
show. **Use only benign, non-real samples — the row title AND the thumbnail both
render, so import placeholder PDFs, never a real document:**
- "SI Authorization Letter" → type **Authorization Letter**
- "Lipid panel results" → type **Test Result**
- "Cardiology clearance letter" → type **Physician Letter**
Then ⌘S. **Hard no's (from the privacy audit):** no oncology/PET/CT/MRI terms, no
real meds/providers/AME names, no "YellowArc"/Virginia/LLC references, no raw
`Screenshot YYYY-MM-DD at H.MM.SS` filenames. (A clean Simulator capture with these
samples needs no scrubbing.) **Then:** rename to `documents.png`, drop it in this
folder, and uncomment the `<figure>` in `index.html` (the `<!-- TODO: ... documents.png -->`
block in the "A look inside the app" rail).

**Finish** — rename the 4 Desktop PNGs to `home.png` / `medxpress.png` / `si.png`
/ `health.png`, move them into this folder, then uncomment the gallery in
`index.html` (delete the `<!--` and `-->` lines around "See it in action").

## Autofill before/after shots (live MedXPress form)

These four show the Safari extension autofilling the **live** `medxpress.faa.gov`
form — the headline feature. **This can't be done in the Simulator** (it needs the
extension running against the real, logged-in FAA form), so it requires a **real
iPad or iPhone**. That removes the Simulator's clean-room safety, so:

- **Seed DEMO data first.** The autofill types whatever's in the app, so add fake
  records (or erase your real ones) before capturing — e.g. one med
  (`Omeprazole 40 mg once daily`) and a couple visits (`Dr. Lee` / `Jordan Avery, FNP`,
  generic addresses). Never your real meds, providers, or addresses.
- **Frame to Item 17 or 19 only.** You're logged into your real FAA account, so keep
  the account header + demographics (Items 1–16: your name, airman number, address)
  **out of frame.**
- **Capture two states per item:** *before* (blank form with the "Fill from Pilot
  Medical Guardian" button) and *after* (panel open + fields filled).
- **Hand the raw PNGs to Claude for a PII pass.** Claude crops the iOS status bar
  (time/battery) while keeping the `medxpress.faa.gov` URL pill, swaps any real
  data to demo values, and web-optimizes. **Raw originals stay local — only the
  scrubbed `medxpress-*` versions go in git.**
- **Accuracy:** only Items **17 & 19** autofill — never show or imply Item 18
  autofilling (Akamai blocks bulk fill there; it's a reference-card path).

| File | Page | What to show |
|------|------|--------------|
| `medxpress-autofill-before.png` | MedXPress Item 17 | Blank medication form + the floating "Fill from Pilot Medical Guardian" button |
| `medxpress-autofill-after.png`  | MedXPress Item 17 | Panel open + a demo medication filled into the fields, verify-accuracy note visible |
| `medxpress-visit-before.png`    | MedXPress Item 19 | Blank doctor-visits form |
| `medxpress-visit-after.png`     | MedXPress Item 19 | Panel open + a demo visit filled in (provider, date, full address) |

**Live layout (2026-06-03):** to keep the home page short and legible on phones, the
site shows only the **two cropped "after" shots** (form + panel, FAA chrome trimmed)
as **tap-to-enlarge** figures — not the full four-image before/after set. The two
`-before` shots stay here for an optional before/after layout later. When recapturing,
the `-after` files are stored already cropped tight to the form + autofill panel.

## Keep in sync as features change

**Screenshots are versioned content, not set-and-forget.** When a build changes,
redesigns, or removes a feature shown here, update or remove the affected shot in
the same pass — a public screenshot of a screen that no longer matches the app is
a credibility (and, for medical copy, an accuracy) problem.

Current shot → feature mapping:
- `home.png` → Home renewal countdown
- `medxpress.png` → MedXPress Prep (Items 17/19, in-app)
- `si.png` → Special Issuance checklist
- `health.png` → Health metric vs FAA threshold (Blood Pressure)
- `documents.png` → My Documents library + Share-with-AME (Build 20)
- `medxpress-autofill-before.png` / `medxpress-autofill-after.png` → Safari extension autofilling MedXPress Item 17 (live form)
- `medxpress-visit-before.png` / `medxpress-visit-after.png` → Safari extension autofilling MedXPress Item 19 (live form)

If a feature in a shot is removed from the app, remove that shot **and** its
`<figure>` block from `index.html`. If a shot's screen is redesigned, recapture it.
