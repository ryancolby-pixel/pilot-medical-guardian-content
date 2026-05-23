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

## Status: beta

⚠️ The Tier-B medical content (medications, SI requirements, thresholds with cited figures) is **draft pending AME advisor review** — `reviewStatus: "draft"` in the envelope. The app surfaces a *"Pending AME review — not yet verified"* badge on each draft entry. Do not rely on these values for a real certification decision.

## How a content update flows

1. Open a PR editing JSON in `v1/`.
2. Run `python3 scripts/gen_manifest.py` to refresh the manifest (CI also checks this).
3. The CI workflow ([`.github/workflows/validate.yml`](.github/workflows/validate.yml)) validates: JSON well-formedness, required envelope fields, duplicate codes, SI cross-refs, and manifest consistency.
4. For **Tier-B medical content** changes (meds / SI / thresholds-with-numbers), an AME advisor review is required before merge (per the project's content pipeline). **Tier-A** factual changes (Item 18 form text, CFR 61.23 durations, AME-directory facts) follow the lighter curator + CI path.
5. Merge to `main` → GitHub Pages publishes within a minute → the app picks it up on its next refresh (cold launch + foreground re-check + best-effort daily background fetch).

## Privacy

The app fetches these files as plain anonymous GETs. No identifiers, no health data, no user content ever flows to this repo or the GitHub Pages CDN. The personal-data plane lives entirely on the pilot's device + their own iCloud private database — by design, the developer can't see it.

## License

The content here is curated from authoritative FAA sources (the *Guide for Aviation Medical Examiners*, 14 CFR, etc.) which are public. This compilation and its structure are dedicated to the public domain under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).

## Not medical, legal, or regulatory advice

This is reference data displayed by an information / record-keeping app. It is not medical advice and does not certify FAA medical fitness.
