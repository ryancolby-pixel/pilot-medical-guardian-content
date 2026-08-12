#!/usr/bin/env bash
# Send an alert email for a tripped FAA safeguard.
#
# WHY THIS EXISTS
# ---------------
# Ryan does not receive GitHub notifications ("I dont have any notifications
# anywhere"), and Slack is setup he should not have to take on. An assigned
# issue is a durable QUEUE but it is not a PUSH -- it only works if someone
# goes and looks. This is the push half, and it deliberately does not depend
# on GitHub's notification settings in any way.
#
# WHY curl AND NOT A MARKETPLACE ACTION
# -------------------------------------
# curl speaks SMTP natively, so there is no third-party action in the supply
# chain of an alert whose whole job is to be trustworthy. It is also one less
# thing to keep pinned.
#
# WHY A SCRIPT AND NOT AN INLINE `run:` BLOCK
# -------------------------------------------
# CLAUDE.md, after the same mistake three times in one day: "Never inline a
# heredoc or a multi-line string in a workflow `run:` block -- put it in a real
# script file." An unindented continuation inside a YAML block scalar silently
# terminates the scalar and produces GitHub's "No jobs were run".
#
# FAIL-SOFT, DELIBERATELY
# -----------------------
# If the secrets are not configured yet this exits 0 with a warning rather than
# failing the job. The issue and the PR are still created either way, so a
# missing secret must never be allowed to suppress the alert that DOES work.
# That is the exact failure this repo already paid for: a safeguard that looked
# like insurance and provided none.
#
# Usage: send-alert-email.sh "<subject>" <body-file>
# Env:   SMTP_USERNAME  SMTP_PASSWORD  ALERT_EMAIL_TO  [ALERT_EMAIL_FROM]

set -euo pipefail

SUBJECT="${1:?usage: send-alert-email.sh <subject> <body-file>}"
BODY_FILE="${2:?usage: send-alert-email.sh <subject> <body-file>}"

if [ -z "${SMTP_USERNAME:-}" ] || [ -z "${SMTP_PASSWORD:-}" ] || [ -z "${ALERT_EMAIL_TO:-}" ]; then
  echo "::warning::Alert email not sent - SMTP_USERNAME / SMTP_PASSWORD / ALERT_EMAIL_TO are not all set. The GitHub issue or PR was still created."
  exit 0
fi

if [ ! -f "$BODY_FILE" ]; then
  echo "::warning::Alert email not sent - body file '$BODY_FILE' not found. The GitHub issue or PR was still created."
  exit 0
fi

FROM="${ALERT_EMAIL_FROM:-$SMTP_USERNAME}"
MSG="$(mktemp)"
trap 'rm -f "$MSG"' EXIT

# Plain RFC 5322. Date is generated on the runner; the body is attached verbatim
# so the report reads the same in mail as it does in the issue.
{
  printf 'From: Pilot Medical Guardian alerts <%s>\n' "$FROM"
  printf 'To: %s\n' "$ALERT_EMAIL_TO"
  printf 'Subject: %s\n' "$SUBJECT"
  printf 'Date: %s\n' "$(date -R)"
  printf 'Content-Type: text/plain; charset=UTF-8\n'
  printf '\n'
  cat "$BODY_FILE"
  printf '\n\n--\nSent by the content repo safeguards. Repo: %s\nRun: %s/%s/actions/runs/%s\n' \
    "${GITHUB_REPOSITORY:-pilot-medical-guardian-content}" \
    "${GITHUB_SERVER_URL:-https://github.com}" \
    "${GITHUB_REPOSITORY:-}" \
    "${GITHUB_RUN_ID:-}"
} > "$MSG"

# iCloud: smtp.mail.me.com:587 with STARTTLS. SMTP_PASSWORD must be an
# APP-SPECIFIC password from appleid.apple.com, not the Apple ID password.
SMTP_URL="${SMTP_URL:-smtp://smtp.mail.me.com:587}"

if curl --silent --show-error --ssl-reqd \
        --url "$SMTP_URL" \
        --user "$SMTP_USERNAME:$SMTP_PASSWORD" \
        --mail-from "$FROM" \
        --mail-rcpt "$ALERT_EMAIL_TO" \
        --upload-file "$MSG"; then
  echo "Alert email sent to $ALERT_EMAIL_TO"
else
  # Still exit 0: the issue/PR is the system of record. A mail outage must not
  # mask the finding, and the job's own logs carry the failure.
  echo "::warning::Alert email FAILED to send. The GitHub issue or PR was still created - check it."
fi
