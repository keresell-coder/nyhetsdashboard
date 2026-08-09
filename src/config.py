"""Kilderegister, kategori/innholdstype-enum og modellkonfigurasjon for nyhetsscreeneren."""

import os

# --- Kilder -----------------------------------------------------------------
# Kun kilder med bekreftet, stabil offentlig RSS-tilgang (verifisert manuelt).
# Kilder uten kjent RSS listes i UNAVAILABLE_SOURCES slik at statusfeltet kan
# vise dem ærlig i stedet for at vi later som de er dekket.

# tier styrer to ting: hvor mange artikler vi henter per kilde, og om
# kilden kan telle som uavhengig redaksjonell bekreftelse.
#   primary_no    - norske hovedkilder
#   international - internasjonale/nordiske redaksjonelle kilder
#   secondary     - institusjoner/primærdata. Teller ALDRI som redaksjonell
#                   bekreftelse, jf. spesifikasjonen; brukes til bakgrunn.
# Strukturen følger en #1 (næringsliv/økonomi) + #2 (bred kvalitet) per
# land/region. region styrer redaksjonell prioritering ("Norden skal
# prioriteres", jf. spesifikasjonen) og hvor mange artikler vi henter.
SOURCES = [
    # --- Norge ---
    {"id": "nrk", "name": "NRK", "url": "https://www.nrk.no/nyheter/siste.rss", "tier": "primary_no", "region": "no"},
    {"id": "dn", "name": "DN", "url": "https://services.dn.no/api/feed/rss/", "tier": "primary_no", "region": "no"},
    {"id": "e24", "name": "E24", "url": "https://e24.no/rss2", "tier": "primary_no", "region": "no"},
    {"id": "vg", "name": "VG", "url": "https://www.vg.no/rss/feed/", "tier": "primary_no", "region": "no"},
    {"id": "aftenposten", "name": "Aftenposten", "url": "https://www.aftenposten.no/rss", "tier": "primary_no", "region": "no"},
    {"id": "tv2", "name": "TV2", "url": "https://www.tv2.no/rss/forsiden/", "tier": "primary_no", "region": "no"},
    {"id": "nettavisen", "name": "Nettavisen", "url": "https://www.nettavisen.no/service/rich-rss", "tier": "primary_no", "region": "no"},

    # --- Norden ---
    {"id": "di", "name": "Dagens Industri", "url": "https://www.di.se/rss", "tier": "international", "region": "nordic"},
    {"id": "svd", "name": "Svenska Dagbladet", "url": "https://www.svd.se/feed/articles.rss", "tier": "international", "region": "nordic"},
    {"id": "borsen", "name": "Børsen", "url": "https://borsen.dk/rss", "tier": "international", "region": "nordic"},
    {"id": "politiken", "name": "Politiken", "url": "https://politiken.dk/rss/senestenyt.rss", "tier": "international", "region": "nordic"},
    {"id": "kauppalehti", "name": "Kauppalehti", "url": "https://feeds.kauppalehti.fi/rss/main", "tier": "international", "region": "nordic"},
    {"id": "hs", "name": "Helsingin Sanomat", "url": "https://www.hs.fi/rss/tuoreimmat.xml", "tier": "international", "region": "nordic"},

    # --- Øvrige internasjonale ---
    {"id": "handelsblatt", "name": "Handelsblatt", "url": "https://www.handelsblatt.com/contentexport/feed/schlagzeilen", "tier": "international", "region": "intl"},
    {"id": "faz", "name": "FAZ", "url": "https://www.faz.net/rss/aktuell/", "tier": "international", "region": "intl"},
    {"id": "ft", "name": "Financial Times", "url": "https://www.ft.com/rss/home", "tier": "international", "region": "intl"},
    {"id": "bbc", "name": "BBC", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "tier": "international", "region": "intl"},
    {"id": "lemonde", "name": "Le Monde", "url": "https://www.lemonde.fr/rss/une.xml", "tier": "international", "region": "intl"},
    {"id": "wsj", "name": "Wall Street Journal", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "tier": "international", "region": "intl"},
    {"id": "nyt", "name": "New York Times", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "tier": "international", "region": "intl"},
    {"id": "nikkei", "name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss/feed/nar", "tier": "international", "region": "intl"},
    {"id": "scmp", "name": "SCMP", "url": "https://www.scmp.com/rss/91/feed", "tier": "international", "region": "intl"},
    {"id": "aljazeera", "name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "tier": "international", "region": "intl"},
    # Global byrådekning. Reuters og AP har begge stengt offentlig RSS
    # (401/DNS borte), så disse to dekker rollen: Bloomberg for marked og
    # makro, France24 for global politikk og konflikt (AFP-basert).
    {"id": "bloomberg", "name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss", "tier": "international", "region": "intl"},
    {"id": "france24", "name": "France 24", "url": "https://www.france24.com/en/rss", "tier": "international", "region": "intl"},

    # --- Sekundær-/bakgrunnskilder (aldri bekreftelse) ---
    {"id": "eu", "name": "EU-kommisjonen", "url": "https://ec.europa.eu/commission/presscorner/api/rss?language=en", "tier": "secondary", "region": "intl"},
    {"id": "eia", "name": "EIA", "url": "https://www.eia.gov/rss/todayinenergy.xml", "tier": "secondary", "region": "intl"},
    {"id": "esa", "name": "ESA", "url": "https://www.esa.int/rssfeed/Our_Activities/Space_News", "tier": "secondary", "region": "intl"},
]

# Norden prioriteres foran øvrige internasjonale kilder når saker må velges
# bort - lavere tall = høyere prioritet. Brukes kun som tiebreak, se under.
REGION_PRIORITY = {"no": 0, "nordic": 1, "intl": 2}

# Nordisk forrang skal være et PÅSLAG, ikke et absolutt førstekriterium.
# Med region som førstekriterium slo en enkeltkilde-sak fra f.eks. Finland
# ut en stor sak omtalt av fire internasjonale redaksjoner - stikk i strid
# med at store internasjonale saker skal komme fram i alle bolker unntatt
# norsk politikk.
#
# Rangeringen er nå: antall uavhengige redaksjonelle kilder + regionpåslag.
#   1 finsk kilde      = 1 + 0.5 = 1.5  -> taper mot
#   2 intl. kilder     = 2 + 0.0 = 2.0
#   2 norske kilder    = 2 + 1.0 = 3.0  -> taper mot
#   4 intl. kilder     = 4 + 0.0 = 4.0
REGION_BONUS = {"no": 1.0, "nordic": 0.5, "intl": 0.0}

# Kilder fra spesifikasjonen som er sjekket, men som ikke har funnet
# offentlig RSS. Vises ærlig i statusfeltet i stedet for at vi gjetter.
UNAVAILABLE_SOURCES = [
    {"id": "dagbladet", "name": "Dagbladet", "reason": "Ingen offentlig RSS-feed funnet"},
    {"id": "klassekampen", "name": "Klassekampen", "reason": "Ingen offentlig RSS-feed funnet"},
    {"id": "abcnyheter", "name": "ABC Nyheter", "reason": "Ingen offentlig RSS-feed funnet"},
    {"id": "reuters", "name": "Reuters", "reason": "Har stengt offentlig RSS (401) – dekkes delvis av Bloomberg og France 24"},
    {"id": "ap", "name": "Associated Press", "reason": "Har stengt offentlig RSS (401)"},
    {"id": "jyllandsposten", "name": "Jyllands-Posten", "reason": "Ingen offentlig RSS-feed funnet"},
    {"id": "lesechos", "name": "Les Echos", "reason": "Blokkerer automatisert henting (403)"},
    {"id": "times", "name": "The Times", "reason": "Ikke tilgjengelig uten abonnement"},
    {"id": "osce", "name": "OSCE", "reason": "Ingen fungerende RSS-feed"},
    {"id": "iea", "name": "IEA", "reason": "Ingen fungerende RSS-feed"},
    {"id": "opec", "name": "OPEC", "reason": "Blokkerer automatisert henting"},
    {"id": "un", "name": "FN", "reason": "Feed ustabil ved verifisering"},
]

# Kilder som ikke kan telle som uavhengig redaksjonell bekreftelse.
NON_CORROBORATING_TIERS = {"secondary"}

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

# Færre artikler fra de brede internasjonale feedene enn fra de norske
# hovedkildene: prioriteringen er norsk/nordisk relevans, og klassifiserings-
# kallet må holdes lite nok til å ikke time ut.
MAX_ARTICLES_PER_SOURCE = 15
MAX_ARTICLES_BY_REGION = {
    "no": 15,
    "nordic": 7,
    "intl": 6,
}
SECONDARY_ARTICLE_LIMIT = 4
HEADLINE_MAX_WORDS = 10
INGRESS_MAX_WORDS = 50
# Spesifikasjonen ber om 200-250 ord. Vi ber Gemini om det i prompten, men
# godtar et bredere spenn ved validering: å kaste en ellers god sak fordi
# den er 15 ord for lang er dårligere redaksjonelt enn å slippe den
# gjennom. Ved forrige kjøring falt 6 av 18 saker på dette alene.
SUMMARY_MIN_WORDS = 120
SUMMARY_MAX_WORDS = 320
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

# Terskel for at to overskrifter fra ULIKE redaksjoner regnes som samme
# hendelse (overlap-koeffisient, 0-1). 0.6 er satt bevisst konservativt:
# heller gå glipp av en sammenslåing enn å slå sammen to ulike saker og
# feilaktig påstå bred kildedekning, jf. spesifikasjonens krav om at
# flerkilde-dekning faktisk skal kunne dokumenteres.
CLUSTER_SIMILARITY_THRESHOLD = 0.6

# Tak på hvor mange klynger som sendes til klassifisering. Med 21 kilder kan
# innhentingen gi ~190 artikler; et for stort kall risikerer tidsavbrudd (det
# var nettopp det som feilet på skrivekallet tidligere). Klyngene er sortert
# med bredest dekkede saker først, så det er halen som kuttes.
MAX_CLUSTERS_TO_CLASSIFY = 120

# Hvor mange dager tilbake vi husker saker for å kunne merke dem som
# "videreført fra forrige rapport".
CONTINUITY_DAYS = 4

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

# Innen rom-/cyberkategorien skal satellittkommunikasjon prioriteres foran
# jordobservasjon når antall saker må begrenses, jf. spesifikasjonen.
SUB_PRIORITY_RANK = {
    "satcom": 0,
    "cyber": 1,
    "jordobservasjon_ovrig": 2,
    "ingen": 3,
}

TIMEZONE = "Europe/Oslo"
