"""Source-owned health manifest; edition time is separate from attempt time."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src import config

HEALTH_PATH = "health.json"


def source_coverage(articles, status, now):
    errors = {e["source"]: e.get("error", "fetch failed") for e in status.get("source_errors", [])}
    checked = {s["source_id"]: s for s in status.get("source_attempts", [])}
    records = []
    for source in config.SOURCES:
        candidates = [a for a in articles if a.source_id == source["id"]]
        dated = [a for a in candidates if a.published is not None]
        usable = [a for a in dated if timedelta(0) <= now - a.published <= timedelta(hours=config.LOOKBACK_HOURS) and a.link]
        future = [a for a in dated if a.published > now]
        stale = [a for a in dated if now - a.published > timedelta(hours=config.LOOKBACK_HOURS)]
        reason = "fetch_failed" if source["name"] in errors else "not_checked" if source["id"] not in checked else "current" if usable else "no_current_dated_articles"
        records.append({
            "source_id": source["id"], "name": source["name"], "url": source["url"],
            "status": reason, "attempted_at": checked.get(source["id"], {}).get("attempted_at"),
            "candidate_count": len(candidates), "usable_article_count": len(usable),
            "undated_article_count": len(candidates) - len(dated),
            "future_article_count": len(future), "stale_article_count": len(stale),
            "latest_published_at": max((a.published for a in dated), default=None).isoformat() if dated else None,
            "earliest_usable_published_at": min((a.published for a in usable), default=None).isoformat() if usable else None,
            "latest_usable_published_at": max((a.published for a in usable), default=None).isoformat() if usable else None,
            "error": errors.get(source["name"]),
        })
    usable_count = sum(r["status"] == "current" for r in records)
    known_unavailable = list(config.UNAVAILABLE_SOURCES)
    coverage = {
        "configured_source_count": len(records), "desired_source_count": len(records) + len(known_unavailable),
        "checked_source_count": sum(r["attempted_at"] is not None for r in records), "usable_source_count": usable_count,
        "missing_source_count": len(records) - usable_count + len(known_unavailable),
        "failed_source_count": sum(r["status"] == "fetch_failed" for r in records),
        "known_unavailable_source_count": len(known_unavailable),
        "usable_article_count": sum(r["usable_article_count"] for r in records if r["status"] == "current"),
        "undated_article_count": sum(r["undated_article_count"] for r in records),
        "future_article_count": sum(r["future_article_count"] for r in records),
        "stale_article_count": sum(r["stale_article_count"] for r in records),
    }
    quality = "blocked" if not usable_count else "current" if not coverage["missing_source_count"] and not coverage["undated_article_count"] and not coverage["future_article_count"] else "degraded"
    return {"status": quality, "coverage": coverage, "sources": records, "known_unavailable_sources": known_unavailable}


def manifest(edition, attempt_at, source_health, *, failure=None):
    edition_health = (edition or {}).get("source_health") or {}
    displayed_sources = [s for story in (edition or {}).get("displayed_stories", (edition or {}).get("stories", [])) for s in story.get("sources", [])]
    observations = [s["published_at"] for s in displayed_sources if s.get("published_at")]
    missing_dates = len(displayed_sources) - len(observations)
    status = "blocked" if failure or not edition or not edition.get("generated_at") else source_health["status"]
    issues = [{"source": r["source_id"], "reason": r["status"]} for r in source_health["sources"] if r["status"] != "current"]
    issues.extend({"source": s["id"], "reason": s["reason"]} for s in source_health.get("known_unavailable_sources", []))
    if failure:
        issues.insert(0, {"source": "generation", "reason": failure})
    if edition and not edition.get("generated_at"):
        issues.insert(0, {"source": "edition", "reason": "legacy_edition_time_unverified"})
    if missing_dates:
        issues.append({"source": "displayed_edition", "reason": "missing_publication_dates", "count": missing_dates})
        if status == "current":
            status = "degraded"
    if not observations:
        status = "blocked"
    return {
        "schema_version": "source-health-v1", "status": status,
        "generated_at": (edition or {}).get("generated_at"),
        "edition_date": (edition or {}).get("edition_date"),
        "edition_type": (edition or {}).get("edition_type"),
        "latest_attempt_at": attempt_at, "attempt_status": "failed" if failure else "completed",
        "expires_at": (datetime.fromisoformat(edition["generated_at"]) + timedelta(hours=24)).isoformat() if edition and edition.get("generated_at") else None,
        "source_observation_start": min(observations) if observations else None,
        "source_observation_end": max(observations) if observations else None,
        "displayed_source_reference_count": len(displayed_sources),
        "displayed_source_missing_date_count": missing_dates,
        "coverage": edition_health.get("coverage", {}),
        "sources": edition_health.get("sources", []),
        "attempt_coverage": source_health["coverage"], "attempt_sources": source_health["sources"],
        "issues": issues, "research_validation": "not_established",
        "next_expected_update_hours": 24,
        "observation_date_basis": "RSS publication timestamps; missing dates are not replaced with fetch/attempt times. Publisher counts do not establish independent reporting.",
    }


def write_manifest(payload):
    target = Path(HEALTH_PATH)
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temp, target)


def validate_manifest(payload, *, require_available=False):
    if payload.get("status") not in {"current", "degraded", "blocked"}:
        raise ValueError("Unknown publication health status")
    attempted = datetime.fromisoformat(payload["latest_attempt_at"])
    if attempted.tzinfo is None:
        raise ValueError("Attempt timestamp requires a timezone")
    generated = payload.get("generated_at")
    if generated and datetime.fromisoformat(generated) > attempted:
        raise ValueError("Edition is future-dated relative to attempt")
    if payload["status"] != "blocked":
        if not generated or not payload.get("source_observation_end") or not payload.get("coverage", {}).get("usable_source_count"):
            raise ValueError("An available edition requires dated source evidence")
        if datetime.fromisoformat(payload["source_observation_end"]) > attempted:
            raise ValueError("Future-dated article in edition")
        if datetime.fromisoformat(payload["source_observation_start"]) > datetime.fromisoformat(payload["source_observation_end"]):
            raise ValueError("Reversed observation range")
        counts = payload["coverage"]
        sources = payload["sources"]
        if counts["configured_source_count"] != len(sources) or counts["usable_source_count"] != sum(s["status"] == "current" for s in sources):
            raise ValueError("Coverage counts differ from source evidence")
    if require_available and payload["status"] == "blocked":
        raise ValueError("Generation blocked; previous edition retained. See health.json for the failed attempt.")


if __name__ == "__main__":
    import sys
    validate_manifest(json.loads(Path(HEALTH_PATH).read_text(encoding="utf-8")), require_available="--require-available" in sys.argv)
