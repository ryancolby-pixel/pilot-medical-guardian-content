# Pilot Medical Guardian — content

Public FAA reference content for the [Pilot Medical Guardian](https://github.com/ryancolby-pixel/pilot-medical-guardian-app) iOS app. The app fetches these JSON files anonymously over HTTPS; the data here is **public FAA fact** (no user data, ever).

## What's here

| File | Contents |
| --- | --- |
| [`v1/manifest.json`](v1/manifest.json) | Content version + file checksums (the app fetches this first; only re-downloads changed files) |
| [`v1/medications.json`](v1/medications.json) | FAA medication statuses, cited |
| [`v1/si_conditions.json`](v1/si_conditions.json) | Special Issuance condition templates |
| [`v1/si_requirements.json`](v1/si_requirements.json) | SI requirement checklists |
| [`v1/thresholds.json`](v1/thresholds.json) | FAA-cited metric thresholds |
| [`v1/item18.json`](v1/item18.json) | Form 8500-8 Item 18 checkbox catalog |
| [`v1/cert_durations.json`](v1/cert_durations.json) | 14 CFR 61.23(d) duration cascade |
| [`v1/ame_directory.json`](v1/ame_directory.json) | Curated AME directory (factual, no ratings) |

## Content status

The reference data here is curated from **authoritative FAA sources and cited to them** — per the project's north-star rule, if a value isn't in an authoritative FAA source, it doesn't ship. The app displays it **descriptively** (the reading, the cited FAA threshold, and the source) and, wherever practical, **links to the FAA's own page rather than paraphrasing it** — the app never puts words in the FAA's mouth. It is reference *information*, not medical advice, and it does not certify FAA medical fitness or make any pass/fail determination.

## How a content update flows

1. Open a PR editing JSON in `v1/`.
2. Run `python3 scripts/gen_manifest.py` to refresh the manifest (CI also checks this).
3. The CI workflow ([`.github/workflows/validate.yml`](.github/workflows/validate.yml)) validates: JSON well-formedness, required envelope fields, duplicate codes, SI cross-refs, and manifest consistency.
4. Medical / **Tier-B** content (meds / SI / thresholds-with-numbers) follows the project's content-pipeline direction — **verbatim-first / link-to-FAA**: quote or link the FAA's own source rather than paraphrase it, with editorial-advisor input where any authored text remains. **Tier-A** factual changes (Item 18 form text, CFR 61.23 durations, AME-directory facts) follow the lighter curator + CI path.
5. Merge to `main` → GitHub Pages publishes within a minute → the app picks it up on its next refresh (cold launch + foreground re-check + best-effort daily background fetch).

## Privacy

The app fetches these files as plain anonymous GETs. No identifiers, no health data, no user content ever flows to this repo or the GitHub Pages CDN. The personal-data plane lives entirely on the pilot's device + their own iCloud private database — by design, the developer can't see it.

## License

The content here is curated from authoritative FAA sources (the *Guide for Aviation Medical Examiners*, 14 CFR, etc.) which are public. This compilation and its structure are dedicated to the public domain under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).

## Not medical, legal, or regulatory advice

This is reference data displayed by an information / record-keeping app. It is not medical advice and does not certify FAA medical fitness.
