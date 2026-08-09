"""Regelbasert forfiltrering før Gemini-kall: tidsvindu og eksakt-URL-dedup.

Formålet er å kutte støy og kostnad før LLM-kall, slik spesifikasjonen ber om,
uten å gjøre semantiske vurderinger som egentlig krever Gemini.
"""

from datetime import datetime, timedelta, timezone

from src import config


def within_lookback(article, now):
    if article.published is None:
        # Kildene er "siste nyheter"-feeder; uten dato antar vi ferskt
        # innhold heller enn å risikere å miste dagens saker.
        return True
    return now - article.published <= timedelta(hours=config.LOOKBACK_HOURS)


def prefilter(articles, now=None):
    now = now or datetime.now(timezone.utc)
    seen_links = set()
    result = []
    for article in articles:
        if not within_lookback(article, now):
            continue
        link_key = article.link.strip().rstrip("/")
        if link_key and link_key in seen_links:
            continue
        if link_key:
            seen_links.add(link_key)
        result.append(article)
    return result
