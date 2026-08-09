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
MAX_STORIES_PER_CATEGORY = 6

TIMEZONE = "Europe/Oslo"
