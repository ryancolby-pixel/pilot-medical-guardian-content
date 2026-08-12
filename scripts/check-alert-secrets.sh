#!/usr/bin/env bash
# Reports WHETHER each alert secret is set, never its value.
set -euo pipefail
missing=0
for v in SMTP_USERNAME SMTP_PASSWORD ALERT_EMAIL_TO; do
  if [ -n "${!v:-}" ]; then
    echo "  present: $v (set)" 2>/dev/null || echo "  present: $v"
  else
    echo "  MISSING: $v"; missing=1
  fi
done
[ "$missing" -eq 0 ] || { echo "::error::One or more alert secrets are not set."; exit 1; }
