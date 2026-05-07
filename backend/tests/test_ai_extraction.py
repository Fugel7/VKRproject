import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai_extraction import (  # noqa: E402
    _coerce_hours,
    _extract_json_object,
    _normalize_ai_tasks,
    extract_tasks_by_rules,
    filter_extracted_tasks,
)


class JsonExtractionTests(unittest.TestCase):
    def test_extract_json_object_accepts_clean_json(self):
        payload = _extract_json_object('{"tasks": [{"title": "A"}]}')

        self.assertEqual(payload["tasks"][0]["title"], "A")

    def test_extract_json_object_accepts_json_inside_text(self):
        payload = _extract_json_object('prefix {"tasks": []} suffix')

        self.assertEqual(payload, {"tasks": []})

    def test_extract_json_object_rejects_empty_response(self):
        with self.assertRaises(HTTPException) as ctx:
            _extract_json_object("")

        self.assertEqual(ctx.exception.status_code, 502)


class TaskNormalizationTests(unittest.TestCase):
    def test_normalize_ai_tasks_cleans_invalid_items(self):
        raw = [
            {"title": "  Сделать API  ", "description": " endpoint ", "status": "done", "execution_hours": "3 часа"},
            {"title": "", "description": "empty title"},
            {"title": "Invalid status", "status": "BROKEN", "execution_hours": -10},
            "not a dict",
        ]

        normalized = _normalize_ai_tasks(raw)

        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0]["title"], "Сделать API")
        self.assertEqual(normalized[0]["description"], "endpoint")
        self.assertEqual(normalized[0]["status"], "DONE")
        self.assertEqual(normalized[0]["execution_hours"], 3)
        self.assertEqual(normalized[1]["status"], "NEW")
        self.assertIsNone(normalized[1]["execution_hours"])

    def test_normalize_ai_tasks_limits_title_and_total_count(self):
        raw = [{"title": f"Задача {index} " + ("x" * 300)} for index in range(20)]

        normalized = _normalize_ai_tasks(raw)

        self.assertEqual(len(normalized), 15)
        self.assertLessEqual(len(normalized[0]["title"]), 180)

    def test_coerce_hours_handles_common_values(self):
        self.assertEqual(_coerce_hours("12 часов"), 12)
        self.assertEqual(_coerce_hours(2.6), 3)
        self.assertEqual(_coerce_hours(1200), 999)
        self.assertIsNone(_coerce_hours("без оценки"))
        self.assertIsNone(_coerce_hours(0))


class TaskFilteringTests(unittest.TestCase):
    def test_filter_extracted_tasks_removes_household_items(self):
        tasks = [
            {"title": "buy milk", "description": "buy milk after work"},
            {"title": "fix backend api", "description": "fix backend endpoint"},
        ]

        filtered = filter_extracted_tasks(tasks, "mixed request", "CRM project")

        self.assertEqual(filtered, [tasks[1]])

    def test_filter_extracted_tasks_limits_result_size(self):
        tasks = [{"title": f"fix backend api {index}", "description": "project task"} for index in range(25)]

        filtered = filter_extracted_tasks(tasks, "backend tasks", "CRM project")

        self.assertEqual(len(filtered), 15)


class RuleBasedExtractionTests(unittest.TestCase):
    def test_rule_based_extraction_creates_project_task(self):
        text = "сделай кнопку входа на странице авторизации"

        tasks = extract_tasks_by_rules(text)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["status"], "NEW")
        self.assertIsNone(tasks[0]["execution_hours"])
        self.assertIn("кнопку входа", tasks[0]["title"].lower())

    def test_rule_based_extraction_ignores_non_project_text(self):
        text = "сделай чай и купи хлеб"

        self.assertEqual(extract_tasks_by_rules(text), [])


if __name__ == "__main__":
    unittest.main()
