import os
import tempfile
import unittest

from app import app


class AuthTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_registration_and_chat_access(self):
        response = self.client.post(
            "/register",
            json={"username": "alice", "password": "secret123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "registered")

        chat_response = self.client.post(
            "/chat",
            json={"message": "hello", "user_id": "alice"},
        )
        self.assertEqual(chat_response.status_code, 200)
        self.assertIn("reply", chat_response.get_json())

    def test_chat_requires_authentication(self):
        response = self.client.post(
            "/chat",
            json={"message": "hello"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["status"], "not_authenticated")


if __name__ == "__main__":
    unittest.main()
