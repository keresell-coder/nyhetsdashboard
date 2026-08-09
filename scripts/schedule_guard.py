#!/usr/bin/env python3
"""Avgjør om denne workflow-kjøringen faktisk skal produsere en rapport.

GitHub Actions' schedule.cron er alltid UTC og flytter seg ikke med
sommertid/vintertid. Løsningen er å planlegge begge UTC-forskyvningene for
begge klokkeslett (07:30 og 17:30 Europe/Oslo) i workflow-fila, og la dette
scriptet avgjøre ved kjøretid om den faktiske norske lokaltiden er innenfor
toleranse for et av målklokkeslettene. To av de fire daglige triggerne vil
alltid være i feil sesong og skal da bare avbryte uten å gjøre noe.

Skriver proceed/run_type til $GITHUB_OUTPUT.
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TOLERANCE_MINUTES = 20
TARGETS = [("morning", 7, 30), ("evening", 17, 30)]
TIMEZONE = "Europe/Oslo"


def decide(now, forced_run_type=""):
    forced = (forced_run_type or "").strip()
    if forced in ("morning", "evening"):
        return forced
    for name, hour, minute in TARGETS:
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if abs((now - target).total_seconds()) <= TOLERANCE_MINUTES * 60:
            return name
    return None


def main():
    now = datetime.now(ZoneInfo(TIMEZONE))
    run_type = decide(now, os.environ.get("FORCE_RUN_TYPE", ""))

    github_output = os.environ.get("GITHUB_OUTPUT")
    lines = []
    if run_type is None:
        print(f"Utenfor kjøretidsvindu ({now.isoformat()}); avbryter uten å publisere.")
        lines.append("proceed=false\n")
    else:
        print(f"Kjøretype: {run_type} ({now.isoformat()})")
        lines.append("proceed=true\n")
        lines.append(f"run_type={run_type}\n")

    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.writelines(lines)
    else:
        sys.stdout.writelines(lines)


if __name__ == "__main__":
    main()
