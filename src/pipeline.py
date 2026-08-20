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

from src import cluster, config, gemini_client, ingest, prefilter, render, state, validate

INDEX_PATH = "index.html"


def _now_oslo():
    return datetime.now(ZoneInfo(config.TIMEZONE))


def _generated_label(run_type, now):
    run_label = {"morning": "morgenrapport", "evening": "ettermiddagsoppdatering"}.get(run_type, run_type)
    return f"Oppdatert {now.strftime('%d.%m.%Y kl. %H:%M')} ({run_label}, {config.TIMEZONE})"


def _write_index(html):
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)


def _degrade(date_str, filtered, status, generated_label, reason):
    """Håndterer at Gemini ikke er tilgjengelig.

    Viktig rekkefølge: har vi allerede publisert en ekte rapport i dag,
    skal den BEHOLDES. Tidligere overskrev en feilet kveldskjøring en
    vellykket morgenrapport med en rå overskriftsliste - altså gikk siden
    fra godt innhold til dårligere fordi et senere forsøk feilet.
    Rå kildeliste brukes bare når vi ikke har noe bedre å vise.
    """
    good_stories, good_run_type = state.last_good_stories(date_str)
    if good_stories:
        html = render.render_stale(
            good_stories,
            generated_label,
            f"{good_run_type}-rapporten i dag (nyere forsøk feilet)",
        )
        _write_index(html)
        print(f"{reason}; beholder dagens {good_run_type}-rapport.")
        return

    html = render.render_raw_fallback(filtered, status, generated_label)
    _write_index(html)
    print(f"{reason}; ingen tidligere rapport i dag, viser rå kildeliste.")


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
        html = render.render_normal([(None, [])], status, generated_label)
        _write_index(html)
        state.record_run(date_str, run_type, [], status)
        print("Ingen saker ble vurdert som relevante nok til publisering.")
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

    html = render.render_normal(sections, status, generated_label)
    _write_index(html)
    state.record_run(date_str, run_type, valid_stories, status)
    pruned = state.prune_old_states(date_str)
    if pruned:
        print(f"Ryddet bort {len(pruned)} gamle state-fil(er)")
    print(f"Fullført ({run_type}): {sum(len(s) for _, s in sections)} sak(er) publisert.")
