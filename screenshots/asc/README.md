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

**Order:** ~~MedXPress leads, not Home~~ - **superseded 2026-09-05 by Ryan's order** (below). The
old rationale (MedXPress is a desktop form, so the desktop set should lead with it) is recorded here
because it was a real argument, not an oversight; it lost to reading the same story on every device.

⚠️ **Copy constraints these headlines respect:** descriptive only, never a fitness or pass/fail
verdict; no em dashes; "pilots" not "airline pilots"; and **nothing promising which documents a
given diagnosis needs** (that claim was retracted from the CACI screen on 8/12 and must not
reappear in marketing).

🚫 The originals in `mac/` and `mac-raw/` are untouched.

## `ipad-v2/` (8) and `iphone-v2/` (7) — 2026-08-31

Same design system as `mac-v2`, so all three platforms match: navy gradient, radial glow, vignette,
two-layer shadow, hairline edge, SF Pro eyebrow over a Semibold headline.

| set | canvas | sources |
|---|---|---|
| `ipad-v2/` | 2064 x 2752 | `asc/ipad/` (already an ASC-legal size) |
| `iphone-v2/` | **1290 x 2796** | `../*.png`, the 1206 x 2620 website set |

⚠️ **The iPhone website captures are 1206 x 2620, which is NOT an ASC-legal size.** They are composed
onto a 1290 x 2796 canvas rather than uploaded directly.
⚠️ **Screen captures have square corners; real devices do not.** Both mobile sets get their corners
rounded before compositing (iPad 92px, iPhone 116px) or the shot reads as a flat rectangle.
🚨 **Device geometry is locked per set to the worst-case headline height** (`fixed_lines`), so one
short headline cannot make its device render larger than the rest. That defect shipped in the first
pass: `07-documents` came out 1056x2296 while the other six were 1017x2210.

**Rebuild:** `python3 screenshots/asc/build-mobile-v2.py`. Same copy constraints as `mac-v2`.

## 2026-08-31 (second pass) — sizes corrected, dead space measured, stale files guarded

🚨 **THE FIRST iPhone SET WAS THE WRONG SIZE.** Built at `1290 x 2796` (iPhone **6.9"**), but the
listing's slot is iPhone **6.5"**, which ASC states must be `1242x2688 / 2688x1242 / 1284x2778 /
2778x1284`. ⇒ **`iphone-v2/` is now `1284 x 2778`**, and **`iphone-69-v2/` keeps `1290 x 2796`** for
the 6.9" slot. **Check which slot ASC is showing before uploading; the error names the sizes.**

📏 **Dead space was MEASURED, not eyeballed.** A first metric counted near-white pixels and was
useless, because a text screen on a white background scores 90%. The working metric is **ink extent**:
the fraction of the frame beyond the last row/column containing local contrast.
- **Trailing right band: 3-10% everywhere. There is no right-side dead space.**
- **Bottom band: `ipad/04-health.png` is 49% empty. Everything else is 5-8%** (normal chrome).
⇒ **`04-health` DROPPED** (its `05-health-bp` sibling shows the same screen populated at 5.8%).
⇒ Fixed safe bottom crops applied: **Mac 6%** (min measured 6.2%), **iPad 5%** (min measured 5.2%).
✅ Verified the Mac crop does **not** cut the "information and record-keeping tool, not medical
advice" line off Home, which sits above the last ink row.

📐 Devices enlarged in frame: Mac window **1732x1300 -> 2019x1424** (side margin 574 -> 430),
iPad **1614x2152 -> 1771x2243**.

🚨 **BOTH SCRIPTS NOW WIPE THEIR OUTPUT DIRECTORY FIRST.** Reordering the set (MedXPress moved to
lead) renamed files, and the old names survived: `mac-v2` held **9** files for a 7-shot set, `ipad-v2`
held **10**, each with a duplicate `01-home`/`02-medxpress-prep` pair from the pre-reorder run **and a
dropped shot still sitting there**. A directory listing looked fine at a glance and would have
uploaded a duplicated set. **A rename is a delete plus a create, and only the create had been running.**

---

## 2026-09-05 - ONE ORDER ON ALL FOUR SETS, AND TWO iPAD SHOTS RE-CAPTURED

**Order set by Ryan:** Home, MedXPress Prep, Item 18, Special Issuance, then certificate / Health /
FAA Reference. **All four sets are now the same seven shots in the same order with the same
headlines**, so a pilot comparing iPhone to iPad to Mac on the listing reads one story rather than
three. `mac-v2/` and the two iPhone sets were re-ordered first; `ipad-v2/` followed.

**`08-share-with-ame` dropped from the iPad set** to match the other three. Nothing is wrong with the
shot; it is the odd one out, and the raw is still in `ipad/`.

🚨 **THE iPAD RAWS WERE CAPTURED FROM THE WRONG PRESENTATION, AND ONLY LOOKING AT THEM CAUGHT IT.**
On iPad, reaching MedXPress Prep or Item 18 **from the Home card** presents a **form sheet**: a small
centred panel over a dimmed Home, roughly a third of the frame. Reaching the same screens from the
**My Records sidebar item** pushes them **full-width**. Same screens, same build, same data - one
renders legibly at listing size and the other does not, and the two most important slots after Home
were the sheet version. ⇒ **On iPad, drive to a screen through the sidebar, not through a Home card,
and look at the composed strip before calling a set done.** The framed set is the instrument here;
a raw that looks fine at full size can still be unreadable at the size Apple renders it.

⚖️ **The sheet is not always the wrong answer: `07-faa-reference` is a sheet and stays one**, because
FAA Reference **is** a search sheet on iPad - the sidebar item presents it. Checked, not assumed.

📐 **`03-medxpress-prep` re-captured** full-width, which also fixed the content: Ryan spec'd this slot
as **meds + visits**, and the Aug 28 raw was scrolled to a position where the **Item 18 block
dominated the frame** - duplicating slot 3. The full-width push fits Item 17 medications **and**
Item 19 visits complete in one viewport, which the sheet could not.

📐 **`09-item18` captured** (new file): 25 of 25 answered, **18h = Yes** with a written explanation,
which surfaces the teal **CACI pathway available** banner.

⚠️ **The container had been seeded twice** (4 medications, 4 visits, duplicate Lisinopril). Uninstall,
reinstall, launch once with `-PMGSeedDemoData` gives the clean `2 medications - 2 visits`. **A demo
seeder is not idempotent; check the counts on Home before capturing anything.**

✅ **The CACI banner in `03-item18` was checked against the 8/12 retraction and is NOT a reprint of it.**
The struck sentence was the paywall's *"walk in knowing exactly which documents your diagnosis needs"*,
retracted because it could not hold across 14 disposition tables that branch by sub-condition. The
banner fires **only on a confident single-worksheet match** and attributes the list to **the FAA's own
worksheet**; the non-confident branch renders the hedged *"N FAA CACI worksheets in this category -
tap to browse"* card instead (seen live on 18i). The split is deliberate, so the constraint above
still holds and this shot does not violate it.

---

## 🚨 WHEN A UI CHANGE MEANS THESE MUST BE RE-TAKEN (standing rule, Ryan 2026-09-05)

> ***"log for any UI changes to screen shot material that they need to be taken again for both iphone sizes,
> the ipad, and mac."*** ⇒ **If a change renders on any screen in the table below, re-capture and rebuild every
> affected set IN THE SAME PASS, and re-upload all four.** The tripwire lives in `CLAUDE.md`; this is the detail.

### The seven slots, and what is actually IN frame

**Ask "does my change render here?" - not "did I touch a screenshot file."**

| # | screen | what is visibly in frame, i.e. what a change would break |
|---|---|---|
| 1 | **Home** | days-remaining countdown + class + expiry date · BasicMed course and CMEC cards · the **MedXPress prep** summary line (`N medications - N visits - N of 25 Item 18 answers`) · **What's next** step card · the **"Ways PMG protects your medical"** list, all five rows and their subtitles · the not-advice footer |
| 2 | **MedXPress Prep** | the **Enable MedXPress autofill** row · **Manual fallback** row · **Item 17** heading, Add/edit link, the medication rows and the `N medications recorded` caption · **Item 18** heading and its link rows · **Item 19** heading, Add/edit, doctor-visit rows *(Mac and iPad show Item 19; iPhone cannot reach it, see below)* |
| 3 | **Item 18 / Medical History** | the intro card wording · the `N of 25 answered` ring · **Mark all remaining as No** · the lettered question rows and Yes/No controls · the **Explanation** label and field · the teal **CACI pathway available** banner and its sentence |
| 4 | **Special Issuance** (`Hypertension on medication`) | **Share with my AME** button · About rows · **Your Authorization** fields (Status, Path, issued, expires, next documentation due) and their helper line · **Requirements Checklist** rows, their done/not-done state, `What the FAA asks for`, `In your FAA letter?`, Add document, reminder chips |
| 5 | **My Medical** | Certificate / BasicMed / Both selector · `Expires in about N months` · certificate class, exam date, AME, next exam · **Update your certificate** row · privilege-duration rows and their CFR citations *(Mac slot shows these; iPhone shows the upper half)* |
| 6 | **Health** | the Blood Pressure chart, **both AME Guide reference lines and their labels** · the citation footer (`FAA Guide for Aviation Medical Examiners, Item 55`) and its `Citation checked` date · the reading rows |
| 7 | **FAA Reference** | the search field placeholder · **Common questions** list *(iPad/iPhone sheet)* · the FAA Threshold card · the **What the FAA says** quotation · the **Source** block, `Last verified` date and `View the FAA source` link |

⚖️ **THE EYEBROW AND HEADLINE ARE BAKED INTO THE COMPOSED IMAGE.** Renaming a tab, a section or a feature
invalidates the art even when the screen is pixel-identical. **Copy changes count as UI changes here.**

🚨 **Slot 6 and 7 are the FAA-content slots and they age on their own.** A CDN publish can move a quoted
sentence, a threshold or a `Last verified` date **with no build at all** - and the screenshot keeps showing the
old one. ⇒ **A content publish that changes displayed FAA text is a re-capture trigger, same as a UI change.**

### Capture -> output map (one capture can feed two slots)

| capture into | rebuilds | script | canvas |
|---|---|---|---|
| `screenshots/iphone-new/` | **`iphone-v2/` AND `iphone-69-v2/`** | `build-mobile-v2.py` | 1284x2778 and 1290x2796 |
| `asc/ipad/` | `ipad-v2/` | `build-mobile-v2.py` | 2064x2752 |
| `asc/mac-raw/` | `mac-v2/` | `build-mac-v2.py` | 2880x1800 |

✅ **The two iPhone sizes do NOT need separate captures** - one raw directory, two canvases, one script run.
📌 **But they are separate ASC slots and BOTH must be re-uploaded.**
✅ Both scripts **wipe their output directory first**, because a reorder renames files and stale names survived
a run once and would have shipped a duplicated set.

### The traps that cost time on 2026-09-05, in the order they bite

1. **🚨 On iPad, reach a screen through the SIDEBAR, not a Home card.** The Home card *presents* a form sheet, a
   small centred panel over a dimmed Home taking about a third of the frame; My Records *pushes* the same screen
   full-width. **Same build, same data, one is unreadable at listing size.** ⚖️ Not universal: `07-faa-reference`
   is a sheet because FAA Reference genuinely is one on iPad. **Check which, do not assume.**
2. **🚨 Look at the COMPOSED STRIP before calling a set done.** A raw that looks fine at full size can be
   illegible once framed. The sheet-vs-push defect was invisible in the raws and obvious in the strip.
3. **⚠️ Seed ONCE.** The demo seeder is not idempotent - a double run gave 4 medications and 4 visits with a
   duplicate Lisinopril. **Read the counts off Home before capturing.** Uninstall, reinstall, launch once with
   `-PMGSeedDemoData`. 🚫 Do not pass the flag again on a relaunch.
4. **⚠️ Pin the status bar with `--time` ONLY.** Also overriding battery/cellular put a **green charging battery
   in one shot out of seven**. **Crop the status-bar strip and stack it against a sibling** before believing it
   matches. Clear the override when done.
5. **📐 iPhone cannot fit medications AND doctor visits in one frame.** Item 18 sits between Item 17 and Item 19
   and runs ~500pt on its own, against a ~750pt screen. **One or the other.** Current slot 2 leads with
   medications, which was Ryan's call 2026-09-05. Mac and iPad fit both.
