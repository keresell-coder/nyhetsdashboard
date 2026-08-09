"""Bygger index.html fra validerte data med ren strengbygging (stdlib
html.escape overalt) - bevisst ingen templating-motor, se plan for
begrunnelse (unngår kollisjon mellom Jekyll/Liquid-syntaks og LLM-tekst).
"""

from html import escape

from src import config

CSS = """
:root {
  color-scheme: dark;
  --bg: #0f1115; --card: #171a21; --card-hover: #1c202a; --border: #262b36;
  --text: #e9ebf0; --muted: #98a1b0; --accent: #6ea8fe; --accent-dim: #3a5a8c;
  --comment: #f2a93c; --comment-bg: #241d10; --single: #7d8590;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  background: var(--bg); color: var(--text); margin: 0; padding: 0 0 4rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.6; font-size: 16px;
}
a { color: var(--accent); }
.wrap { max-width: 760px; margin: 0 auto; padding: 0 1.25rem; }

header.top { padding: 2.25rem 1.25rem 1.25rem; max-width: 760px; margin: 0 auto; }
header.top h1 { margin: 0 0 0.4rem; font-size: 1.75rem; letter-spacing: -0.01em; }
header.top .meta { color: var(--muted); font-size: 0.92rem; }
.stats-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.9rem; }
.stat-chip {
  font-size: 0.78rem; color: var(--muted); background: var(--card);
  border: 1px solid var(--border); border-radius: 999px; padding: 0.25rem 0.65rem;
}
.coverage-note {
  margin-top: 0.9rem; font-size: 0.82rem; color: var(--muted);
  border-left: 2px solid var(--accent-dim); padding-left: 0.7rem;
}

nav.jump {
  position: sticky; top: 0; z-index: 10; background: rgba(15,17,21,0.92);
  backdrop-filter: blur(6px); border-bottom: 1px solid var(--border);
  padding: 0.6rem 1.25rem; margin-top: 1.25rem;
}
nav.jump .wrap { display: flex; flex-wrap: wrap; gap: 0.4rem; padding: 0; }
nav.jump a {
  font-size: 0.78rem; text-decoration: none; color: var(--muted);
  border: 1px solid var(--border); border-radius: 999px; padding: 0.28rem 0.7rem;
  white-space: nowrap;
}
nav.jump a:hover { color: var(--text); border-color: var(--accent-dim); }

main.wrap { padding-top: 1.5rem; }

.highlights { margin-bottom: 2.5rem; }
.highlights h2 { font-size: 1rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; margin: 0 0 1rem; }
article.highlight {
  border-left: 3px solid var(--accent); padding-left: 1rem; margin-bottom: 1.4rem;
}
article.highlight .rank { color: var(--accent); font-size: 0.8rem; font-weight: 600; }
article.highlight .rank .new { color: var(--comment); margin-left: 0.4rem; }
article.highlight h3 { margin: 0.2rem 0 0.4rem; font-size: 1.2rem; }

section.category { margin-top: 2.4rem; scroll-margin-top: 3.5rem; }
section.category h2 {
  font-size: 1.15rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 0;
}
h2.section-title { border: none; margin: 2.6rem 0 0.25rem; font-size: 1.3rem; }
p.section-subtitle { color: var(--muted); font-size: 0.88rem; margin: 0 0 0.5rem; }

article.story {
  background: var(--card); border: 1px solid var(--border); border-radius: 12px;
  padding: 1.1rem 1.25rem; margin: 1rem 0; transition: background 0.15s ease;
}
article.story:hover { background: var(--card-hover); }
article.story.is-comment { background: var(--comment-bg); border-color: #4a3a1a; }
article.story h3 { margin: 0 0 0.5rem; font-size: 1.08rem; line-height: 1.4; }
article.story p.ingress, article.highlight p.ingress { margin: 0 0 0.6rem; color: var(--text); }
article.story .badges, article.highlight .badges { margin-bottom: 0.6rem; display: flex; flex-wrap: wrap; gap: 0.35rem; }
.badge {
  display: inline-block; font-size: 0.72rem; padding: 0.18rem 0.55rem; border-radius: 999px;
  border: 1px solid var(--border); color: var(--muted);
}
.badge.comment { color: var(--comment); border-color: var(--comment); }
.badge.single { color: var(--single); border-color: var(--single); }
.badge.multi { color: var(--accent); border-color: var(--accent-dim); }
p.disclaimer { color: var(--comment); font-size: 0.82rem; margin: -0.1rem 0 0.6rem; }
details.summary summary { cursor: pointer; color: var(--accent); font-size: 0.9rem; list-style: none; }
details.summary summary::-webkit-details-marker { display: none; }
details.summary summary::before { content: "▸ "; }
details.summary[open] summary::before { content: "▾ "; }
details.summary .body { margin-top: 0.6rem; color: var(--text); white-space: pre-line; }
ul.sources { margin: 0.7rem 0 0; padding-left: 1.1rem; font-size: 0.85rem; color: var(--muted); }
ul.sources a { color: var(--accent); }

details.status {
  max-width: 760px; margin: 3rem auto 0; padding: 0 1.25rem;
}
details.status summary {
  cursor: pointer; color: var(--muted); font-size: 0.82rem; list-style: none;
}
details.status summary::-webkit-details-marker { display: none; }
details.status .body {
  margin-top: 0.6rem; padding: 0.9rem 1rem; background: var(--card);
  border: 1px solid var(--border); border-radius: 10px; font-size: 0.82rem; color: var(--muted);
}
details.status .body div { margin-bottom: 0.4rem; }
.banner {
  color: var(--comment); border: 1px solid var(--comment); border-radius: 8px;
  padding: 0.7rem 0.9rem; margin: 1.25rem 1.25rem 0; max-width: 760px;
  margin-left: auto; margin-right: auto;
}
.raw-list li { margin-bottom: 0.5rem; }
.empty-state { color: var(--muted); padding: 1rem 0; }
"""


def _page_shell(title, header_html, nav_html, body_html, footer_html):
    return f"""<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
{header_html}
{nav_html}
<main class="wrap">
{body_html}
</main>
{footer_html}
</body>
</html>
"""


def _header_html(generated_label, all_stories):
    n_stories = len(all_stories)
    n_sources = len({s["source_name"] for story in all_stories for s in story["sources"]})
    n_categories = len({s["main_category"] for s in all_stories})
    stats = ""
    if n_stories:
        stats = (
            '<div class="stats-row">'
            f'<span class="stat-chip">{n_stories} sak(er)</span>'
            f'<span class="stat-chip">{n_sources} kilde(r) brukt</span>'
            f'<span class="stat-chip">{n_categories} kategori(er)</span>'
            "</div>"
        )
    coverage = (
        f"Dekker foreløpig {len(config.SOURCES)} norske kilder "
        f"({', '.join(s['name'] for s in config.SOURCES)}). "
        "Internasjonale og sekundære kilder kommer i en senere fase."
    )
    return f"""<header class="top">
  <h1>Morgenrapport &amp; Nyhetsscreener</h1>
  <div class="meta">{escape(generated_label)}</div>
  {stats}
  <div class="coverage-note">{escape(coverage)}</div>
</header>"""


def _badges_html(story):
    badges = []
    if story["content_group"] == "kommentar_debatt":
        badges.append('<span class="badge comment">Kommentar/debatt</span>')
    if story["distinct_editorial_source_count"] <= 1:
        badges.append('<span class="badge single">Enkeltkilde</span>')
    else:
        badges.append(f'<span class="badge multi">{story["distinct_editorial_source_count"]} uavhengige kilder</span>')
    label = config.CONTENT_TYPE_LABELS.get(story["content_type"], story["content_type"])
    badges.append(f'<span class="badge">{escape(label)}</span>')
    return f'<div class="badges">{"".join(badges)}</div>'


def _story_body_html(story):
    sources_html = "".join(
        f'<li><a href="{escape(s["link"])}" rel="noopener noreferrer" target="_blank">{escape(s["source_name"])}: {escape(s["title"])}</a></li>'
        for s in story["sources"]
    )
    disclaimer_line = ""
    if story.get("comment_disclaimer"):
        disclaimer_line = f'<p class="disclaimer">{escape(story["comment_disclaimer"])}</p>'
    return f"""{_badges_html(story)}
  {disclaimer_line}
  <p class="ingress">{escape(story["ingress"])}</p>
  <details class="summary">
    <summary>Les mer</summary>
    <div class="body">{escape(story["summary"])}</div>
  </details>
  <ul class="sources">{sources_html}</ul>"""


def _story_html(story):
    is_comment_class = " is-comment" if story["content_group"] == "kommentar_debatt" else ""
    return f"""<article class="story{is_comment_class}">
  <h3>{escape(story["headline"])}</h3>
  {_story_body_html(story)}
</article>"""


def _select_highlights(stories):
    candidates = [s for s in stories if s["content_group"] == "redaksjonelt"]
    ranked = sorted(
        candidates,
        key=lambda s: (-s["distinct_editorial_source_count"], config.CATEGORY_PRIORITY.get(s["main_category"], 99)),
    )
    return ranked[: config.TOP_STORIES_COUNT]


def _highlights_html(top_stories, new_ids=frozenset()):
    if not top_stories:
        return ""
    cards = []
    for i, story in enumerate(top_stories, start=1):
        cat_label = config.CATEGORY_LABELS.get(story["main_category"], story["main_category"])
        new_tag = '<span class="new">NY</span>' if story["story_id"] in new_ids else ""
        cards.append(f"""<article class="highlight">
  <div class="rank">#{i} · {escape(cat_label)}{new_tag}</div>
  <h3>{escape(story["headline"])}</h3>
  {_story_body_html(story)}
</article>""")
    return f'<section class="highlights"><h2>Viktigste saker</h2>{"".join(cards)}</section>'


def _category_groups(stories):
    grouped = {cat: [] for cat in config.CATEGORIES}
    for story in stories:
        grouped.setdefault(story["main_category"], []).append(story)
    return grouped


def _section_html(section_id, stories, exclude_ids):
    remaining = [s for s in stories if s["story_id"] not in exclude_ids]
    if not remaining:
        return "", []
    grouped = _category_groups(remaining)
    nav_items = []
    parts = []
    for cat in config.CATEGORIES:
        items = grouped.get(cat) or []
        if not items:
            continue
        anchor = f"cat-{section_id}-{cat}"
        cards = "".join(_story_html(s) for s in items)
        parts.append(f'<section class="category" id="{anchor}"><h2>{escape(config.CATEGORY_LABELS[cat])}</h2>{cards}</section>')
        nav_items.append((anchor, config.CATEGORY_LABELS[cat], len(items)))
    return "".join(parts), nav_items


def _nav_html(nav_groups):
    """nav_groups: liste av (seksjonstittel|None, [(anchor, label, count)])."""
    links = []
    for section_title, items in nav_groups:
        prefix = f"{section_title}: " if section_title else ""
        for anchor, label, count in items:
            links.append(f'<a href="#{anchor}">{escape(prefix)}{escape(label)} ({count})</a>')
    if not links:
        return ""
    return f'<nav class="jump"><div class="wrap">{"".join(links)}</div></nav>'


def _status_body_html(status):
    lines = []
    unavailable = status.get("unavailable_sources") or []
    if unavailable:
        names = ", ".join(f'{u["name"]} ({u["reason"]})' for u in unavailable)
        lines.append(f"<div>Ikke inkludert i denne versjonen: {escape(names)}</div>")
    source_errors = status.get("source_errors") or []
    if source_errors:
        names = ", ".join(e["source"] for e in source_errors)
        lines.append(f"<div>Kilder som feilet ved henting denne kjøringen: {escape(names)}</div>")
    dropped = status.get("dropped_count") or 0
    if dropped:
        lines.append(f"<div>{dropped} sak(er) utelatt pga. kvalitetskontroll (f.eks. for langt/kort sammendrag).</div>")
    if not lines:
        lines.append("<div>Ingen kjente problemer i denne kjøringen.</div>")
    return "".join(lines)


def _status_details_html(status):
    return f"""<details class="status">
  <summary>Om denne rapporten / kildestatus</summary>
  <div class="body">{_status_body_html(status)}</div>
</details>"""


def render_normal(sections, status, generated_label):
    """sections: liste av (tittel, stories) - brukes for å skille
    ettermiddagens nye saker fra morgenens saker ved kveldskjøring."""
    all_stories = [s for _, stories in sections for s in stories]

    if not all_stories:
        header = _header_html(generated_label, all_stories)
        body = '<p class="empty-state">Ingen saker å vise i denne kjøringen.</p>'
        footer = _status_details_html(status)
        return _page_shell("Morgenrapport & Nyhetsscreener", header, "", body, footer)

    top_stories = _select_highlights(all_stories)
    top_ids = {s["story_id"] for s in top_stories}
    new_ids = {s["story_id"] for s in sections[0][1]} if len(sections) > 1 else set()

    body_parts = [_highlights_html(top_stories, new_ids)]
    nav_groups = []
    for idx, (title, stories) in enumerate(sections):
        section_html, nav_items = _section_html(str(idx), stories, top_ids)
        if title:
            body_parts.append(f'<h2 class="section-title">{escape(title)}</h2>')
        if not section_html:
            body_parts.append('<p class="empty-state">Ingen nye saker i denne seksjonen.</p>')
        else:
            body_parts.append(section_html)
        nav_groups.append((title if len(sections) > 1 else None, nav_items))

    header = _header_html(generated_label, all_stories)
    nav = _nav_html(nav_groups)
    body = "".join(body_parts)
    footer = _status_details_html(status)
    return _page_shell("Morgenrapport & Nyhetsscreener", header, nav, body, footer)


def render_raw_fallback(articles, status, generated_label):
    """Ren kildebasert visning uten AI-sammendrag, gruppert per kilde (ikke
    kategori, siden kategorisering krever et vellykket Gemini-kall)."""
    banner = '<div class="banner">Automatisk sammendrag utilgjengelig – viser rå kildeliste.</div>'
    by_source = {}
    for a in articles:
        by_source.setdefault(a.source_name, []).append(a)
    parts = []
    for source_name in sorted(by_source):
        lis = "".join(
            f'<li><a href="{escape(a.link)}" target="_blank" rel="noopener noreferrer">{escape(a.title)}</a></li>'
            for a in by_source[source_name]
        )
        parts.append(f'<section class="category"><h2>{escape(source_name)}</h2><ul class="raw-list">{lis}</ul></section>')
    header = _header_html(generated_label, [])
    body = "".join(parts)
    footer = _status_details_html(status)
    return _page_shell("Morgenrapport & Nyhetsscreener", header, "", banner + body, footer)


def render_stale(stories, generated_label, stale_since_label):
    banner = f'<div class="banner">Kunne ikke oppdatere – viser forrige vellykkede rapport fra {escape(stale_since_label)}.</div>'
    top_stories = _select_highlights(stories)
    top_ids = {s["story_id"] for s in top_stories}
    section_html, nav_items = _section_html("stale", stories, top_ids)
    header = _header_html(generated_label, stories)
    nav = _nav_html([(None, nav_items)])
    body = _highlights_html(top_stories) + section_html
    footer = _status_details_html({})
    return _page_shell("Morgenrapport & Nyhetsscreener", header, nav, banner + body, footer)
