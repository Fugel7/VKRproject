import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import helpers as bot_helpers  # noqa: E402


class BotHelperTests(unittest.TestCase):
    def test_build_startapp_link_normalizes_names(self):
        link = bot_helpers.build_startapp_link("@demo_bot", "/tracker", "project-key")

        self.assertEqual(link, "https://t.me/demo_bot/tracker?startapp=project-key")

    def test_should_attempt_task_extraction_requires_action_marker(self):
        self.assertTrue(bot_helpers.should_attempt_task_extraction("сделай кнопку входа"))
        self.assertFalse(bot_helpers.should_attempt_task_extraction(""))
        self.assertFalse(bot_helpers.should_attempt_task_extraction("просто обсуждаем проект"))

    def test_extract_text_from_pdf_bytes_returns_empty_on_invalid_pdf(self):
        self.assertEqual(bot_helpers.extract_text_from_pdf_bytes(b"not a pdf"), "")

    def test_extract_text_from_docx_bytes_returns_empty_on_invalid_docx(self):
        self.assertEqual(bot_helpers.extract_text_from_docx_bytes(b"not a docx"), "")


if __name__ == "__main__":
    unittest.main()
