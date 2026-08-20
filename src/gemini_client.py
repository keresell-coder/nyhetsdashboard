"""Eneste sted i kodebasen som kaller ut til en LLM (Gemini). Ingen andre
moduler skal gjøre nettverkskall mot en språkmodell-API.

Tre kall per kjøring, stramt budsjettert mot den reelle gratiskvoten på
20 forespørsler i døgnet (se config.py):
  1. classify_articles - klassifiser+velg ut blant alle forfiltrerte artikler
  2-3. draft_stories   - skriv norsk tekst for de utvalgte sakene, i bunker

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


class QuotaExhausted(GeminiError):
    """Døgnkvoten er brukt opp - videre forsøk er nytteløse i dag."""


# To tellere: _quota_calls er forespørsler som faktisk tærer på døgnkvoten
# (20/døgn). _attempts teller alt, inkludert 503-forsøk, så en kjøring ikke
# kan gå i evig løkke.
_quota_calls = 0
_attempts = 0
_model_order = None      # løses ved første kall
_working_model = None    # første modell som svarte, gjenbrukes i kjøringen


def calls_made():
    return _quota_calls


def reset_counters():
    """Kun for tester."""
    global _quota_calls, _attempts, _model_order, _working_model
    _quota_calls = _attempts = 0
    _model_order = None
    _working_model = None


def _is_daily_quota_error(body_text):
    lowered = body_text.lower()
    return "perday" in lowered or "per day" in lowered or "requests per day" in lowered


def list_available_models():
    """Henter modeller som faktisk er tilgjengelige for denne nøkkelen.

    Dette er et GET mot /models og tærer ikke på generateContent-kvoten.
    Gjør at reservelisten ikke blir utdatert når Google endrer modellnavn.
    """
    url = f"{config.GEMINI_API_BASE}?key={config.GEMINI_API_KEY}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"Kunne ikke hente modelliste ({exc}); bruker konfigurert reserveliste.")
        return []
    names = []
    for m in data.get("models", []):
        if "generateContent" not in (m.get("supportedGenerationMethods") or []):
            continue
        name = (m.get("name") or "").split("/")[-1]
        if name:
            names.append(name)
    return names


def _resolve_model_order():
    """Rekkefølgen modeller prøves i: konfigurert modell først, deretter
    reserveliste, deretter eventuelle andre gratis Flash-modeller som
    faktisk finnes."""
    global _model_order
    if _model_order is not None:
        return _model_order

    available = list_available_models()
    ordered = [config.GEMINI_MODEL]
    for name in config.GEMINI_MODEL_FALLBACKS:
        if name not in ordered:
            ordered.append(name)

    if available:
        # Dropp navn som ikke finnes, og legg til andre gratis Flash-modeller
        # som ekstra reserve.
        available_set = set(available)
        ordered = [m for m in ordered if m in available_set]
        for name in available:
            if config.FREE_MODEL_MARKER in name and name not in ordered:
                ordered.append(name)
        if not ordered:
            print("ADVARSEL: ingen av de konfigurerte modellene finnes. Prøver som oppgitt.")
            ordered = [config.GEMINI_MODEL]
        print(f"Tilgjengelige modeller (utvalg): {ordered[:4]}")

    _model_order = ordered
    return _model_order


def _request(model, payload, timeout):
    url = f"{config.GEMINI_API_BASE}/{model}:generateContent?key={config.GEMINI_API_KEY}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(payload, timeout=60, max_retries=1):
    """Prøver modellene i tur og orden, med skikkelig ventetid ved 503.

    En modell som svarer 503 er overbelastet, ikke ødelagt - vi venter og
    prøver igjen noen ganger før vi går videre til neste modell. 404 betyr
    at modellnavnet ikke finnes, og vi går rett videre.
    """
    global _quota_calls, _attempts, _working_model

    if not config.GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY mangler")

    models = _resolve_model_order()
    # Har vi allerede funnet en modell som svarer, bruk den først.
    if _working_model and _working_model in models:
        models = [_working_model] + [m for m in models if m != _working_model]

    last_error = None
    for model in models:
        for attempt in range(max_retries + 1):
            if _quota_calls >= config.MAX_GEMINI_CALLS_PER_RUN:
                raise QuotaExhausted(
                    f"Nådde budsjettgrensen på {config.MAX_GEMINI_CALLS_PER_RUN} "
                    "kvotebærende Gemini-kall for denne kjøringen"
                )
            if _attempts >= config.MAX_GEMINI_ATTEMPTS_PER_RUN:
                raise GeminiError(
                    f"Nådde taket på {config.MAX_GEMINI_ATTEMPTS_PER_RUN} forsøk "
                    f"for denne kjøringen. Siste feil: {last_error}"
                )

            _attempts += 1
            try:
                result = _request(model, payload, timeout)
                _quota_calls += 1
                if _working_model != model:
                    print(f"Bruker modell: {model}")
                    _working_model = model
                return result
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code} på {model}"
                error_body = ""
                try:
                    error_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass

                if exc.code == 429:
                    _quota_calls += 1
                    if _is_daily_quota_error(error_body):
                        raise QuotaExhausted(
                            f"Gemini-døgnkvoten er brukt opp: {error_body[:200]}"
                        ) from exc
                    time.sleep(30)
                    continue

                if exc.code == 404:
                    print(f"Modell {model} finnes ikke, prøver neste.")
                    break  # neste modell

                if exc.code >= 500:
                    wait = config.RETRY_BACKOFF_SECONDS[
                        min(attempt, len(config.RETRY_BACKOFF_SECONDS) - 1)
                    ]
                    print(f"{model}: HTTP {exc.code}, venter {wait}s (forsøk {attempt + 1})")
                    time.sleep(wait)
                    continue

                _quota_calls += 1
                raise GeminiError(
                    f"Gemini API-feil (HTTP {exc.code}) på {model}: {error_body[:300]}"
                ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = f"{type(exc).__name__} på {model}: {exc}"
                wait = config.RETRY_BACKOFF_SECONDS[
                    min(attempt, len(config.RETRY_BACKOFF_SECONDS) - 1)
                ]
                print(f"{model}: {type(exc).__name__}, venter {wait}s (forsøk {attempt + 1})")
                time.sleep(wait)
                continue
        print(f"Gir opp {model}, går videre til neste modell.")

    raise GeminiError(f"Ingen modeller svarte. Siste feil: {last_error}")


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


def _format_cluster_block(members):
    """Formaterer én klynge (se cluster.py). Første artikkel er representant
    og bærer article_id-en Gemini skal svare med."""
    lead = members[0]
    published = lead.published.isoformat() if lead.published else "ukjent"
    lines = [
        f"article_id: {lead.article_id}",
        f"Publisert: {published}",
        f"Kommentar-URL-hint: {any(m.comment_hint for m in members)}",
        f"Antall redaksjoner som dekker denne: {len({m.source_id for m in members})}",
    ]
    # Kun de tre første medlemmene og korte ingresser: hele poenget er å gi
    # nok kontekst til klassifisering, ikke å sende hele feeden inn.
    for m in members[:3]:
        desc = (m.description or "")[:120]
        lines.append(f"  [{m.source_name}] {m.title} :: {desc}")
    lines.append("---")
    return "\n".join(lines)


def classify_articles(clusters):
    """Kall 1: klassifiser innholdstype/kategori og foreslå sammenslåing.

    Tar imot klynger fra cluster.py, ikke enkeltartikler. Den deterministiske
    klyngingen har allerede slått sammen nær identiske overskrifter gratis;
    Gemini skal fange det den ikke klarer - samme hendelse beskrevet med helt
    ulike ord, eller på ulike språk.
    """
    if not clusters:
        return []

    cluster_blocks = "\n".join(_format_cluster_block(c) for c in clusters)
    prompt = f"""Du er redaksjonell analytiker for en norsk nyhetsscreener.

Under følger saker fra nyhetskilders RSS-feeder siste døgn. Hver sak har en
article_id og kan allerede inneholde flere artikler fra ulike redaksjoner om
samme hendelse (disse er slått sammen automatisk på likelydende overskrift).

For HVER sak skal du:
1. Klassifisere innholdstype (content_type) presist: nyhet, reportasje,
   intervju, analyse_redaksjonell, kommentar, leder, ytring, kronikk,
   debattinnlegg, eller analyse_vurderende. Bruk "Kommentar-URL-hint" som en
   svak indikasjon, ikke fasit - vurder tittel og ingress selv.
2. Angi hovedkategori (main_category): norsk_politikk, nordisk_politikk,
   internasjonal_politikk, sikkerhet_forsvar, okonomi_makro, geopolitikk,
   rom_cyber, eller sport. Legg til inntil 2 sekundære kategorier hvis
   relevant (secondary_tags).
3. Hvis main_category er rom_cyber: angi sub_priority som "satcom" (satellitt-
   kommunikasjon og konnektivitet), "cyber" (cybersikkerhet/-politikk), eller
   "jordobservasjon_ovrig". Ellers: "ingen".
4. SLÅ SAMMEN SAKER SOM DEKKER SAMME HENDELSE. Dette er viktig og
   underrapporteres lett. Hvis denne saken dekker samme underliggende
   hendelse som en sak med LAVERE article_id lenger opp, sett
   likely_duplicate_of til den article_id-en.
   - Vinkling, ordvalg og språk varierer mye mellom redaksjoner. Se etter
     samme aktør + samme handling + samme tidspunkt, ikke like ord.
   - Eksempel som SKAL slås sammen: "Resultatløft for Berkshire Hathaway -
     pengebingen krympet i andre kvartal" og "Berkshire Hathaway tjente 12,9
     milliarder dollar på driften" - samme kvartalstall, ulik vinkling.
   - Eksempel som IKKE skal slås sammen: to saker om samme selskap, men om
     ulike hendelser (kvartalstall vs. et oppkjøp).
   - Slå også sammen på tvers av språk (norsk/svensk/dansk/engelsk/fransk).
5. Sett promote til true kun hvis dette er en substansiell, redaksjonelt
   relevant sak (ikke quiz, værmelding, annonse eller ren underholdnings-
   trivia) som hører hjemme i en seriøs daglig nyhetsoversikt.

Saker:
{cluster_blocks}

Returner KUN strukturert JSON i henhold til det oppgitte skjemaet, én
oppføring per article_id over. Ikke dikt opp article_id-er."""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema.CLASSIFY_RESPONSE_SCHEMA,
        },
    }
    data = _extract_json(_post(payload, timeout=150, max_retries=2))
    return data.get("classifications", [])


def _format_group_block(group):
    lines = [f"Gruppe: {group['group_key']} (kategori: {group['main_category']})"]
    for a in group["articles"]:
        lines.append(
            f"  article_id: {a.article_id} | Kilde: {a.source_name} | "
            f"Tittel: {a.title} | Ingress: {a.description}"
        )
    return "\n".join(lines)


def _draft_batch(groups):
    """Skriver én bunke saker. Kaster GeminiError hvis bunken feiler."""
    group_blocks = "\n\n".join(_format_group_block(g) for g in groups)
    prompt = f"""Du er en erfaren norsk nyhetsredaktør. Under følger grupper av
kildeartikler som dekker samme sak. Skriv redaksjonelt nøkternt norsk
sammendrag for HVER gruppe, basert KUN på artiklene i den gruppen.

LENGDEKRAV (viktigst - saker utenfor disse grensene forkastes automatisk):
- Overskrift: HØYST 10 ord. Tell ordene før du svarer.
- Ingress: HØYST 50 ord. Tell ordene før du svarer.
- Sammendrag: 200-250 ord, aldri under 150 eller over 300. Tell ordene før
  du svarer, og juster teksten hvis du bommer.

Øvrige regler:
- Sammendraget skal være en syntese av kildene, IKKE kopi av én enkelt
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
    data = _extract_json(_post(payload, timeout=90, max_retries=1))
    return data.get("stories", [])


def draft_stories(groups, status=None):
    """Kall 2: skriv norsk overskrift/ingress/sammendrag for utvalgte saker.

    Deles opp i bunker fordi ett samlet kall for alle sakene ba om 4000+ ord
    i én forespørsel og timet ut konsekvent. En bunke som feiler tar ikke med
    seg resten av rapporten - de øvrige sakene publiseres, og feilen
    registreres i status slik at den vises i "Om denne rapporten".
    """
    if not groups:
        return []

    batches = [
        groups[i : i + config.DRAFT_BATCH_SIZE]
        for i in range(0, len(groups), config.DRAFT_BATCH_SIZE)
    ]
    stories = []
    failed_batches = 0
    last_error = None

    for idx, batch in enumerate(batches, start=1):
        try:
            batch_stories = _draft_batch(batch)
            stories.extend(batch_stories)
            print(f"Skrivebunke {idx}/{len(batches)}: {len(batch_stories)} sak(er)")
        except QuotaExhausted as exc:
            # Kvoten er tom - resten av bunkene ville bare kastet bort
            # forespørsler på å få samme svar. Publiser det vi har.
            failed_batches += len(batches) - idx + 1
            last_error = exc
            print(f"Skrivebunke {idx}/{len(batches)}: kvote tom, avbryter resten ({exc})")
            break
        except GeminiError as exc:
            failed_batches += 1
            last_error = exc
            print(f"Skrivebunke {idx}/{len(batches)} feilet: {exc}")

    if failed_batches and status is not None:
        status["draft_batch_failures"] = failed_batches

    # Bare gi opp helt hvis ingen bunker gikk gjennom - da har vi ingenting
    # å publisere, og pipelinen skal falle tilbake til rå kildeliste.
    if not stories:
        raise GeminiError(f"Alle {len(batches)} skrivebunker feilet: {last_error}")

    return stories
