#!/usr/bin/env python3
"""Has each scheduled safeguard actually run recently?

WHY. On 2026-07-11 an automated drift check was built at Ryan's request. It did not run
once for 27 days: it sat on a branch where a cron trigger cannot fire, its activation was
gated behind an App Review that never happened, and its YAML would not parse. None of
that was visible, because a workflow that never runs produces nothing to look at. It
looked like insurance and was not.

So this asks the question nobody was asking: for every workflow in this repo that has a
schedule, when did it last actually execute? A scheduled job that has been silent for
well past its own interval has stopped working, whatever its file says.

It reads the workflow files for their cron intervals rather than hardcoding a list, so a
new scheduled check is covered the day it is added and nobody has to remember.

USAGE
    python3 scripts/check-watchdog.py          # exit 1 if a scheduled workflow has gone quiet
"""

import datetime
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

# A scheduled job is considered silent once this much of its own interval has passed with
# no run. Generous on purpose: GitHub delays scheduled runs under load, sometimes by
# hours, and a watchdog that fires on ordinary lateness is noise, which is the exact
# failure this whole exercise was about.
GRACE_MULTIPLIER = 2.5


def cron_interval_days(expr: str) -> float | None:
    """Rough interval for the cron forms this repo uses. None if not recognised."""
    fields = expr.split()
    if len(fields) != 5:
        return None
    _, _, dom, _, dow = fields
    if dow != "*":          # weekly, e.g. "0 15 * * 1"
        return 7.0
    if dom == "*":          # daily, e.g. "0 13 * * *"
        return 1.0
    return None


# This file's own workflow is excluded. It cannot meaningfully watch itself: on its very
# first run it would report itself as never having run, and if it ever stopped it would
# not be around to say so. That blind spot is real and unavoidable, so it is named here
# rather than papered over. Its own last-run time is visible on the Actions tab.
SELF = "watchdog.yml"


def scheduled_workflows() -> dict[str, float]:
    """{workflow filename: expected interval in days} for everything with a schedule."""
    found = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        if path.name == SELF:
            continue
        text = path.read_text()
        crons = re.findall(r'cron:\s*"([^"]+)"', text)
        intervals = [d for d in (cron_interval_days(c) for c in crons) if d]
        if intervals:
            found[path.name] = min(intervals)
    return found


def last_run(workflow_file: str) -> datetime.datetime | None:
    r = subprocess.run(
        ["gh", "run", "list", "--workflow", workflow_file, "--limit", "1",
         "--json", "createdAt", "--jq", ".[0].createdAt"],
        cwd=ROOT, capture_output=True, text=True,
    )
    stamp = r.stdout.strip()
    if r.returncode != 0 or not stamp:
        return None
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def main() -> int:
    now = datetime.datetime.now(datetime.timezone.utc)
    workflows = scheduled_workflows()
    if not workflows:
        print("No scheduled workflows found. Nothing to watch.")
        return 0

    silent = []
    print(f"checking {len(workflows)} scheduled workflow(s)\n")
    for name, interval in sorted(workflows.items()):
        when = last_run(name)
        allowed = interval * GRACE_MULTIPLIER
        if when is None:
            silent.append(f"- `{name}`: **has never run**, and it is scheduled every "
                          f"{interval:g} day(s)")
            print(f"  NEVER RUN   {name}  (every {interval:g}d)")
            continue
        age = (now - when).total_seconds() / 86400
        if age > allowed:
            silent.append(f"- `{name}`: last ran **{age:.1f} days ago**, but it is "
                          f"scheduled every {interval:g} day(s)")
            print(f"  SILENT      {name}  last run {age:.1f}d ago (every {interval:g}d)")
        else:
            print(f"  ok          {name}  last run {age:.1f}d ago (every {interval:g}d)")

    print()
    if not silent:
        print("Every scheduled safeguard has run recently.")
        return 0

    report = [
        "A scheduled check has stopped running.",
        "",
        "This matters more than it looks. A workflow that never runs produces no output, "
        "so nothing about it looks wrong. In July 2026 a drift check sat dead for 27 days "
        "for three separate reasons and appeared to be working the entire time.",
        "",
        *silent,
        "",
        "**Check, in this order:** is the workflow file on the repository's DEFAULT branch "
        "(scheduled runs fire from nowhere else)? Does its YAML parse? Has GitHub disabled "
        "it for inactivity, which it does to scheduled workflows in repos with no pushes "
        "for 60 days?",
    ]
    (ROOT / "watchdog-report.md").write_text("\n".join(report) + "\n")
    print("\n".join(silent))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
