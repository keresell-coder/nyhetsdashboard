"""Henter og parser RSS-feeder til en flat liste av Article-objekter."""

import gzip
import io
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from src import config

USER_AGENT = "Mozilla/5.0 (compatible; NyhetsscreenerBot/1.0; +https://github.com/keresell-coder/nyhetsdashboard)"


@dataclass
class Article:
    article_id: int
    source_id: str
    source_name: str
    title: str
    description: str
    link: str
    published: "datetime | None"
    comment_hint: bool = field(default=False)
    tier: str = field(default="primary_no")

    @property
    def is_corroborating(self):
        """Sekundærkilder (institusjoner, primærdata) dokumenterer og gir
        bakgrunn, men teller aldri som uavhengig redaksjonell bekreftelse."""
        return self.tier not in config.NON_CORROBORATING_TIERS


COMMENT_URL_MARKERS = (
    "/meninger/", "/mening/", "/kommentar/", "/kommentarer/", "/debatt/",
    "/ytring/", "/ytringer/", "/kronikk/", "/leder/", "/lederartikkel/",
)


def _parse_pubdate(text):
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _text(item, tag):
    el = item.find(tag)
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _has_comment_marker(link):
    lowered = link.lower()
    return any(marker in lowered for marker in COMMENT_URL_MARKERS)


def _decompress(raw, content_encoding):
    """Noen feeder (bl.a. FN) svarer gzip-komprimert selv uten at vi ber om
    det. Uten dette feiler XML-parsingen med binærsøppel."""
    encoding = (content_encoding or "").lower()
    try:
        if "gzip" in encoding or raw[:2] == b"\x1f\x8b":
            return gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        if "deflate" in encoding:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    except (OSError, zlib.error):
        return raw
    return raw


def fetch_source(source, status):
    """Henter og parser én RSS-kilde. Feil fanges per kilde og logges i status."""
    articles = []
    req = urllib.request.Request(source["url"], headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = _decompress(response.read(), response.headers.get("Content-Encoding"))
        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        limit = config.MAX_ARTICLES_BY_TIER.get(
            source.get("tier"), config.MAX_ARTICLES_PER_SOURCE
        )
        for item in items[:limit]:
            title = _text(item, "title")
            if not title:
                continue
            link = _text(item, "link")
            description = _text(item, "description")
            pub_raw = _text(item, "pubDate")
            articles.append({
                "source_id": source["id"],
                "source_name": source["name"],
                "title": title,
                "description": description,
                "link": link,
                "published": _parse_pubdate(pub_raw),
                "comment_hint": _has_comment_marker(link),
                "tier": source.get("tier", "primary_no"),
            })
    except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError, TimeoutError, OSError) as exc:
        status.setdefault("source_errors", []).append({"source": source["name"], "error": str(exc)})
    return articles


def fetch_all(status):
    """Henter alle konfigurerte kilder og tildeler stabile article_id-er."""
    raw = []
    for source in config.SOURCES:
        raw.extend(fetch_source(source, status))

    articles = []
    for idx, item in enumerate(raw):
        articles.append(Article(
            article_id=idx,
            source_id=item["source_id"],
            source_name=item["source_name"],
            title=item["title"],
            description=item["description"],
            link=item["link"],
            published=item["published"],
            comment_hint=item["comment_hint"],
            tier=item["tier"],
        ))
    status["unavailable_sources"] = list(config.UNAVAILABLE_SOURCES)
    return articles
