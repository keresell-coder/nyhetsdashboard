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


def build_groups(classifications, articles, clusters_by_lead=None):
    """Slår sammen klassifiserte artikler til saksgrupper basert på Geminis
    likely_duplicate_of-forslag, filtrerer bort ikke-promoterte og ugyldige
    article_id-referanser, og kutter til et hardt tak på antall saker.

    Taket er ikke bare kosmetikk: hver sak koster Gemini-forespørsler, og
    døgnkvoten er 20 (se config.py). Prioriteringen følger spesifikasjonens
    redaksjonelle rekkefølge - bred kildedekning først, deretter fagområde.
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

    clusters_by_lead = clusters_by_lead or {}

    def member_articles(members):
        """Alle artikler bak en gruppe: både de Gemini slo sammen og de
        cluster.py allerede hadde slått sammen under hver representant."""
        out = []
        for c in members:
            lead_id = c["article_id"]
            out.extend(clusters_by_lead.get(lead_id) or [articles_by_id[lead_id]])
        return out

    def distinct_sources(members):
        # Kun redaksjonelle kilder teller - sekundærkilder gir bakgrunn,
        # ikke bekreftelse.
        return len({
            a.source_id for a in member_articles(members) if a.is_corroborating
        })

    def sub_priority_rank(root):
        """Innen rom_cyber: satcom foran cyber foran jordobservasjon."""
        return config.SUB_PRIORITY_RANK.get(
            by_id[root].get("sub_priority") or "ingen", 3
        )

    def region_rank(members):
        """Beste (laveste) regionprioritet i gruppen - brukes som tiebreak."""
        arts = member_articles(members)
        return min((a.region_priority for a in arts), default=9)

    def relevance_score(members):
        """Kildebredde pluss et moderat nordisk påslag.

        Bredden dominerer bevisst: en stor sak omtalt av flere
        internasjonale redaksjoner skal ikke fortrenges av en liten
        enkeltkildesak fra Norden. Påslaget gir Norden forrang kun ved
        omtrent lik dekning.
        """
        arts = member_articles(members)
        best_region = min(
            (a.region for a in arts),
            key=lambda r: config.REGION_PRIORITY.get(r, 9),
            default="intl",
        )
        return distinct_sources(members) + config.REGION_BONUS.get(best_region, 0.0)

    # Grupper per fagområde, beste sak (flest uavhengige kilder) først.
    by_category = {}
    for root, members in groups_by_root.items():
        by_category.setdefault(by_id[root]["main_category"], []).append((root, members))
    for cat_groups in by_category.values():
        cat_groups.sort(
            key=lambda rm: (
                sub_priority_rank(rm[0]),
                -relevance_score(rm[1]),
                region_rank(rm[1]),
            )
        )

    # Fordel plassene runde for runde i stedet for streng prioritetsrekkefølge.
    # Ren prioritetssortering lot de høyest prioriterte fagområdene spise hele
    # taket, slik at f.eks. økonomi og sport falt helt ut på dager med mye
    # sikkerhetsstoff. Runde-for-runde gir bredde, mens rekkefølgen innenfor
    # hver runde fortsatt følger den redaksjonelle prioriteringen.
    ordered_categories = sorted(
        by_category, key=lambda c: config.CATEGORY_PRIORITY.get(c, 99)
    )
    selection = []
    for round_no in range(config.MAX_STORIES_PER_CATEGORY):
        for cat in ordered_categories:
            if round_no < len(by_category[cat]):
                selection.append(by_category[cat][round_no])

    for root, members in selection:
        if len(groups_by_key) >= config.MAX_TOTAL_STORIES:
            break
        root_classification = by_id[root]
        main_category = root_classification["main_category"]
        per_category_count[main_category] = per_category_count.get(main_category, 0) + 1

        group_key = str(root)
        groups_by_key[group_key] = {
            "group_key": group_key,
            "main_category": main_category,
            "secondary_tags": root_classification.get("secondary_tags", []),
            "content_type": root_classification["content_type"],
            "sub_priority": root_classification.get("sub_priority") or "ingen",
            "articles": member_articles(members),
        }

    dropped_for_capacity = len(groups_by_root) - len(groups_by_key)
    return groups_by_key, dropped_for_capacity


def validate_stories(draft_raw, groups_by_key, previous_ids=None):
    """Validerer Geminis skrevne saker mot ordgrenser og ekte kildereferanser.
    Returnerer (gyldige saker som dicts, status-tillegg).

    previous_ids: {story_id: dato} fra tidligere dagers rapporter, brukt til
    å merke videreførte saker.
    """
    valid_stories = []
    drop_reasons = []
    previous_ids = previous_ids or {}

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
            {
                "source_name": a.source_name,
                "link": a.link,
                "title": a.title,
                "is_secondary": not a.is_corroborating,
            }
            for a in used_articles
        ]
        content_type = group["content_type"]
        content_group = config.CONTENT_GROUP[content_type]

        # Kun redaksjonelle kilder teller som uavhengig bekreftelse.
        # Sekundærkilder (EU, EIA, ESA) dokumenterer og gir bakgrunn, men
        # gjør ikke en sak "omtalt av flere medier", jf. spesifikasjonen.
        distinct_editorial_sources = len(
            {a.source_id for a in used_articles if a.is_corroborating}
        )
        secondary_source_count = sum(1 for a in used_articles if not a.is_corroborating)

        sid = state.story_id([a.link for a in used_articles])
        valid_stories.append({
            "story_id": sid,
            "continued_from": previous_ids.get(sid),
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
            "secondary_source_count": secondary_source_count,
            "comment_disclaimer": config.COMMENT_DISCLAIMER if content_group == "kommentar_debatt" else None,
        })

    status_additions = {
        "dropped_count": len(drop_reasons),
        "drop_reasons": drop_reasons,
    }
    return valid_stories, status_additions
