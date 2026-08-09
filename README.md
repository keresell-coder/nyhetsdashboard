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

## Manuell kjøring / test

Actions-fanen → "Daily News Screener" → "Run workflow", velg `morning`
eller `evening` for å teste uten å vente på klokkeslettet.
