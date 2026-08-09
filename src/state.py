"""Tilstandslagring for samme-dags delta (07:30 -> 17:30).

Lagrer én fil per dato under data/state/. Morgenkjøringen skriver sine
validerte saker dit; kveldskjøringen leser fila og viser kun det som er nytt
siden morgenen, uten å be Gemini oppsummere de samme sakene på nytt.

Denne fil-per-dato-strukturen er bevisst laget for å kunne vokse rett inn i
et rullerende flerdagers "story-fingerprint"-lager i Fase 2, uten
formatendring.
"""

import hashlib
import json
import os

from src import config

STATE_DIR = os.path.join("data", "state")


def story_id(source_urls):
    normalized = sorted(u.strip().rstrip("/") for u in source_urls if u)
    digest = hashlib.sha1("|".join(normalized).encode("utf-8")).hexdigest()
    return digest[:16]


def state_path(date_str):
    return os.path.join(STATE_DIR, f"{date_str}.json")


def load_state(date_str):
    path = state_path(date_str)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(date_str, state):
    os.makedirs(STATE_DIR, exist_ok=True)
    path = state_path(date_str)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def record_run(date_str, run_type, story_dicts, status):
    """Lagrer resultatet av en kjøring (morning/evening) i dagens state-fil."""
    state = load_state(date_str)
    state["date"] = date_str
    state[run_type] = {
        "stories": story_dicts,
        "status": status,
    }
    save_state(date_str, state)
    return state


def morning_story_ids(date_str):
    state = load_state(date_str)
    morning = state.get("morning")
    if not morning:
        return None
    return {s["story_id"] for s in morning.get("stories", [])}


def morning_stories(date_str):
    state = load_state(date_str)
    morning = state.get("morning")
    if not morning:
        return None
    return morning.get("stories", [])


def _parse_date(date_str):
    from datetime import datetime
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def previous_story_ids(date_str, days=None):
    """story_id-er publisert i rapportene de foregående dagene.

    Brukes til å merke saker som "videreført fra forrige rapport", jf.
    spesifikasjonens krav om at overlapp skal være tydelig markert. Ser kun
    bakover på TIDLIGERE datoer - samme dags morgen/kveld håndteres av
    delta-logikken i pipeline.py.
    """
    from datetime import timedelta

    days = config.CONTINUITY_DAYS if days is None else days
    today = _parse_date(date_str)
    seen = {}
    for back in range(1, days + 1):
        day = (today - timedelta(days=back)).strftime("%Y-%m-%d")
        state = load_state(day)
        for run_type in ("morning", "evening"):
            run = state.get(run_type)
            if not run:
                continue
            for story in run.get("stories", []):
                seen.setdefault(story["story_id"], day)
    return seen


def prune_old_states(date_str, keep_days=None):
    """Sletter state-filer eldre enn vinduet vi trenger, så repoet ikke
    vokser i det uendelige med filer ingen leser."""
    from datetime import timedelta

    keep_days = (config.CONTINUITY_DAYS + 3) if keep_days is None else keep_days
    if not os.path.isdir(STATE_DIR):
        return []
    cutoff = _parse_date(date_str) - timedelta(days=keep_days)
    removed = []
    for name in os.listdir(STATE_DIR):
        if not name.endswith(".json"):
            continue
        try:
            file_date = _parse_date(name[:-5])
        except ValueError:
            continue
        if file_date < cutoff:
            try:
                os.remove(os.path.join(STATE_DIR, name))
                removed.append(name)
            except OSError:
                pass
    return removed


def last_good_stories(date_str):
    """Beste tilgjengelige tidligere resultat for fallback ved total svikt."""
    state = load_state(date_str)
    for run_type in ("evening", "morning"):
        run = state.get(run_type)
        if run and run.get("stories"):
            return run["stories"], run_type
    return None, None
