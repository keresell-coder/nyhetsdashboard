"""Kilderegister, kategori/innholdstype-enum og modellkonfigurasjon for nyhetsscreeneren."""

import os

# --- Kilder -----------------------------------------------------------------
# Kun kilder med bekreftet, stabil offentlig RSS-tilgang (verifisert manuelt).
# Kilder uten kjent RSS listes i UNAVAILABLE_SOURCES slik at statusfeltet kan
# vise dem ærlig i stedet for at vi later som de er dekket.

SOURCES = [
    {"id": "nrk", "name": "NRK", "url": "https://www.nrk.no/nyheter/siste.rss", "tier": "primary_no"},
    {"id": "dn", "name": "DN", "url": "https://services.dn.no/api/feed/rss/", "tier": "primary_no"},
    {"id": "e24", "name": "E24", "url": "https://e24.no/rss2", "tier": "primary_no"},
    {"id": "vg", "name": "VG", "url": "https://www.vg.no/rss/feed/", "tier": "primary_no"},
    {"id": "aftenposten", "name": "Aftenposten", "url": "https://www.aftenposten.no/rss", "tier": "primary_no"},
    {"id": "tv2", "name": "TV2", "url": "https://www.tv2.no/rss/forsiden/", "tier": "primary_no"},
    {"id": "nettavisen", "name": "Nettavisen", "url": "https://www.nettavisen.no/service/rich-rss", "tier": "primary_no"},
]

UNAVAILABLE_SOURCES = [
    {"id": "dagbladet", "name": "Dagbladet", "reason": "Ingen offentlig RSS-feed funnet"},
    {"id": "klassekampen", "name": "Klassekampen", "reason": "Ingen offentlig RSS-feed funnet"},
    {"id": "abcnyheter", "name": "ABC Nyheter", "reason": "Ingen offentlig RSS-feed funnet"},
]

# --- Kategorier og innholdstyper ---------------------------------------------
# De 8 fagområdene fra spesifikasjonen.

CATEGORIES = [
    "norsk_politikk",
    "nordisk_politikk",
    "internasjonal_politikk",
    "sikkerhet_forsvar",
    "okonomi_makro",
    "geopolitikk",
    "rom_cyber",
    "sport",
]

CATEGORY_LABELS = {
    "norsk_politikk": "Norsk politikk",
    "nordisk_politikk": "Nordisk politikk",
    "internasjonal_politikk": "Internasjonal politikk",
    "sikkerhet_forsvar": "Sikkerhet og forsvar",
    "okonomi_makro": "Økonomi og makro",
    "geopolitikk": "Geopolitikk",
    "rom_cyber": "Rom- og cyberteknologi og -politikk",
    "sport": "Sport",
}

# Finkornet innholdstype som Gemini klassifiserer til.
CONTENT_TYPES = [
    "nyhet",
    "reportasje",
    "intervju",
    "analyse_redaksjonell",
    "kommentar",
    "leder",
    "ytring",
    "kronikk",
    "debattinnlegg",
    "analyse_vurderende",
]

CONTENT_TYPE_LABELS = {
    "nyhet": "Nyhet",
    "reportasje": "Reportasje",
    "intervju": "Intervju",
    "analyse_redaksjonell": "Analyse",
    "kommentar": "Kommentar",
    "leder": "Leder",
    "ytring": "Ytring",
    "kronikk": "Kronikk",
    "debattinnlegg": "Debattinnlegg",
    "analyse_vurderende": "Analyse (vurderende)",
}

# Deterministisk mapping innholdstype -> hovedgruppe. Gemini kan ikke motsi
# denne ved å skrive noe annet i selve teksten; rendering stoler kun på dette.
CONTENT_GROUP = {
    "nyhet": "redaksjonelt",
    "reportasje": "redaksjonelt",
    "intervju": "redaksjonelt",
    "analyse_redaksjonell": "redaksjonelt",
    "kommentar": "kommentar_debatt",
    "leder": "kommentar_debatt",
    "ytring": "kommentar_debatt",
    "kronikk": "kommentar_debatt",
    "debattinnlegg": "kommentar_debatt",
    "analyse_vurderende": "kommentar_debatt",
}

COMMENT_DISCLAIMER = "Kommentarstoff – ikke selvstendig redaksjonell bekreftelse."

# --- Gemini-konfigurasjon -----------------------------------------------------
# Modellnavn styres via miljøvariabel (satt fra en GitHub Actions repo Variable),
# aldri hardkodet, siden Gemini sine gratis-modeller endres jevnlig.
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# --- Kjøreparametere ----------------------------------------------------------
LOOKBACK_HOURS = 24
MAX_ARTICLES_PER_SOURCE = 15
HEADLINE_MAX_WORDS = 10
INGRESS_MAX_WORDS = 50
SUMMARY_MIN_WORDS = 150
SUMMARY_MAX_WORDS = 280
MAX_STORIES_PER_CATEGORY = 4
TOP_STORIES_COUNT = 3

# --- Gemini-kvotebudsjett ------------------------------------------------
# REELLE gratiskvoter, avlest i Google AI Studio (aistudio.google.com ->
# Rate Limit) for Gemini 3.6 Flash, ikke fra nettartikler:
#   RPM  5 forespørsler/minutt
#   RPD  20 forespørsler/DØGN
#   TPM  250K input-tokens/minutt
#
# Døgnkvoten nullstilles ved midnatt Stillehavstid = kl. 09:00 norsk tid.
# Konsekvens: kveldskjøringen (17:30) og NESTE morgens kjøring (07:30)
# faller innenfor samme Gemini-døgn og deler de samme 20 forespørslene.
# Budsjettet under må derfor dekke to kjøringer, med rom for retries.
#
# Med MAX_TOTAL_STORIES=12 og DRAFT_BATCH_SIZE=6 blir det:
#   1 klassifiseringskall + 2 skrivekall = 3 per kjøring = 6 per døgn.
# Det gir 14 forespørsler i reserve til retries og manuelle testkjøringer.
MAX_TOTAL_STORIES = 12
DRAFT_BATCH_SIZE = 6
MAX_GEMINI_CALLS_PER_RUN = 6

# Grov tilnærming til spesifikasjonens redaksjonelle prioriteringsrekkefølge,
# brukt til å plukke ut "Viktigste saker i dag". Lavere tall = høyere
# prioritet. Fullstendig 8-trinns trimming kommer i Fase 3.
CATEGORY_PRIORITY = {
    "sikkerhet_forsvar": 1,
    "norsk_politikk": 2,
    "geopolitikk": 3,
    "okonomi_makro": 4,
    "nordisk_politikk": 5,
    "rom_cyber": 6,
    "internasjonal_politikk": 7,
    "sport": 8,
}

TIMEZONE = "Europe/Oslo"
