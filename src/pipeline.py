"""Orkestrerer hele kjøringen: innhenting -> forfiltrering -> Gemini ->
validering -> tilstand -> rendering. Kalles fra generate_dashboard.py.

Se NEWS_SCREENER_SPEC.md og planen for den graderte fallback-stigen dette
implementerer:
  1. Alt fungerer -> normal rendering.
  2. Noen saker feiler validering -> publiser resten + notis.
  3. Gemini-kall feiler -> rå kildebasert visning, ingen AI-sammendrag.
  4. Ingen artikler i det hele tatt -> ikke overskriv index.html; vis siste
     vellykkede rapport med "stale"-banner, eller en ærlig tom side hvis
     det heller ikke finnes noen tidligere rapport.
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from src import config, gemini_client, ingest, prefilter, render, state, validate

INDEX_PATH = "index.html"


def _now_oslo():
    return datetime.now(ZoneInfo(config.TIMEZONE))


def _generated_label(run_type, now):
    run_label = {"morning": "morgenrapport", "evening": "ettermiddagsoppdatering"}.get(run_type, run_type)
    return f"Oppdatert {now.strftime('%d.%m.%Y kl. %H:%M')} ({run_label}, {config.TIMEZONE})"


def _write_index(html):
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)


def run():
    run_type = os.environ.get("RUN_TYPE", "morning").strip() or "morning"
    if run_type not in ("morning", "evening"):
        run_type = "morning"

    now = _now_oslo()
    date_str = now.strftime("%Y-%m-%d")
    generated_label = _generated_label(run_type, now)
    status = {}

    articles = ingest.fetch_all(status)
    filtered = prefilter.prefilter(articles)

    if not filtered:
        stale_stories, stale_run_type = state.last_good_stories(date_str)
        if stale_stories:
            html = render.render_stale(stale_stories, generated_label, f"tidligere {stale_run_type}-kjøring i dag")
            _write_index(html)
            print("Ingen artikler hentet denne kjøringen; viser forrige rapport (stale).")
            return
        html = render.render_normal([(None, [])], status, generated_label)
        _write_index(html)
        print("Ingen artikler hentet, og ingen tidligere rapport finnes. Publiserte tom side.")
        return

    try:
        classifications = gemini_client.classify_articles(filtered)
    except gemini_client.GeminiError as exc:
        status["gemini_error"] = str(exc)
        html = render.render_raw_fallback(filtered, status, generated_label)
        _write_index(html)
        print(f"Gemini-klassifisering feilet ({exc}); viser rå kildeliste.")
        return

    groups_by_key, dropped_for_capacity = validate.build_groups(classifications, filtered)

    if not groups_by_key:
        html = render.render_normal([(None, [])], status, generated_label)
        _write_index(html)
        state.record_run(date_str, run_type, [], status)
        print("Ingen saker ble vurdert som relevante nok til publisering.")
        return

    try:
        draft_raw = gemini_client.draft_stories(list(groups_by_key.values()))
    except gemini_client.GeminiError as exc:
        status["gemini_error"] = str(exc)
        html = render.render_raw_fallback(filtered, status, generated_label)
        _write_index(html)
        print(f"Gemini-skriving feilet ({exc}); viser rå kildeliste.")
        return

    valid_stories, validation_status = validate.validate_stories(draft_raw, groups_by_key)
    validation_status["dropped_count"] = validation_status.get("dropped_count", 0) + dropped_for_capacity
    status.update(validation_status)

    if run_type == "morning":
        sections = [(None, valid_stories)]
    else:
        morning_ids = state.morning_story_ids(date_str)
        if morning_ids is None:
            sections = [("Full rapport (ingen morgenrapport funnet i dag)", valid_stories)]
        else:
            new_stories = [s for s in valid_stories if s["story_id"] not in morning_ids]
            carried = state.morning_stories(date_str) or []
            sections = [
                ("Ettermiddagsoppdatering – nye saker siden morgenrapporten", new_stories),
                ("Morgenens saker", carried),
            ]
            valid_stories = new_stories  # det som lagres i state for "evening"

    html = render.render_normal(sections, status, generated_label)
    _write_index(html)
    state.record_run(date_str, run_type, valid_stories, status)
    print(f"Fullført ({run_type}): {sum(len(s) for _, s in sections)} sak(er) publisert.")
