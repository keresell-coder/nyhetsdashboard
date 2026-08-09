import os
import urllib.request
import json
import xml.etree.ElementTree as ET

# 1. Definer nyhetskilder (RSS-feeder)
RSS_FEEDS = {
    "Norge & Økonomi": [
        "https://www.nrk.no/nyheter/siste.rss",
        "https://e24.no/rss2"
    ],
    "Teknologi & Fremtid": [
        "https://www.tek.no/feed/rss"
    ]
}

API_KEY = os.environ.get("GEMINI_API_KEY")

def fetch_rss_headlines():
    articles = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    for category, urls in RSS_FEEDS.items():
        for url in urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    xml_data = response.read()
                    root = ET.fromstring(xml_data)
                    for item in root.findall('.//item')[:5]:
                        title = item.find('title').text if item.find('title') is not None else ''
                        desc = item.find('description').text if item.find('description') is not None else ''
                        link = item.find('link').text if item.find('link') is not None else ''
                        if title:
                            articles.append(f"Kategori: {category}\nTittel: {title}\nInnhold: {desc}\nLenke: {link}\n---")
            except Exception as e:
                print(f"Feil ved henting av {url}: {e}")
    return "\n".join(articles)

def generate_html_with_gemini(raw_news):
    if not API_KEY:
        print("FEIL: GEMINI_API_KEY mangler i Environment Variables!")
        return "<h1>Feil: API-nøkkel mangler</h1>"

    prompt = f"""
Du er en erfaren nyhetsredaktør. Analyser følgende ferske nyheter fra ulike kilder og lag et stilrent, moderne HTML-dashboard på norsk.

Inndata:
{raw_news}

KRAV TIL OUTPUT:
1. Returner KUN ren HTML-kode (start direkte med <!DOCTYPE html> og slutt med </html>). Ingen markdown-blokker (som ```html).
2. Designet skal være mørk modus (dark mode) med fin typografi, responsive kort som ser bra ut på mobil og PC.
3. Innhold:
   - Tittel: "Morgenrapport & Nyhetsscreener"
   - Topp-seksjon: "Viktigste saker i dag (3 punkter)"
   - Kategoriser sakene ryddig.
   - Gi korte sammendrag (2-3 setninger) for hver sak med lenke til kilden ("Les mer").
"""

    # Vi bruker gemini-1.5-flash som er svært stabil og rask via API-et
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=){API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            html_content = res_data['candidates'][0]['content']['parts'][0]['text']
            
            # Rengjør eventuelle markdown-koder
            html_content = html_content.replace("```html", "").replace("```", "").strip()
            return html_content
    except Exception as e:
        print(f"Feil i Gemini API-kall: {e}")
        return f"<h1>Kunne ikke generere dashboard: {e}</h1>"

if __name__ == "__main__":
    print("Henter nyheter...")
    news = fetch_rss_headlines()
    print("Genererer dashboard med Gemini...")
    html = generate_html_with_gemini(news)
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Fullført! index.html er opprettet.")
