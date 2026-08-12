#!/usr/bin/env bash
# Body for the one-off delivery test.
set -euo pipefail
cat <<'BODY'
This is a test of the Pilot Medical Guardian content safeguards.

If you are reading this in your inbox, the alerting works. From now on you will
get an email like this, automatically, when any of these trip:

  - a cited FAA page changes upstream
  - a cited FAA source stops resolving
  - an FAA CACI worksheet PDF is reissued
  - the FAA HIMS-AME PDF is reissued
  - a scheduled safeguard stops running

Each one also opens a GitHub issue or pull request assigned to you, so there is
a durable record even if an email is missed.

No action needed. This message was sent manually as a one-off test and the
workflow that sent it is being deleted.
BODY
