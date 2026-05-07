import json
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db_helpers import add_task_audit_entry, normalize_task_status  # noqa: E402


class FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))


class NormalizeTaskStatusTests(unittest.TestCase):
    def test_empty_status_defaults_to_new(self):
        self.assertEqual(normalize_task_status(None), "NEW")
        self.assertEqual(normalize_task_status(""), "NEW")

    def test_status_is_case_insensitive(self):
        self.assertEqual(normalize_task_status("done"), "DONE")
        self.assertEqual(normalize_task_status("in_progress"), "IN_PROGRESS")

    def test_invalid_status_raises_400(self):
        with self.assertRaises(HTTPException) as ctx:
            normalize_task_status("blocked")

        self.assertEqual(ctx.exception.status_code, 400)


class AuditEntryTests(unittest.TestCase):
    def test_add_task_audit_entry_serializes_json_values(self):
        cur = FakeCursor()

        add_task_audit_entry(
            cur,
            task_id=10,
            actor_id=20,
            event_type="UPDATE",
            field="title",
            old_value={"title": "Старое"},
            new_value={"title": "Новое"},
        )

        self.assertEqual(len(cur.calls), 1)
        _query, params = cur.calls[0]
        self.assertEqual(params[:4], (10, 20, "UPDATE", "title"))
        self.assertEqual(json.loads(params[4]), {"title": "Старое"})
        self.assertEqual(json.loads(params[5]), {"title": "Новое"})

    def test_add_task_audit_entry_keeps_null_values(self):
        cur = FakeCursor()

        add_task_audit_entry(cur, 1, 2, "CREATE", None, None, {"status": "NEW"})

        _query, params = cur.calls[0]
        self.assertIsNone(params[3])
        self.assertIsNone(params[4])
        self.assertEqual(json.loads(params[5]), {"status": "NEW"})


if __name__ == "__main__":
    unittest.main()
