"""
Tests for agent-improve CLI.
Run with: python3 -m pytest test_agent_improve.py -v
or:        python3 -m unittest -v test_agent_improve.py
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Allow importing agent_improve from the same directory
sys.path.insert(0, str(Path(__file__).parent))
import agent_improve


class TestScoreMatrix(unittest.TestCase):
    def test_low_ambition_caps_at_two(self):
        self.assertEqual(agent_improve.SCORE_MATRIX[("LOW", "EXCELLENT")], 2)
        self.assertEqual(agent_improve.SCORE_MATRIX[("LOW", "GOOD")], 2)
        self.assertEqual(agent_improve.SCORE_MATRIX[("LOW", "ADEQUATE")], 1)
        self.assertEqual(agent_improve.SCORE_MATRIX[("LOW", "POOR")], 1)

    def test_high_excellent_is_five(self):
        self.assertEqual(agent_improve.SCORE_MATRIX[("HIGH", "EXCELLENT")], 5)

    def test_medium_good_is_three(self):
        self.assertEqual(agent_improve.SCORE_MATRIX[("MEDIUM", "GOOD")], 3)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_store = agent_improve.STORE_DIR
        self.orig_db = agent_improve.DB_PATH
        self.orig_skills = agent_improve.SKILLS_DIR
        self.orig_sessions = agent_improve.SESSIONS_DIR
        agent_improve.STORE_DIR = Path(self.tmpdir.name)
        agent_improve.DB_PATH = Path(self.tmpdir.name) / "improve.db"
        agent_improve.SKILLS_DIR = Path(self.tmpdir.name) / "skills"
        agent_improve.SESSIONS_DIR = Path(self.tmpdir.name) / "sessions"

    def tearDown(self):
        agent_improve.STORE_DIR = self.orig_store
        agent_improve.DB_PATH = self.orig_db
        agent_improve.SKILLS_DIR = self.orig_skills
        agent_improve.SESSIONS_DIR = self.orig_sessions
        self.tmpdir.cleanup()

    def test_get_db_creates_tables(self):
        conn = agent_improve.get_db()
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
        self.assertIn("self_evals", tables)
        self.assertIn("mistakes", tables)
        self.assertIn("skills", tables)

    def test_eval_recorded(self):
        conn = agent_improve.get_db()

        class Args:
            harness = "test-harness"
            task = "test task"
            ambition = "MEDIUM"
            quality = "GOOD"
            score = None
            note = "test note"
            auto = False

        agent_improve.cmd_eval(Args())
        row = conn.execute("SELECT * FROM self_evals").fetchone()
        self.assertEqual(row["harness"], "test-harness")
        self.assertEqual(row["score"], 3)
        self.assertEqual(row["ambition"], "MEDIUM")
        self.assertEqual(row["quality"], "GOOD")

    def test_mistake_recorded(self):
        conn = agent_improve.get_db()

        class Args:
            harness = "test-harness"
            category = "behavior-claim"
            desc = "assumed method existed"
            trigger = "exists, available"

        agent_improve.cmd_mistake(Args())
        row = conn.execute("SELECT * FROM mistakes").fetchone()
        self.assertEqual(row["category"], "behavior-claim")
        self.assertEqual(row["description"], "assumed method existed")

    def test_skill_recorded(self):
        conn = agent_improve.get_db()

        class Args:
            harness = "hermes"
            name = "my-skill"
            file = None
            description = "A useful skill"

        agent_improve.cmd_skill(Args())
        row = conn.execute("SELECT * FROM skills").fetchone()
        self.assertEqual(row["name"], "my-skill")
        self.assertEqual(row["harness"], "hermes")

    def test_inflation_warning(self):
        """Four consecutive scores >= 4 should trigger warning."""
        conn = agent_improve.get_db()

        class Args:
            harness = "inflate-test"
            task = "task"
            ambition = "HIGH"
            quality = "EXCELLENT"
            score = None
            note = ""
            auto = False

        import io
        from contextlib import redirect_stdout
        for _ in range(4):
            agent_improve.cmd_eval(Args())

        buf = io.StringIO()
        with redirect_stdout(buf):
            agent_improve.cmd_eval(Args())
        self.assertIn("consecutive high scores", buf.getvalue())

    def test_auto_mode_records_session_end(self):
        conn = agent_improve.get_db()

        class Args:
            harness = "auto-test"
            auto = True

        agent_improve.cmd_eval(Args())
        row = conn.execute("SELECT * FROM self_evals WHERE harness='auto-test'").fetchone()
        self.assertEqual(row["note"], "auto-recorded")

    def test_report_runs_without_error(self):
        import io
        from contextlib import redirect_stdout

        agent_improve.get_db()

        class Args:
            days = 7

        buf = io.StringIO()
        with redirect_stdout(buf):
            agent_improve.cmd_report(Args())
        self.assertIn("Self-Improvement Report", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
