"""Deterministisk klynging av artikler som dekker samme hendelse.

Dette kjøres FØR Gemini og koster ingen API-forespørsler - viktig, siden
døgnkvoten bare er 20 (se config.py). Den fanger de opplagte tilfellene der
flere redaksjoner publiserer nær identiske overskrifter om samme hendelse
("Zelenskyj: Odesas havn skadet i russiske angrep" hos både NRK og
Aftenposten). Gemini får deretter klyngene, ikke enkeltartiklene, og kan
slå sammen flere på semantisk grunnlag - inkludert på tvers av språk, som
denne ordbaserte metoden ikke klarer.

Uten dette ble bare 2 av 25 saker merket som flerkildedekket, selv om flere
av dem åpenbart var dekket av flere aviser.
"""

import re
import unicodedata

from src import config

# Norske/svenske/danske/engelske funksjonsord som ikke sier noe om hva
# saken handler om, og som ellers gir falske treff mellom urelaterte saker.
STOPWORDS = {
    "og", "i", "på", "til", "for", "av", "med", "er", "som", "det", "en", "et",
    "den", "de", "har", "kan", "skal", "ble", "blir", "var", "om", "at", "fra",
    "seg", "ikke", "men", "så", "vil", "her", "nå", "etter", "over", "under",
    "mot", "ved", "eller", "å", "the", "a", "an", "of", "to", "in", "on", "for",
    "and", "is", "are", "was", "were", "be", "has", "have", "with", "at", "by",
    "från", "och", "för", "att", "som", "med", "har", "der", "die", "das",
    "les", "des", "une", "dans", "pour", "que", "del", "las", "los", "por",
}

MIN_TOKENS = 3


def _normalize(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return text


def title_tokens(title):
    tokens = {
        t for t in _normalize(title).split()
        if len(t) > 2 and t not in STOPWORDS and not t.isdigit()
    }
    return tokens


def _similarity(tokens_a, tokens_b):
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = len(tokens_a & tokens_b)
    # Overlap-koeffisient (delt på den minste mengden) i stedet for Jaccard:
    # overskrifter varierer mye i lengde mellom redaksjoner, og Jaccard
    # straffer da en kort overskrift som er helt inneholdt i en lang.
    return overlap / min(len(tokens_a), len(tokens_b))


def cluster_articles(articles, threshold=None):
    """Grupperer artikler som ser ut til å dekke samme hendelse.

    Returnerer en liste av klynger, hver som en liste av Article-objekter.
    Artikler fra samme kilde slås ikke sammen - to VG-saker om samme tema
    er som regel ulike vinklinger, ikke duplikater, og å slå dem sammen
    ville feilaktig sett ut som bredere kildedekning enn det er.
    """
    threshold = config.CLUSTER_SIMILARITY_THRESHOLD if threshold is None else threshold

    token_sets = [title_tokens(a.title) for a in articles]
    parent = list(range(len(articles)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i in range(len(articles)):
        if len(token_sets[i]) < MIN_TOKENS:
            continue
        for j in range(i + 1, len(articles)):
            if len(token_sets[j]) < MIN_TOKENS:
                continue
            if articles[i].source_id == articles[j].source_id:
                continue
            if _similarity(token_sets[i], token_sets[j]) >= threshold:
                union(i, j)

    grouped = {}
    for idx, article in enumerate(articles):
        grouped.setdefault(find(idx), []).append(article)

    # Rekkefølgen avgjør hva som overlever når listen må kuttes før
    # klassifisering. Kildebredde dominerer, med et moderat nordisk påslag
    # (se config.REGION_BONUS) - ellers ville en enkeltkildesak fra Norden
    # fortrengt en stor sak omtalt av flere internasjonale redaksjoner.
    def sort_key(members):
        best_region = min(
            (m.region for m in members),
            key=lambda r: config.REGION_PRIORITY.get(r, 9),
        )
        distinct = len({m.source_id for m in members})
        score = distinct + config.REGION_BONUS.get(best_region, 0.0)
        return (-score, config.REGION_PRIORITY.get(best_region, 9))

    return sorted(grouped.values(), key=sort_key)
