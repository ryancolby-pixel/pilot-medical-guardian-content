#!/usr/bin/env bash
# File a safeguard finding as ONE GitHub issue and ONE email, and stay quiet while it is unchanged.
#
# usage: file-finding.sh <label> <color> <label-description> <issue-title> <body-file> <email-subject>
#
# WHY (Ryan 2026-10-05: "one email per finding"). check-content-fidelity.yml and
# check-verification-age.yml commented on their issue EVERY run and sent no email of their own,
# so they reached Ryan only through GitHub's "all jobs have failed" mail plus the issue mail.
# Their three older siblings (links, med-claims, freshness) already notify on CHANGE, not on
# STATE, keyed on a fingerprint in the issue body. This gives these two the same rule:
#   - same finding as the open issue  -> no comment, no email, green run
#   - new or different finding        -> create or update the issue (unassigned), send OUR email
# The issue is never assigned: assignment is what made GitHub send a second mail.
#
# THE FINGERPRINT is the body's FINDINGS section only: everything before the first "## " heading
# (Warnings / Approaching sections change without the finding changing), with lines about a
# source that "could not fetch" dropped (network flake is not a new finding) and every digit
# removed (timestamps and "52 days" counters move every week).
#
# Email failure is recorded as mail_failed=true in $GITHUB_OUTPUT; the workflow's last step
# fails the run only on that (see send-alert-email.sh).

set -euo pipefail

LABEL="${1:?label}"; COLOR="${2:?color}"; LABEL_DESC="${3:?label description}"
TITLE="${4:?issue title}"; BODY_FILE="${5:?body file}"; SUBJECT="${6:?email subject}"

FP=$(awk '/^## /{exit} {print}' "$BODY_FILE" | grep -v 'could not fetch' | tr -d '0-9' \
     | shasum -a 256 | cut -c1-16)

OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT
{ cat "$BODY_FILE"; printf '\n\n<!-- fingerprint:%s -->\n' "$FP"; } > "$OUT"

gh label create "$LABEL" --color "$COLOR" --description "$LABEL_DESC" 2>/dev/null || true
EXISTING=$(gh issue list --state open --label "$LABEL" --author 'github-actions[bot]' \
           --json number --jq '.[0].number' || true)

if [ -n "$EXISTING" ]; then
  PREV=$(gh issue view "$EXISTING" --json body --jq '.body' | grep -o 'fingerprint:[a-f0-9]*' \
         | head -1 | cut -d: -f2 || true)
  if [ "$PREV" = "$FP" ]; then
    echo "Same finding as issue #$EXISTING already reports. Staying quiet."
    exit 0
  fi
  gh issue comment "$EXISTING" --body-file "$OUT"
  gh issue edit "$EXISTING" --body-file "$OUT"
else
  gh issue create --title "$TITLE" --label "$LABEL" --body-file "$OUT"
fi

./scripts/send-alert-email.sh "$SUBJECT" "$OUT" || echo "mail_failed=true" >> "${GITHUB_OUTPUT:-/dev/null}"
