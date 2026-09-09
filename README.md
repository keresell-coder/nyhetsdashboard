# nyhetsdashboard

Daglig norsk nyhetsscreener. Kjører automatisk i GitHub Actions kl. 07:30 og
17:30 (Europe/Oslo, DST-trygt) og publiseres på GitHub Pages. Ingen lokal
avhengighet – alt lever i dette repoet.

Redaksjonell spesifikasjon: se `NEWS_SCREENER_SPEC.md` i kildeprosjektet
(ikke committet hit). Nåværende status er **Fase 1** av en faset utrulling:

- Kilder: NRK, DN, E24, VG, Aftenposten, TV2, Nettavisen (offentlig RSS,
  verifisert). Dagbladet, Klassekampen og ABC Nyheter mangler kjent RSS og
  vises som "ikke tilgjengelig" i statusfeltet.
- Alle 8 fagkategorier og skille mellom redaksjonelt/kommentarstoff er på
  plass. Ekte flerkilde-klynging på tvers av utgivere, full "videreført fra
  forrige rapport"-sporing og internasjonale kilder kommer i Fase 2/3.
- 17:30-kjøringen viser kun det som er nytt siden 07:30 samme dag (delta),
  ikke en full ny rapport.

## Arkitektur

```
RSS-innhenting → forfiltrering → Gemini (klassifiser) → gruppering
  → Gemini (skriv norsk tekst) → Python-validering → tilstand → HTML
```

Gemini returnerer kun strukturert JSON og refererer aldri til URL-er direkte
(kun interne `article_id`-er) – Python slår opp faktiske kildelenker og
avviser enhver referanse som ikke faktisk ble sendt inn. Se `src/`.

## Oppsett

- `GEMINI_API_KEY` – repo secret (allerede satt).
- `GEMINI_MODEL` – valgfri repo **variable** (Settings → Secrets and
  variables → Actions → Variables). Standard er `gemini-flash-latest` hvis
  ikke satt. Bruk kun modeller i Flash-familien – Gemini Pro er ikke lenger
  gratis.

## Gemini-kvote (viktig begrensning)

Gratisnivået gir **20 forespørsler i døgnet** (avlest i Google AI Studio →
Rate Limit, ikke fra nettartikler – de tar ofte feil). I tillegg 5
forespørsler/minutt og 250K input-tokens/minutt.

Døgnkvoten nullstilles ved midnatt Stillehavstid = **kl. 09:00 norsk tid**.
Det betyr at kveldskjøringen (17:30) og neste morgens kjøring (07:30)
faller innenfor samme Gemini-døgn og deler de samme 20 forespørslene.

Designet er derfor budsjettert stramt:

| | Antall |
|---|---|
| Saker per rapport (`MAX_TOTAL_STORIES`) | 12 |
| Kall per kjøring | 3 (1 klassifisering + 2 skrivebunker) |
| Kall per døgn (to kjøringer) | 6 |
| Reserve til retries og manuelle testkjøringer | 14 |

`MAX_GEMINI_CALLS_PER_RUN` i `src/config.py` er en hard stopper som hindrer
at en feilsituasjon spiser opp døgnkvoten. Går kvoten likevel tom, beholdes
siste gyldige utgave med opprinnelig dato. En rå kildeliste brukes bare når
ingen tidligere utgave finnes; den regnes ikke som en gyldig AI-utgave.

**Merk ved testing:** hver manuelle `workflow_dispatch` bruker 3
forespørsler av de 20. Unngå mange testkjøringer på rad.

## Manuell kjøring / test

Actions-fanen → "Daily News Screener" → "Run workflow", velg `morning`
eller `evening` for å teste uten å vente på klokkeslettet.

## Når rapporten viser «rå kildeliste»

Det betyr at Gemini ikke svarte. Sjekk Actions-loggen:

- `HTTP 503` – modellen er overbelastet. Klienten venter 5/15/30 sekunder,
  prøver tre ganger, og bytter så til neste modell i
  `GEMINI_MODEL_FALLBACKS`. Skjer dette vedvarende, sett repo-variabelen
  `GEMINI_MODEL` til en annen Flash-modell.
- `døgnkvoten er brukt opp` – 20 forespørsler er brukt. Kvoten nullstilles
  kl. 09:00 norsk tid. Merk at 07:30-kjøringen trekker fra FORRIGE døgns
  kvote; reserve-cron kl. 10:30 fanger opp dagen etter nullstilling.

Har det allerede kommet en gyldig rapport, også en tidligere dag, beholdes
den. Helsebanneret viser det nye, mislykkede forsøket uten å endre utgavens
opprinnelige dato eller sammendrag.

## Datoer, kildedekning og publiseringskontroll

`health.json` er den offentlige kontrakten for portal og helsebanner:

- `generated_at` er siste gyldige utgaves tidspunkt; `latest_attempt_at` og
  `attempt_status` beskriver siste forsøk. Eldre utgaver uten lagret klokkeslett
  får `generated_at: null`, ikke et gjettet tidspunkt.
- `source_observation_start/end` er RSS-publiseringsdatoer i den viste utgaven.
  Manglende dato/tidssone, fremtidige datoer og artikler eldre enn 24 timer
  tas ikke inn som ferske kilder. Hentetid erstatter aldri publiseringsdato.
- `coverage`/`sources` tilhører utgaven; `attempt_coverage`/`attempt_sources`
  beskriver siste forsøk. Konfigurerte, kontrollerte, brukbare, feilende og
  ønskede utilgjengelige kilder telles separat. Utgiverantall dokumenterer
  ikke uavhengig rapportering eller faktakontroll av et sammendrag.
- `status` er `current`, `degraded` eller `blocked`. `expires_at` er en
  eksplisitt frist: også en teknisk vellykket, beholdt utgave utløper.

Ved blokkert generering publiserer workflowen helseoppdateringen først,
beholder utgaven og markerer deretter kjøringen som mislykket. En ny utgave
skrives bare etter datokontroll og eksisterende kilde-/formatvalidering.
Dette etablerer ikke at AI-sammendragene er faktamessig eller semantisk riktige.

Regresjoner uten modellkall eller nettverk: `python -m unittest discover -s tests -v`.
Disse kjøres på PR, main og før planlagt generering.
