"""JSON-schema (Gemini responseSchema) for de to strukturerte LLM-kallene.

Gemini skal ALDRI returnere URL-er eller frittstående kilder - kun
article_id-er den fikk oppgitt i samme kall. Python slår opp faktisk URL
ved rendering (se render.py) og validate.py avviser enhver referanse til en
article_id som ikke faktisk ble sendt inn.
"""

from src import config

CLASSIFY_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        # Representativ article_id for klyngen (se cluster.py).
        "article_id": {"type": "integer"},
        "content_type": {"type": "string", "enum": config.CONTENT_TYPES},
        "main_category": {"type": "string", "enum": config.CATEGORIES},
        "secondary_tags": {
            "type": "array",
            "items": {"type": "string", "enum": config.CATEGORIES},
            "maxItems": 2,
        },
        "sub_priority": {
            "type": "string",
            "enum": ["satcom", "cyber", "jordobservasjon_ovrig", "ingen"],
        },
        "likely_duplicate_of": {"type": "integer"},
        "promote": {"type": "boolean"},
    },
    "required": ["article_id", "content_type", "main_category", "promote"],
}

CLASSIFY_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": CLASSIFY_ITEM_SCHEMA,
        }
    },
    "required": ["classifications"],
}

STORY_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "group_key": {"type": "string"},
        "headline": {"type": "string"},
        "ingress": {"type": "string"},
        "summary": {"type": "string"},
        "source_article_ids": {
            "type": "array",
            "items": {"type": "integer"},
        },
    },
    "required": ["group_key", "headline", "ingress", "summary", "source_article_ids"],
}

DRAFT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": STORY_ITEM_SCHEMA,
        }
    },
    "required": ["stories"],
}
