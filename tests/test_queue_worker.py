import unittest
import os
import tempfile
import sqlite3
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from queue_manager import (
    init_queue_db,
    enqueue_turn,
    get_pending_turns,
    mark_turn_status,
    prune_processed_turns
)
from memory_worker import format_notification


class TestQueueManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_queue.db")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_init_and_enqueue(self):
        init_queue_db(self.db_path)
        ok = enqueue_turn("Hallo, wie gehts?", "Mir geht es gut!", source="telegram", chat_id="12345", db_path=self.db_path)
        self.assertTrue(ok)

        # Enqueue same turn should deduplicate and return True without duplicate insert
        ok_dup = enqueue_turn("Hallo, wie gehts?", "Mir geht es gut!", source="telegram", chat_id="12345", db_path=self.db_path)
        self.assertTrue(ok_dup)

        pending = get_pending_turns(limit=10, db_path=self.db_path)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["user_prompt"], "Hallo, wie gehts?")
        self.assertEqual(pending[0]["chat_id"], "12345")

    def test_mark_and_prune(self):
        enqueue_turn("Frage 1", "Antwort 1", db_path=self.db_path)
        enqueue_turn("Frage 2", "Antwort 2", db_path=self.db_path)
        
        pending = get_pending_turns(limit=10, db_path=self.db_path)
        self.assertEqual(len(pending), 2)
        
        turn1_id = pending[0]["id"]
        mark_turn_status([turn1_id], status="processed", summary="1 fact synced", db_path=self.db_path)

        pending_after = get_pending_turns(limit=10, db_path=self.db_path)
        self.assertEqual(len(pending_after), 1)
        self.assertEqual(pending_after[0]["user_prompt"], "Frage 2")


class TestWorkerNotification(unittest.TestCase):
    def test_format_notification(self):
        changes = {
            "facts": [{"id": "user.test.dog", "category": "user", "fact": "Golden Retriever 4 Jahre", "is_update": False}],
            "episodes": [{"id": "travel.foehr_2026", "topic": "travel", "title": "Föhr Urlaub", "is_update": True}],
            "learnings": [{"id": "finance.investing", "category": "finance", "insight": "80/20 Allokation", "is_update": False}],
            "entity_links": [{"source": "infra.beelink", "target": "service.immich", "relation": "hosts"}]
        }
        msg = format_notification(changes)
        self.assertIn("Autonomes Gedächtnis aktualisiert", msg)
        self.assertIn("user.test.dog", msg)
        self.assertIn("travel.foehr_2026", msg)
        self.assertIn("finance.investing", msg)
        self.assertIn("infra.beelink", msg)


if __name__ == "__main__":
    unittest.main()
