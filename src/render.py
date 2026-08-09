"""Bygger index.html fra validerte data med ren strengbygging (stdlib
html.escape overalt) - bevisst ingen templating-motor, se plan for
begrunnelse (unngår kollisjon mellom Jekyll/Liquid-syntaks og LLM-tekst).
"""

from html import escape

from src import config

CSS = """
:root {
  color-scheme: dark;
  --bg: #0f1115; --card: #171a21; --border: #262b36; --text: #e6e8ec;
  --muted: #9aa3b2; --accent: #6ea8fe; --comment: #f5a623; --single: #7d8590;
}
* { box-sizing: border-box; }
body {
  background: var(--bg); color: var(--text); margin: 0; padding: 0 0 3rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.5;
}
header { padding: 2rem 1.25rem 1rem; max-width: 860px; margin: 0 auto; }
header h1 { margin: 0 0 0.25rem; font-size: 1.6rem; }
header .meta { color: var(--muted); font-size: 0.9rem; }
main { max-width: 860px; margin: 0 auto; padding: 0 1.25rem; }
section.category { margin-top: 2rem; }
section.category h2 {
  font-size: 1.1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.4rem;
}
article.story {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 1rem 1.1rem; margin: 0.9rem 0;
}
article.story h3 { margin: 0 0 0.4rem; font-size: 1.05rem; }
article.story p.ingress { margin: 0 0 0.5rem; color: var(--text); }
article.story .badges { margin-bottom: 0.5rem; }
.badge {
  display: inline-block; font-size: 0.72rem; padding: 0.15rem 0.5rem; border-radius: 999px;
  margin-right: 0.35rem; border: 1px solid var(--border); color: var(--muted);
}
.badge.comment { color: var(--comment); border-color: var(--comment); }
.badge.single { color: var(--single); border-color: var(--single); }
details.summary { margin-top: 0.4rem; }
details.summary summary { cursor: pointer; color: var(--accent); font-size: 0.9rem; }
details.summary .body { margin-top: 0.5rem; color: var(--text); }
ul.sources { margin: 0.6rem 0 0; padding-left: 1.1rem; font-size: 0.85rem; color: var(--muted); }
ul.sources a { color: var(--accent); }
.status-footer {
  max-width: 860px; margin: 2.5rem auto 0; padding: 1rem 1.25rem; color: var(--muted);
  font-size: 0.82rem; border-top: 1px solid var(--border);
}
.status-footer .banner {
  color: var(--comment); border: 1px solid var(--comment); border-radius: 8px;
  padding: 0.6rem 0.8rem; margin-bottom: 0.8rem;
}
.raw-list li { margin-bottom: 0.5rem; }
"""


def _page_shell(title, body_html, generated_label):
    return f"""<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>Morgenrapport &amp; Nyhetsscreener</h1>
  <div class="meta">{escape(generated_label)}</div>
</header>
<main>
{body_html}
</main>
</body>
</html>
"""


def _story_html(story):
    sources_html = "".join(
        f'<li><a href="{escape(s["link"])}" rel="noopener noreferrer" target="_blank">{escape(s["source_name"])}: {escape(s["title"])}</a></li>'
        for s in story["sources"]
    )
    disclaimer_line = ""
    if story.get("comment_disclaimer"):
        disclaimer_line = f'<p class="ingress" style="color:var(--comment); font-size:0.82rem;">{escape(story["comment_disclaimer"])}</p>'
    return f"""<article class="story">
  <h3>{escape(story["headline"])}</h3>
  {_badges_html(story)}
  {disclaimer_line}
  <p class="ingress">{escape(story["ingress"])}</p>
  <details class="summary">
    <summary>Les mer</summary>
    <div class="body">{escape(story["summary"])}</div>
  </details>
  <ul class="sources">{sources_html}</ul>
</article>"""


def _badges_html(story):
    badges = []
    if story["content_group"] == "kommentar_debatt":
        badges.append('<span class="badge comment">Kommentar/debatt</span>')
    if story["distinct_editorial_source_count"] <= 1:
        badges.append('<span class="badge single">Enkeltkilde</span>')
    else:
        badges.append(f'<span class="badge">{story["distinct_editorial_source_count"]} uavhengige kilder</span>')
    label = config.CONTENT_TYPE_LABELS.get(story["content_type"], story["content_type"])
    badges.append(f'<span class="badge">{escape(label)}</span>')
    return f'<div class="badges">{"".join(badges)}</div>'


def _stories_by_category(stories):
    grouped = {cat: [] for cat in config.CATEGORIES}
    for story in stories:
        grouped.setdefault(story["main_category"], []).append(story)
    return grouped


def _category_sections_html(stories):
    grouped = _stories_by_category(stories)
    parts = []
    for cat in config.CATEGORIES:
        items = grouped.get(cat) or []
        if not items:
            continue
        cards = "".join(_story_html(s) for s in items)
        parts.append(f'<section class="category"><h2>{escape(config.CATEGORY_LABELS[cat])}</h2>{cards}</section>')
    return "".join(parts) if parts else '<p class="meta">Ingen saker å vise.</p>'


def _status_footer_html(status, banner=None):
    lines = []
    if banner:
        lines.append(f'<div class="banner">{escape(banner)}</div>')
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
        lines.append(f"<div>{dropped} sak(er) utelatt pga. kvalitetskontroll.</div>")
    if not lines:
        lines.append("<div>Ingen kjente problemer i denne kjøringen.</div>")
    return f'<div class="status-footer">{"".join(lines)}</div>'


def render_normal(sections, status, generated_label):
    """sections: liste av (tittel, stories) - brukes for å skille
    ettermiddagens nye saker fra morgenens saker ved kveldskjøring."""
    parts = []
    for title, stories in sections:
        if title:
            parts.append(f"<h2 style='border:none;margin-top:2.2rem;'>{escape(title)}</h2>")
        all_stories = stories
        parts.append(_category_sections_html(all_stories))
    body = "".join(parts) + _status_footer_html(status)
    return _page_shell("Morgenrapport & Nyhetsscreener", body, generated_label)


def render_raw_fallback(articles, status, generated_label):
    """Ren kildebasert visning uten AI-sammendrag, gruppert per kilde (ikke
    kategori, siden kategorisering krever et vellykket Gemini-kall)."""
    parts = ['<div class="status-footer banner" style="margin-bottom:1.5rem;">Automatisk sammendrag utilgjengelig – viser rå kildeliste.</div>']
    by_source = {}
    for a in articles:
        by_source.setdefault(a.source_name, []).append(a)
    for source_name in sorted(by_source):
        lis = "".join(
            f'<li><a href="{escape(a.link)}" target="_blank" rel="noopener noreferrer">{escape(a.title)}</a></li>'
            for a in by_source[source_name]
        )
        parts.append(f'<section class="category"><h2>{escape(source_name)}</h2><ul class="raw-list">{lis}</ul></section>')
    body = "".join(parts) + _status_footer_html(status)
    return _page_shell("Morgenrapport & Nyhetsscreener", body, generated_label)


def render_stale(stories, generated_label, stale_since_label):
    banner = f"Kunne ikke oppdatere – viser forrige vellykkede rapport fra {stale_since_label}."
    body = _category_sections_html(stories) + _status_footer_html({}, banner=banner)
    return _page_shell("Morgenrapport & Nyhetsscreener", body, generated_label)
