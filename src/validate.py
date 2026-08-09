"""Håndhever spesifikasjonens harde regler. All tillit til Gemini stopper her:
enhver referanse til noe som ikke faktisk ble sendt inn i det aktuelle
kallet blir avvist, ikke bare logget.
"""

from src import config, state

DROP_REASON_LABELS = {
    "unknown_group": "ukjent gruppe",
    "no_valid_sources": "ingen gyldige kildereferanser",
    "headline_too_long": "overskrift for lang",
    "ingress_too_long": "ingress for lang",
    "summary_out_of_range": "sammendrag utenfor lengdekrav",
}


def _word_count(text):
    return len(text.split())


def build_groups(classifications, articles):
    """Slår sammen klassifiserte artikler til saksgrupper basert på Geminis
    likely_duplicate_of-forslag, filtrerer bort ikke-promoterte og ugyldige
    article_id-referanser, og kutter til maks antall saker per kategori.
    """
    articles_by_id = {a.article_id: a for a in articles}
    valid = [
        c for c in classifications
        if c.get("promote") and c.get("article_id") in articles_by_id
    ]

    # Finn rot for hver artikkel: følg likely_duplicate_of til den peker på
    # noe som enten mangler, ikke er promotert, eller ikke finnes i settet.
    by_id = {c["article_id"]: c for c in valid}

    def resolve_root(article_id, depth=0):
        c = by_id.get(article_id)
        dup_of = c.get("likely_duplicate_of") if c else None
        if dup_of is None or dup_of not in by_id or dup_of == article_id or depth > 10:
            return article_id
        return resolve_root(dup_of, depth + 1)

    groups_by_root = {}
    for c in valid:
        root = resolve_root(c["article_id"])
        groups_by_root.setdefault(root, []).append(c)

    groups_by_key = {}
    per_category_count = {}
    dropped_for_capacity = 0

    # Størst gruppe (flest kilder) først, så favoriseres saker med bredere
    # dekning når kategori-taket nås.
    for root, members in sorted(groups_by_root.items(), key=lambda kv: -len(kv[1])):
        root_classification = by_id[root]
        main_category = root_classification["main_category"]
        count_so_far = per_category_count.get(main_category, 0)
        if count_so_far >= config.MAX_STORIES_PER_CATEGORY:
            dropped_for_capacity += len(members)
            continue
        per_category_count[main_category] = count_so_far + 1

        group_key = str(root)
        groups_by_key[group_key] = {
            "group_key": group_key,
            "main_category": main_category,
            "secondary_tags": root_classification.get("secondary_tags", []),
            "content_type": root_classification["content_type"],
            "sub_priority": root_classification.get("sub_priority") or "ingen",
            "articles": [articles_by_id[c["article_id"]] for c in members],
        }

    return groups_by_key, dropped_for_capacity


def validate_stories(draft_raw, groups_by_key):
    """Validerer Geminis skrevne saker mot ordgrenser og ekte kildereferanser.
    Returnerer (gyldige saker som dicts, status-tillegg).
    """
    valid_stories = []
    drop_reasons = []

    for draft in draft_raw:
        group = groups_by_key.get(draft.get("group_key"))
        if group is None:
            drop_reasons.append("unknown_group")
            continue

        allowed_ids = {a.article_id for a in group["articles"]}
        requested_ids = set(draft.get("source_article_ids", []))
        valid_ids = requested_ids & allowed_ids
        if not valid_ids:
            drop_reasons.append("no_valid_sources")
            continue

        headline = (draft.get("headline") or "").strip()
        ingress = (draft.get("ingress") or "").strip()
        summary = (draft.get("summary") or "").strip()

        if not headline or _word_count(headline) > config.HEADLINE_MAX_WORDS:
            drop_reasons.append("headline_too_long")
            continue
        if not ingress or _word_count(ingress) > config.INGRESS_MAX_WORDS:
            drop_reasons.append("ingress_too_long")
            continue
        summary_words = _word_count(summary)
        if not summary or not (config.SUMMARY_MIN_WORDS <= summary_words <= config.SUMMARY_MAX_WORDS):
            drop_reasons.append("summary_out_of_range")
            continue

        articles_by_id = {a.article_id: a for a in group["articles"]}
        used_articles = [articles_by_id[i] for i in sorted(valid_ids)]
        sources = [
            {"source_name": a.source_name, "link": a.link, "title": a.title}
            for a in used_articles
        ]
        content_type = group["content_type"]
        content_group = config.CONTENT_GROUP[content_type]
        distinct_editorial_sources = len({a.source_id for a in used_articles})

        valid_stories.append({
            "story_id": state.story_id([a.link for a in used_articles]),
            "headline": headline,
            "ingress": ingress,
            "summary": summary,
            "content_type": content_type,
            "content_group": content_group,
            "main_category": group["main_category"],
            "secondary_tags": group["secondary_tags"],
            "sub_priority": group["sub_priority"],
            "sources": sources,
            "distinct_editorial_source_count": distinct_editorial_sources,
            "comment_disclaimer": config.COMMENT_DISCLAIMER if content_group == "kommentar_debatt" else None,
        })

    status_additions = {
        "dropped_count": len(drop_reasons),
        "drop_reasons": drop_reasons,
    }
    return valid_stories, status_additions
