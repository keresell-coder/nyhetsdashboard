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
    region: str = field(default="no")

    @property
    def region_priority(self):
        return config.REGION_PRIORITY.get(self.region, 9)

    @property
    def is_corroborating(self):
        """Sekundærkilder (institusjoner, primærdata) dokumenterer og gir
        bakgrunn, men teller aldri som uavhengig redaksjonell bekreftelse."""
        return self.tier not in config.NON_CORROBORATING_TIERS


COMMENT_URL_MARKERS = (
    "/meninger/", "/mening/", "/kommentar/", "/kommentarer/", "/debatt/",
    "/ytring/", "/ytringer/", "/kronikk/", "/leder/", "/lederartikkel/",
)


# Feedene bruker tre ulike formater. RSS 2.0 har element uten navnerom,
# RSS 1.0/RDF legger dem under purl.org-navnerommet, og Atom bruker
# <entry> under Atom-navnerommet. Uten dette finner parseren null artikler
# i RDF- og Atom-feeder - oppdaget da Nikkei Asia stille bidro med 0 saker.
NS_RSS1 = "{http://purl.org/rss/1.0/}"
NS_ATOM = "{http://www.w3.org/2005/Atom}"
NS_DC = "{http://purl.org/dc/elements/1.1/}"

ITEM_PATHS = (".//item", f".//{NS_RSS1}item", f".//{NS_ATOM}entry")

# Feltnavn i prioritert rekkefølge per format.
TITLE_TAGS = ("title", f"{NS_RSS1}title", f"{NS_ATOM}title")
DESC_TAGS = (
    "description", f"{NS_RSS1}description",
    f"{NS_ATOM}summary", f"{NS_ATOM}content",
)
LINK_TAGS = ("link", f"{NS_RSS1}link")
DATE_TAGS = (
    "pubDate", f"{NS_DC}date", "date",
    f"{NS_ATOM}published", f"{NS_ATOM}updated",
)


def _parse_pubdate(text):
    """Godtar både RFC 2822 (RSS 2.0 pubDate) og ISO 8601 (dc:date, Atom)."""
    if not text:
        return None
    text = text.strip()
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _find_items(root):
    for path in ITEM_PATHS:
        items = root.findall(path)
        if items:
            return items
    return []


def _first_text(item, tags):
    for tag in tags:
        el = item.find(tag)
        if el is not None and el.text and el.text.strip():
            return el.text.strip()
    return ""


def _find_link(item):
    """Atom legger URL-en i href-attributtet, ikke i elementteksten."""
    text = _first_text(item, LINK_TAGS)
    if text:
        return text
    for tag in (f"{NS_ATOM}link", "link"):
        for el in item.findall(tag):
            href = el.get("href")
            if href:
                rel = el.get("rel")
                if rel in (None, "alternate"):
                    return href.strip()
    return ""


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
        items = _find_items(root)
        if source.get("tier") == "secondary":
            limit = config.SECONDARY_ARTICLE_LIMIT
        else:
            limit = config.MAX_ARTICLES_BY_REGION.get(
                source.get("region"), config.MAX_ARTICLES_PER_SOURCE
            )
        for item in items[:limit]:
            title = _first_text(item, TITLE_TAGS)
            if not title:
                continue
            link = _find_link(item)
            description = _first_text(item, DESC_TAGS)
            pub_raw = _first_text(item, DATE_TAGS)
            articles.append({
                "source_id": source["id"],
                "source_name": source["name"],
                "title": title,
                "description": description,
                "link": link,
                "published": _parse_pubdate(pub_raw),
                "comment_hint": _has_comment_marker(link),
                "tier": source.get("tier", "primary_no"),
                "region": source.get("region", "no"),
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
            region=item["region"],
        ))
    status["unavailable_sources"] = list(config.UNAVAILABLE_SOURCES)
    return articles
