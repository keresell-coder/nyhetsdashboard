#!/usr/bin/env python3
"""Avgjør om denne workflow-kjøringen skal produsere en rapport.

GitHub Actions' schedule.cron er alltid UTC og flytter seg ikke med
sommertid/vintertid. Derfor planlegges begge UTC-forskyvningene for begge
klokkeslett (07:30 og 17:30 Europe/Oslo), og dette scriptet avgjør hva som
faktisk skal kjøres.

VIKTIG LÆRDOM: første versjon krevde at faktisk lokaltid lå innenfor
±20 minutter av måltidspunktet. Det slo feil - GitHub kjører planlagte
jobber betydelig forsinket når det er travelt. 10. august 2026 kom de tre
planlagte kjøringene 22, 103 og 54 minutter for sent, og ALLE ble avvist.
Ingen rapport ble publisert den dagen.

Løsningen er ikke et større toleransevindu, men å slutte å måle avstand til
et klokkeslett i det hele tatt:

  1. Hvilket DØGNVINDU er vi i nå? (morgen 05-13, kveld 13-24 norsk tid)
  2. Har dette vinduet allerede produsert en rapport i dag?

Da spiller det ingen rolle om jobben starter 20 eller 120 minutter for
sent. De fire cron-oppføringene fungerer som gjentatte forsøk: den første
som kommer gjennom publiserer, resten ser at jobben er gjort og avslutter.

Skriver proceed/run_type til $GITHUB_OUTPUT.
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TIMEZONE = "Europe/Oslo"
STATE_DIR = os.path.join("data", "state")

# Lokale timeintervall (fra og med, til) for hvert vindu.
WINDOWS = (
    ("morning", 5, 13),
    ("evening", 13, 24),
)


def slot_for(now):
    """Hvilket døgnvindu er vi i? None mellom midnatt og kl. 05."""
    for name, start, end in WINDOWS:
        if start <= now.hour < end:
            return name
    return None


def already_ran(date_str, run_type):
    """Har dette vinduet allerede publisert en rapport i dag?

    Leser state-fila pipeline.py skriver ved vellykket kjøring. Feilede
    kjøringer skriver ikke state, så de blir automatisk forsøkt på nytt av
    neste cron - som er ønsket oppførsel.
    """
    path = os.path.join(STATE_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    run = state.get(run_type)
    return bool(run and run.get("stories"))


def decide(now, forced_run_type="", state_lookup=None):
    """Returnerer (run_type|None, begrunnelse)."""
    forced = (forced_run_type or "").strip()
    if forced in ("morning", "evening"):
        return forced, f"tvunget kjøretype: {forced}"

    run_type = slot_for(now)
    if run_type is None:
        return None, f"utenfor døgnvinduene (kl. {now.hour:02d} norsk tid)"

    lookup = state_lookup or already_ran
    if lookup(now.strftime("%Y-%m-%d"), run_type):
        return None, f"{run_type}-rapport er allerede publisert i dag"

    return run_type, f"{run_type}-vindu, ingen rapport publisert ennå"


def main():
    now = datetime.now(ZoneInfo(TIMEZONE))
    run_type, reason = decide(now, os.environ.get("FORCE_RUN_TYPE", ""))

    print(f"Lokal tid: {now.strftime('%Y-%m-%d %H:%M')} ({TIMEZONE})")
    print(f"Beslutning: {reason}")

    lines = ["proceed=false\n"] if run_type is None else [
        "proceed=true\n",
        f"run_type={run_type}\n",
    ]
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.writelines(lines)
    else:
        sys.stdout.writelines(lines)


if __name__ == "__main__":
    main()
