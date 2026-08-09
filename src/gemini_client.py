"""Eneste sted i kodebasen som kaller ut til en LLM (Gemini). Ingen andre
moduler skal gjøre nettverkskall mot en språkmodell-API.

To kall per kjøring, som avtalt i planen, for å holde antall Gemini-kall
lavt og innenfor gratis-kvoten:
  1. classify_articles - klassifiser+velg ut blant alle forfiltrerte artikler
  2. draft_stories     - skriv norsk overskrift/ingress/sammendrag for de
                          utvalgte sakene

Gemini refererer KUN til article_id-verdier den fikk oppgitt i samme kall -
aldri URL-er. Dette er en bevisst anti-hallusinasjon-mekanisme.
"""

import json
import time
import urllib.error
import urllib.request

from src import config, schema


class GeminiError(Exception):
    pass


def _post(payload, timeout=45, max_retries=2):
    if not config.GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY mangler")

    url = f"{config.GEMINI_API_BASE}/{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    last_error = None
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 or exc.code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise GeminiError(f"Gemini API-feil (HTTP {exc.code}): {exc.read()[:300]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            time.sleep(2 ** attempt)
            continue
    raise GeminiError(f"Gemini API utilgjengelig etter {max_retries + 1} forsøk: {last_error}")


def _extract_json(response_data):
    try:
        text = response_data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiError(f"Uventet Gemini-responsformat: {response_data}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Gemini returnerte ugyldig JSON: {text[:300]}") from exc


def _format_article_block(article):
    published = article.published.isoformat() if article.published else "ukjent"
    return (
        f"article_id: {article.article_id}\n"
        f"Kilde: {article.source_name}\n"
        f"Tittel: {article.title}\n"
        f"Ingress/beskrivelse: {article.description}\n"
        f"Publisert: {published}\n"
        f"Kommentar-URL-hint: {article.comment_hint}\n"
        "---"
    )


def classify_articles(articles):
    """Kall 1: klassifiser innholdstype/kategori og foreslå duplikater."""
    if not articles:
        return []

    article_blocks = "\n".join(_format_article_block(a) for a in articles)
    prompt = f"""Du er redaksjonell analytiker for en norsk nyhetsscreener.

Under følger en nummerert liste med artikler (article_id) hentet fra norske
nyhetskilders RSS-feeder i løpet av det siste døgnet.

For HVER artikkel skal du:
1. Klassifisere innholdstype (content_type) presist: nyhet, reportasje,
   intervju, analyse_redaksjonell, kommentar, leder, ytring, kronikk,
   debattinnlegg, eller analyse_vurderende. Bruk "Kommentar-URL-hint" som en
   svak indikasjon, ikke fasit - vurder tittel og ingress selv.
2. Angi hovedkategori (main_category): norsk_politikk, nordisk_politikk,
   internasjonal_politikk, sikkerhet_forsvar, okonomi_makro, geopolitikk,
   rom_cyber, eller sport. Legg til inntil 2 sekundære kategorier hvis
   relevant (secondary_tags).
3. Hvis main_category er rom_cyber: angi sub_priority som "satcom" (satellitt-
   kommunikasjon), "cyber" (cybersikkerhet/-politikk), eller
   "jordobservasjon_ovrig". Ellers: "ingen".
4. Hvis denne artikkelen dekker samme reelle hendelse som en artikkel med
   LAVERE article_id lenger opp i listen, sett likely_duplicate_of til den
   article_id-en. Ellers utelat feltet.
5. Sett promote til true kun hvis dette er en substansiell, redaksjonelt
   relevant sak (ikke quiz, værmelding, annonse eller ren underholdnings-
   trivia) som hører hjemme i en seriøs daglig nyhetsoversikt.

Artikler:
{article_blocks}

Returner KUN strukturert JSON i henhold til det oppgitte skjemaet. Ikke
diktet opp artikler eller article_id-er som ikke er listet over."""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema.CLASSIFY_RESPONSE_SCHEMA,
        },
    }
    data = _extract_json(_post(payload))
    return data.get("classifications", [])


def _format_group_block(group):
    lines = [f"Gruppe: {group['group_key']} (kategori: {group['main_category']})"]
    for a in group["articles"]:
        lines.append(
            f"  article_id: {a.article_id} | Kilde: {a.source_name} | "
            f"Tittel: {a.title} | Ingress: {a.description}"
        )
    return "\n".join(lines)


def draft_stories(groups):
    """Kall 2: skriv norsk overskrift/ingress/sammendrag for utvalgte saker."""
    if not groups:
        return []

    group_blocks = "\n\n".join(_format_group_block(g) for g in groups)
    prompt = f"""Du er en erfaren norsk nyhetsredaktør. Under følger grupper av
kildeartikler som dekker samme sak. Skriv redaksjonelt nøkternt norsk
sammendrag for HVER gruppe, basert KUN på artiklene i den gruppen.

Regler:
- Overskrift: maksimalt 10 ord.
- Ingress: maksimalt 50 ord.
- Sammendrag: 200-250 ord. Syntese av kildene, IKKE kopi av én enkelt
  artikkel. Faktabasert og nøkternt. Skill tydelig mellom hva som er
  bekreftet, hva som er analyse, og hva som er vurdering. Unngå lange
  direkte sitater - parafraser.
- source_article_ids skal KUN inneholde article_id-er som faktisk står i
  gruppen under. Ikke referer til artikler som ikke er oppgitt.
- Hvis gruppen består av kommentar/debatt-innhold: vær tydelig i teksten på
  at dette er en vurdering/meningsytring, ikke nøytral nyhetsrapportering.
- Skriv på norsk, selv om kildene er på andre språk.

Grupper:
{group_blocks}

Returner KUN strukturert JSON i henhold til det oppgitte skjemaet, én
oppføring per gruppe (group_key må matche eksakt)."""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema.DRAFT_RESPONSE_SCHEMA,
        },
    }
    data = _extract_json(_post(payload))
    return data.get("stories", [])
