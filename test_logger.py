import os
import sqlite3
import tempfile
import unittest

import logger


class LoggerTests(unittest.TestCase):
    def test_init_db_and_log_interaction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test_chat_logs.db")

            logger.init_db(db_path)

            conn = sqlite3.connect(db_path)
            table_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='interaction_logs'"
            ).fetchone()
            conn.close()

            self.assertIsNotNone(table_exists)

            logger.log_interaction(
                prompt="Hello",
                response="Hi there",
                model_used="test-model",
                user_id="tester",
                db_path=db_path,
                export_to_desktop=False,
            )

            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT prompt, response, model_used, status FROM interaction_logs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()

            self.assertEqual(row[0], "Hello")
            self.assertEqual(row[1], "Hi there")
            self.assertEqual(row[2], "test-model")
            self.assertEqual(row[3], "SUCCESS")

    def test_export_logs_to_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test_chat_logs.db")
            backup_dir = os.path.join(temp_dir, "backups")

            logger.init_db(db_path)
            logger.log_interaction(
                prompt="Export me",
                response="Done",
                model_used="test-model",
                user_id="tester",
                db_path=db_path,
                export_to_desktop=False,
            )

            export_path = logger.export_daily_backup(db_path=db_path, backup_dir=backup_dir)

            self.assertTrue(os.path.exists(export_path))
            with open(export_path, "r", encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("Export me", content)


if __name__ == "__main__":
    unittest.main()
