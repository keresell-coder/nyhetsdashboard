import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src import config, gemini_client, health, ingest, pipeline, prefilter, render, state
from scripts import schedule_guard

NOW = datetime(2026, 9, 9, 8, tzinfo=timezone.utc)
SOURCE = {"id": "test", "name": "Test publisher", "url": "https://example.test/feed"}


def article(number=1, published=NOW - timedelta(hours=1), source=SOURCE):
    return ingest.Article(number, source["id"], source["name"], "A relevant market event", "Source excerpt", f"https://example.test/news/{number}", published)


def checked(articles, status):
    status["source_attempts"] = [{"source_id": SOURCE["id"], "attempted_at": NOW.isoformat()}]
    return articles


def classifications(clusters):
    return [{"article_id": c[0].article_id, "promote": True, "main_category": "okonomi", "content_type": "nyhet"} for c in clusters]


def drafts(groups, status):
    return [{"group_key": g["group_key"], "headline": "Market source report", "ingress": "A dated source supports this summary.", "summary": " ".join(["Evidence"] * 125), "source_article_ids": [a.article_id for a in g["articles"]]} for g in groups]


class HealthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.index = self.root / "index.html"
        self.health_file = self.root / "health.json"
        for target, value in [("src.config.SOURCES", [SOURCE]), ("src.config.UNAVAILABLE_SOURCES", []),
                              ("src.pipeline.INDEX_PATH", str(self.index)), ("src.health.HEALTH_PATH", str(self.health_file)),
                              ("src.state.STATE_DIR", str(self.root / "state")), ("scripts.schedule_guard.STATE_DIR", str(self.root / "state"))]:
            mock = patch(target, value)
            mock.start()
            self.addCleanup(mock.stop)

    def run_pipeline(self, articles=None, *, date=NOW, classify=classifications, draft=drafts, run_type="morning"):
        with patch("src.pipeline._now_oslo", return_value=date), patch.dict("os.environ", {"RUN_TYPE": run_type}), \
             patch("src.ingest.fetch_all", side_effect=lambda s: checked([article()] if articles is None else articles, s)), \
             patch("src.gemini_client.classify_articles", side_effect=classify), patch("src.gemini_client.draft_stories", side_effect=draft):
            pipeline.run()
        return json.loads(self.health_file.read_text())

    def test_normal_edition_has_actual_generation_source_dates_and_coverage(self):
        manifest = self.run_pipeline()
        self.assertEqual(manifest["status"], "current")
        self.assertEqual(manifest["generated_at"], NOW.isoformat())
        self.assertEqual(manifest["source_observation_end"], article().published.isoformat())
        self.assertEqual(manifest["coverage"]["usable_source_count"], 1)
        self.assertEqual(manifest["research_validation"], "not_established")
        health.validate_manifest(manifest, require_available=True)
        self.assertIn('id="source-health-status"', self.index.read_text())
        self.assertNotIn("uavhengige kilder", self.index.read_text())
        self.assertEqual(state.last_good_edition("2026-09-09")["generated_at"], NOW.isoformat())

    def test_fetch_failure_next_day_retains_exact_html_and_original_edition_date(self):
        self.run_pipeline()
        original = self.index.read_bytes()
        result = self.run_pipeline([], date=NOW + timedelta(days=1))
        self.assertEqual(self.index.read_bytes(), original)
        self.assertEqual(result["generated_at"], NOW.isoformat())
        self.assertEqual(result["latest_attempt_at"], (NOW + timedelta(days=1)).isoformat())
        self.assertEqual(result["edition_date"], "2026-09-09")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["attempt_status"], "failed")
        self.assertEqual(result["coverage"]["usable_source_count"], 1)
        self.assertEqual(result["attempt_coverage"]["usable_source_count"], 0)
        self.assertFalse(schedule_guard.already_ran("2026-09-10", "morning"))
        with self.assertRaisesRegex(ValueError, "Generation blocked"):
            health.validate_manifest(result, require_available=True)

    def test_classification_and_draft_failure_never_overwrite_last_good(self):
        self.run_pipeline()
        original = self.index.read_bytes()
        for stage in ("classify", "draft"):
            with self.subTest(stage=stage):
                result = self.run_pipeline(**{stage: gemini_client.GeminiError("unavailable")})
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(self.index.read_bytes(), original)

    def test_invalid_or_empty_model_output_never_overwrites_last_good(self):
        self.run_pipeline()
        original = self.index.read_bytes()
        for options in ({"classify": lambda _: []}, {"draft": lambda *args: []}, {"draft": lambda *args: [{"group_key": "invented", "source_article_ids": [1]}]}):
            with self.subTest(options=options):
                self.assertEqual(self.run_pipeline(**options)["status"], "blocked")
                self.assertEqual(self.index.read_bytes(), original)

    def test_no_valid_source_dates_on_first_attempt_has_no_fake_edition(self):
        result = self.run_pipeline([article(published=None), article(2, NOW + timedelta(minutes=1)), article(3, NOW - timedelta(days=2))])
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["generated_at"])
        self.assertIsNone(result["source_observation_end"])
        self.assertIsNone(state.last_good_edition("2026-09-09"))
        self.assertEqual(result["attempt_coverage"]["future_article_count"], 1)
        self.assertEqual(result["attempt_coverage"]["undated_article_count"], 1)
        self.assertIn("Ingen gyldig datert utgave", self.index.read_text())

    def test_partial_source_coverage_is_degraded_not_full_coverage(self):
        missing = {"id": "missing", "name": "Missing", "url": "https://example.test/missing"}
        with patch("src.config.SOURCES", [SOURCE, missing]), patch("src.config.UNAVAILABLE_SOURCES", [{"id": "unavailable", "name": "Unavailable", "reason": "No verified feed"}]):
            result = self.run_pipeline()
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["coverage"]["configured_source_count"], 2)
        self.assertEqual(result["coverage"]["desired_source_count"], 3)
        self.assertEqual(result["coverage"]["missing_source_count"], 2)
        self.assertEqual(result["sources"][1]["status"], "not_checked")

    def test_partial_draft_failure_publishes_dated_subset_as_degraded(self):
        def partial(groups, status):
            status["draft_batch_failures"] = 1
            return drafts(groups, status)
        result = self.run_pipeline(draft=partial)
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["attempt_status"], "completed")
        self.assertIsNotNone(result["source_observation_end"])

    def test_failed_source_cannot_count_as_usable_even_if_candidates_exist(self):
        status = {"source_errors": [{"source": SOURCE["name"], "error": "failed"}]}
        checked([article()], status)
        result = health.source_coverage([article()], status, NOW)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["coverage"]["usable_source_count"], 0)
        self.assertEqual(result["coverage"]["failed_source_count"], 1)

    def test_legacy_edition_gets_monitor_but_never_an_invented_generation_time(self):
        original = '<html><body><p>Oppdatert 08.09.2026 kl. 07:30</p><p>Original body</p></body></html>'
        self.index.write_text(original)
        state.record_run("2026-09-08", "morning", [{"story_id": "old", "sources": []}], {})
        result = self.run_pipeline([])
        self.assertIsNone(result["generated_at"])
        self.assertEqual(result["edition_date"], "2026-09-08")
        self.assertIn("legacy_edition_time_unverified", [x["reason"] for x in result["issues"]])
        self.assertEqual(self.index.read_text(), render.ensure_health_monitor(original))
        self.assertEqual(render.ensure_health_monitor(self.index.read_text()), self.index.read_text())

    def test_empty_evening_delta_is_a_completed_edition_not_another_retry(self):
        self.run_pipeline()
        result = self.run_pipeline(date=NOW + timedelta(hours=4), run_type="evening")
        self.assertEqual(result["edition_type"], "evening")
        self.assertTrue(schedule_guard.already_ran("2026-09-09", "evening"))
        edition = state.last_good_edition("2026-09-09")
        self.assertEqual(edition["stories"], [])
        self.assertEqual(len(edition["displayed_stories"]), 1)

    def test_manifest_rejects_future_timestamp_and_false_coverage(self):
        result = self.run_pipeline()
        result["generated_at"] = (NOW + timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "future-dated"):
            health.validate_manifest(result)
        result["generated_at"] = NOW.isoformat()
        result["coverage"]["usable_source_count"] += 1
        with self.assertRaisesRegex(ValueError, "Coverage counts"):
            health.validate_manifest(result)

    def test_prefilter_never_substitutes_fetch_time_for_missing_or_future_dates(self):
        good = article()
        self.assertEqual(prefilter.prefilter([good, article(2, None), article(3, NOW + timedelta(seconds=1)), article(4, NOW - timedelta(hours=25))], now=NOW), [good])
        self.assertIsNone(ingest._parse_pubdate("2026-09-09T08:00:00"))
        self.assertEqual(ingest._parse_pubdate("2026-09-09T10:00:00+02:00"), NOW)

    def test_python_311_syntax(self):
        for path in [*Path("src").glob("*.py"), *Path("scripts").glob("*.py")]:
            with self.subTest(path=path):
                ast.parse(path.read_text(), filename=str(path), feature_version=(3, 11))


if __name__ == "__main__":
    unittest.main()
