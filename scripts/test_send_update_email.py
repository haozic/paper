import unittest
from unittest.mock import patch

from scripts import send_update_email as mail


make_digest = mail.make_digest
new_items = mail.new_items


class UpdateEmailTests(unittest.TestCase):
    def test_no_new_articles_produces_no_notification_items(self):
        old = [{"u": "a", "t": "旧文章"}]
        self.assertEqual(new_items(old, old.copy()), [])

    def test_digest_lists_only_new_articles_and_real_revision(self):
        old = [{"u": "a", "t": "旧文章"}]
        current = old + [{"u": "b", "t": "新文章", "y": 2026, "i": 6}]
        changes = [("旗帜", new_items(old, current))]
        subject, body = make_digest(changes, "abc123", "haozic/paper", "42")
        self.assertIn("旗帜 1 篇", subject)
        self.assertIn("新文章（2026 年第 6 期）", body)
        self.assertNotIn("旧文章", body)
        self.assertIn("/commit/abc123", body)
        self.assertIn("/actions/runs/42", body)

    def test_sends_one_qq_email_after_new_article(self):
        def items_at(revision, path):
            if path != "data/qs/meta.json":
                return []
            return [] if revision == "HEAD^" else [{"u": "new", "t": "新增文章", "y": 2026, "i": 1}]

        env = {
            "UPDATE_MAIL_USER": "reader@qq.com",
            "UPDATE_MAIL_PASSWORD": "test-authorization-code",
            "GITHUB_REPOSITORY": "haozic/paper",
            "GITHUB_RUN_ID": "42",
        }
        with patch.dict(mail.os.environ, env, clear=True), \
             patch.object(mail, "items_at", side_effect=items_at), \
             patch.object(mail.subprocess, "check_output", return_value="abc123\n"), \
             patch.object(mail.smtplib, "SMTP_SSL") as smtp:
            self.assertEqual(mail.main(), 0)
        smtp.assert_called_once()
        self.assertEqual(smtp.call_args.args[:2], ("smtp.qq.com", 465))
        connection = smtp.return_value.__enter__.return_value
        connection.login.assert_called_once_with("reader@qq.com", "test-authorization-code")
        message = connection.send_message.call_args.args[0]
        self.assertEqual(message["To"], "reader@qq.com")
        self.assertIn("新增文章", message.get_content())


if __name__ == "__main__":
    unittest.main()
