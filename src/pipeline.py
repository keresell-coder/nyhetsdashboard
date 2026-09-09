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

from src import cluster, config, gemini_client, health, ingest, prefilter, render, state, validate
from pathlib import Path

INDEX_PATH = "index.html"


def _now_oslo():
    return datetime.now(ZoneInfo(config.TIMEZONE))


def _generated_label(run_type, now):
    run_label = {"morning": "morgenrapport", "evening": "ettermiddagsoppdatering"}.get(run_type, run_type)
    return f"Oppdatert {now.strftime('%d.%m.%Y kl. %H:%M')} ({run_label}, {config.TIMEZONE})"


def _write_index(html):
    path = Path(INDEX_PATH)
    temp = path.with_suffix(".html.tmp")
    temp.write_text(html, encoding="utf-8")
    os.replace(temp, path)


def _degrade(date_str, filtered, status, generated_label, reason):
    edition = state.last_good_edition(date_str)
    if edition:
        # Keep the exact displayed edition. Failed attempts must not relabel
        # its content as newly generated or discard its carried morning items.
        if not Path(INDEX_PATH).exists():
            stories = edition.get("displayed_stories", edition.get("stories", []))
            label = f"Siste gyldige utgave: {edition.get('generated_at') or edition['edition_date'] + ' (klokkeslett ikke verifisert)'}"
            _write_index(render.render_stale(stories, label, edition["edition_date"], {"generation_error": reason}))
    elif not Path(INDEX_PATH).exists():
        _write_index(render.render_raw_fallback(filtered, status, "Ingen gyldig datert utgave tilgjengelig"))
    existing_html = Path(INDEX_PATH).read_text(encoding="utf-8")
    monitored_html = render.ensure_health_monitor(existing_html)
    if monitored_html != existing_html:
        _write_index(monitored_html)
    payload = health.manifest(edition, status["attempted_at"], status["source_health"], failure=reason)
    health.validate_manifest(payload)
    health.write_manifest(payload)
    print(f"{reason}; siste gyldige utgave beholdes. health.json viser mislykket forsøk.")


def run():
    run_type = os.environ.get("RUN_TYPE", "morning").strip() or "morning"
    if run_type not in ("morning", "evening"):
        run_type = "morning"

    now = _now_oslo()
    date_str = now.strftime("%Y-%m-%d")
    generated_label = _generated_label(run_type, now)
    status = {"attempted_at": now.isoformat()}

    articles = ingest.fetch_all(status)
    now = _now_oslo()
    status["source_health"] = health.source_coverage(articles, status, now)
    usable_source_ids = {s["source_id"] for s in status["source_health"]["sources"] if s["status"] == "current"}
    filtered = prefilter.prefilter([a for a in articles if a.source_id in usable_source_ids], now=now)

    if not filtered:
        _degrade(date_str, filtered, status, generated_label, "Ingen brukbare daterte kildeartikler")
        return

    # Deterministisk klynging FØR Gemini: slår sammen nær identiske
    # overskrifter fra ulike redaksjoner uten å bruke av døgnkvoten.
    all_clusters = cluster.cluster_articles(filtered)
    clusters = all_clusters[: config.MAX_CLUSTERS_TO_CLASSIFY]
    clusters_by_lead = {c[0].article_id: c for c in clusters}
    multi_source_clusters = sum(1 for c in clusters if len({a.source_id for a in c}) > 1)
    print(
        f"{len(filtered)} artikler -> {len(all_clusters)} klynger "
        f"({multi_source_clusters} med flere redaksjoner), "
        f"sender {len(clusters)} til klassifisering"
    )

    try:
        classifications = gemini_client.classify_articles(clusters)
    except gemini_client.QuotaExhausted as exc:
        status["quota_exhausted"] = True
        _degrade(date_str, filtered, status, generated_label,
                 f"Gemini-døgnkvoten er tom ({exc})")
        return
    except gemini_client.GeminiError as exc:
        status["gemini_error"] = str(exc)
        _degrade(date_str, filtered, status, generated_label,
                 f"Gemini-klassifisering feilet ({exc})")
        return

    groups_by_key, dropped_for_capacity = validate.build_groups(
        classifications, filtered, clusters_by_lead
    )

    if not groups_by_key:
        _degrade(date_str, filtered, status, generated_label, "Klassifisering ga ingen publiserbare saker")
        return

    try:
        draft_raw = gemini_client.draft_stories(list(groups_by_key.values()), status)
    except gemini_client.QuotaExhausted as exc:
        status["quota_exhausted"] = True
        _degrade(date_str, filtered, status, generated_label,
                 f"Gemini-døgnkvoten er tom ({exc})")
        return
    except gemini_client.GeminiError as exc:
        status["gemini_error"] = str(exc)
        _degrade(date_str, filtered, status, generated_label,
                 f"Gemini-skriving feilet ({exc})")
        return

    previous_ids = state.previous_story_ids(date_str)
    valid_stories, validation_status = validate.validate_stories(
        draft_raw, groups_by_key, previous_ids
    )
    if not valid_stories:
        _degrade(date_str, filtered, status, generated_label, "Ingen sammendrag besto validering")
        return
    continued = sum(1 for s in valid_stories if s.get("continued_from"))
    if continued:
        validation_status["continued_count"] = continued
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

    generated = _now_oslo()
    if status.get("draft_batch_failures") or validation_status.get("drop_reasons"):
        status["source_health"]["status"] = "degraded"
    displayed = [story for _, stories in sections for story in stories]
    edition = {
        "generated_at": generated.isoformat(), "edition_date": date_str, "edition_type": run_type,
        "stories": valid_stories, "displayed_stories": displayed, "source_health": status["source_health"],
    }
    payload = health.manifest(edition, generated.isoformat(), status["source_health"])
    if payload["status"] == "blocked":
        _degrade(date_str, filtered, status, generated_label, "Publiseringskontroll mangler daterte kilder i utgaven")
        return
    health.validate_manifest(payload, require_available=True)
    html = render.render_normal(sections, status, _generated_label(run_type, generated))
    _write_index(html)
    state.record_run(date_str, run_type, valid_stories, status, generated_at=generated.isoformat(),
                     source_health=status["source_health"], displayed_stories=displayed)
    health.write_manifest(payload)
    pruned = state.prune_old_states(date_str)
    if pruned:
        print(f"Ryddet bort {len(pruned)} gamle state-fil(er)")
    print(f"Fullført ({run_type}): {sum(len(s) for _, s in sections)} sak(er) publisert.")
