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

### 2026-10-27 — iPhone and iPad sets re-captured for iOS 2.3.4 (all seven slots)

The 10/26-27 visual pass (status chips, larger section headers, 42pt countdown), the MedXPress Prep footer's new
**Share with my AME** button, and the SI **Requirements** timeline changed every slot. iPhone 17 Pro and iPad Pro 13"
sims, fresh install of the 2.3.4 build, seeded once (Home read 2 medications, 2 visits, 246 days), Pro via the launch
argument `-compedPro YES` (argument domain, nothing persisted), `--time 9:41` (iPad `2026-10-09T13:41:00.000Z`).
- **Slot 4 framing changed:** iPhone frames the authorization dates + the new Requirements timeline + Notes; iPad is the
  top of the SI screen, which now includes Requirements. Headline unchanged ("See what you sent and what is open").
- **iPhone slot 2:** the taller footer (two buttons) hides the "2 medications recorded" caption; both rows still show.
- **iPad slot 1:** the fifth "Ways PMG protects" row now falls just below the frame (taller section spacing). Kept the
  top-of-Home framing.
- **Fresh-install chrome to clear first:** iPhone shows the old 2.3 What's New sheet; iPad shows the intro, the consent
  screen and the "Lock your records" card (Not now); both ask for notifications on My Medical.
- **Duo outer + inner re-taken the same day** (`duo-outer-v2/`, `duo-inner-v2/`): PMG-Duo, fresh install, seeded once, 9:41.
  Outer and inner Prep slots scroll so both medications clear the two-button footer; both SI slots frame Your
  Authorization + Requirements. ⚠️ Device Hub windows are invisible to the background (AX) tools and its pose
  buttons refused automated clicks ("could not verify which document"), so Ryan set the open pose by hand.
- **Mac re-taken the same day** (`mac-v2/`, Ryan's OK to bring the window forward): `mac-companion` 1.2.4 Debug from a
  worktree, test store DELETED then `-PMGSeedDemoData` once, `-PMGForceLight`, `-compedPro YES` (launch argument),
  `screencapture -l <window> -o` after `open <debug .app>` so every raw is the ACTIVE look (close button reads red).
  The capture caught a real defect: the Prep footer cut "Open MedXPress in Safari" (fixed `mac-companion`, see git log,
  ships after 1.2.4 (19)). Prefs unchanged, store deleted, extension list = baseline.
- **Not done in this pass:** the
  header asset (its own medical-only capture; "267", "Class 1 medical" and the expiry are drawn by
  `build-header-asset.py`, and Home no longer shows "Class 1 medical"), and the website gallery (held until 2.3.4 /
  1.2.4 are live: new UI on the site before release would show features the store build does not have).

### 2026-10-16 — iPhone Duo: two new sets (`duo-outer-v2/`, `duo-inner-v2/`)

ASC's iPhone Duo slot takes **outer 1398x2034** and **inner 2853x2007** (or the rotated sizes), required from April 2027 for
builds on the iOS 27.1 SDK (`APP_STORE_APPROVAL.md` #7). Same seven slots, order and headlines. Raws in `duo-outer/` and
`duo-inner/`, captured on the `PMG-Duo` simulator (iOS 27.1) with `simctl io <udid> screenshot --display=<UUID>`
(`simctl io <udid> enumerate` lists the two framebuffers by size), demo data seeded once, `compedPro` set for the run and
removed after, `--time 9:41`. Poses are set by hand in Xcode 27's Device Hub (it replaced Simulator.app): outer = closed;
inner = fully open and WIDE, which shows the sidebar layout. Inner FAA Reference is a sheet, as on iPad; everything else is
reached through the sidebar. The captures do not draw the outer camera dot, same as iPhone captures omit the Island.
⚠️ The simulator tool's taps are in POINTS of the live display (inner 951x669): divide the 2853-px capture by 3.
`build-mobile-v2.py` builds both; the iPhone and iPad outputs came back byte-identical. 📌 This is now a FIFTH and SIXTH
set: a change to any slot screen re-captures these too.

### 2026-10-14 — slot 3 (Item 18) re-captured on all four sets for iOS 2.3.2 / Mac 1.2.2

18h = Yes now shows a **"1 FAA table for this question / Hypertension FAQs"** card under the CACI banner (FAA disposition
tables, app `6e5f4c0d` / `f13989c2`), so the 10/9 Item 18 raws no longer matched the build. Re-taken with the same framing:
iPhone 17 Pro (`iphone-new/item18.png`, `--time 9:41`), iPad Pro 13" via the sidebar (`asc/ipad/09-item18.png`; the iPad status
bar shows the DATE, so it was pinned with `--time "2026-10-09T13:41:00.000Z"` to keep "Fri Oct 9" like its siblings; a
non-millisecond ISO string is rejected), Mac 1.2.2 Debug (`asc/mac-raw/04-item18.png`, test store seeded once, light mode).
⚠️ **A background Mac window renders INACTIVE** (gray traffic lights, gray progress bar, dimmed sidebar): `screencapture -l`
works off-Space but captured the inactive look, so the window was brought forward for ~2 s (Ryan's OK) and captured active;
the selected 18h row then draws in the active blue. Both scripts re-run: only the three `03-item18.png` outputs changed in the
mobile sets, and `mac-v2/03-item18.png` in the Mac set. Mac settings restored, test store deleted, extension list = baseline.

### 2026-10-09 — end-of-month demo expiry, re-captured (iPad all 7, iPhone 6 of 7)

`DemoDataSeeder` (app `ea7b678d` / `cf59dfc3`) now computes the certificate expiry from a mid-month exam ~4 months back
with `RenewalCalculator`, so the demo reads **Jun 30, 2027** (when run in Oct 2026), matching the header asset. Before,
it stored `days(130)`: a mid-month date on Home, and on the Mac certificate slot "through Jan 5, 2027" beside its own
"Class 1 privileges Jan 31, 2027". The SI authorization now runs 2 years from the exam (it must outlive the certificate,
or Home shows the SI date instead), and the SI item due date sits outside Home's 60-day "SI item due" window (inside it,
the card pushes the fifth "Ways PMG protects" row off the iPad Home slot).
- **iPad, all seven re-taken**: five of the Aug 28 raws carried a green charging battery and cell bars. Slot 4 is now the
  top of the SI screen (Share with my AME, About, Your Authorization, checklist in one frame).
- **iPhone, six re-taken** on the iPhone 17 Pro (the 9/05 iPhone Air sim is gone; `home.png` was already 17 Pro). The
  9/05 raws read 11:52 / 11:58 / 11:59; all seven now read 9:41.
- **iPhone slot 2 changed shape**: the MedXPress confirmation-number section now sits between the autofill rows and Item
  17, so autofill and the medication list no longer fit one frame. Shipped: scrolled to confirmation number + Item 17
  medications + Open MedXPress (Ryan 10/9: "Your call"; kept, since his 9/05 call was to lead with medications. The alternative keeps the autofill rows and loses the medications).
- **Mac, all seven re-taken the same day** (Ryan: "Ok lets do the mac"), in his own account with `-PMGScreenshotStore`
  (`lsof` showed only `tmp/PMGScreenshotStore/screenshots.store`), not a second user account. Three traps, in order:
  ⚠️ **the temp store SURVIVES between sessions** (an earlier session never deleted it), so `-PMGSeedDemoData` stacked a
  second set: 8 medications. Delete `Data/tmp/PMGScreenshotStore` BEFORE seeding, not only after. ⚠️ **His Mac runs Dark
  mode**: `-AppleInterfaceStyle Light` did nothing; **`-NSRequiresAquaSystemAppearance YES`** forced light for this app only
  (never change his system setting). ⚖️ The sidebar now renders `#EDEDED` where the August raws read `#FAFAFA`, active
  window or not, so all seven were re-taken rather than three, or the strip would disagree with itself.
  `compedPro` set for the session (DEBUG-only, `EntitlementManager.compOverride`) and restored to `0`. Safari extension:
  the build's `.appex` displaced the `/Applications` 1.2.1 entry; `pluginkit -r` on ours brought his back and the list
  matched the pre-build baseline exactly; then `lsregister -u` and the build deleted.
- **Website refreshed with it** (Mac shot leads the hero): `hero-mac` / `hero-ipad` / `hero-iphone` / `home` from these
  raws plus a fresh iPhone 17 Pro Home (264), same sizes as before. The Mac hero alt had re-acquired "130 days ...
  January 5, 2027" in the 9/02 redesign; made generic again (the 8/28 rule).

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
| `asc/duo-outer/` | `duo-outer-v2/` | `build-mobile-v2.py` | 1398x2034 |
| `asc/duo-inner/` | `duo-inner-v2/` | `build-mobile-v2.py` | 2853x2007 |

✅ **The two iPhone sizes do NOT need separate captures** - one raw directory, two canvases, one script run.
📌 ~~But they are separate ASC slots and BOTH must be re-uploaded.~~ **2026-10-14: ASC now has one "iPhone with Dynamic Island (large display)" box (6.5"/6.7"/6.9") taking 1290x2796; it rejects 1284x2778. Upload `iphone-69-v2/` only; the medium-display (6.1"/6.3") box borrows it.**
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
