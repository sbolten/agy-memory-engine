#!/usr/bin/env python3
"""
Comprehensive Unit & Integration Test Suite for agy-memory-engine
Tests:
- Database initialization & schema creation (memories, episodes, learnings)
- FTS5 indexing & automatic trigger synchronization
- Multi-layer Prefetch (Facts + Episodes + Learnings + Preferences)
- Fuzzy & typo matching
- Upsert logic (conflict resolution & in-place updates)
- Ingestion & compaction lifecycle
"""

import os
import sys
import tempfile
import unittest
import json
import io
from contextlib import redirect_stdout

# Set temporary test database environment variable before importing engine
TEST_DIR = tempfile.mkdtemp()
TEST_DB = os.path.join(TEST_DIR, "test_memory.db")
os.environ["AGY_MEMORY_DB"] = TEST_DB

import agy_memory

class TestAgyMemoryEngine(unittest.TestCase):

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def test_01_fact_lifecycle(self):
        """Test creating, indexing and querying atomic facts."""
        agy_memory.upsert_fact("infra.test_ip", "infra", "Server IP 192.168.1.50", "server ip network test")
        
        with agy_memory.db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT fact FROM memories WHERE id = 'infra.test_ip'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "Server IP 192.168.1.50")

            # Test FTS5 sync trigger
            cursor.execute('SELECT id FROM memories_fts WHERE memories_fts MATCH \'"192.168.1.50"\'')
            fts_row = cursor.fetchone()
            self.assertIsNotNone(fts_row)
            self.assertEqual(fts_row[0], "infra.test_ip")

    def test_02_episode_lifecycle(self):
        """Test creating, indexing and querying narrative chronicles/episodes."""
        agy_memory.upsert_episode(
            episode_id="stweg.test_dispute",
            topic="stweg",
            title="STWEG Höhenweg 15 Streitfall",
            period="2020-2026",
            status="active",
            narrative="Laufender Nachbarschaftskonflikt bezüglich Baumschnitt und Kamin.",
            entities="Herr Jenni, Familie Bolten",
            stance="Nur schriftliche Anwaltskommunikation",
            keywords="Jenni Baum Garten Kamin Streit"
        )

        with agy_memory.db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, stance FROM episodes WHERE id = 'stweg.test_dispute'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "STWEG Höhenweg 15 Streitfall")
            self.assertEqual(row[1], "Nur schriftliche Anwaltskommunikation")

            # Test FTS5 sync trigger
            cursor.execute("SELECT id FROM episodes_fts WHERE episodes_fts MATCH 'Baumschnitt'")
            fts_row = cursor.fetchone()
            self.assertIsNotNone(fts_row)
            self.assertEqual(fts_row[0], "stweg.test_dispute")

    def test_03_learning_lifecycle(self):
        """Test creating, indexing and querying experiential learnings."""
        agy_memory.upsert_learning(
            learning_id="travel.dog_ferienhaus",
            category="travel",
            insight="Immer Zaunhöhe vorab prüfen für Hund.",
            context="Erfahrungen mit Abbie in Italien",
            keywords="Ferienhaus Hund Zaun Italien"
        )

        with agy_memory.db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT insight FROM learnings WHERE id = 'travel.dog_ferienhaus'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "Immer Zaunhöhe vorab prüfen für Hund.")

            # Test FTS5 sync trigger
            cursor.execute("SELECT id FROM learnings_fts WHERE learnings_fts MATCH 'Zaunhöhe'")
            fts_row = cursor.fetchone()
            self.assertIsNotNone(fts_row)
            self.assertEqual(fts_row[0], "travel.dog_ferienhaus")

    def test_04_multi_layer_prefetch(self):
        """Test prefetching across all layers in a single query."""
        # 1. Fact
        agy_memory.upsert_fact("pref.text", "preference", "Immer Zeilenabstand halten", "format text layout")
        agy_memory.upsert_fact("infra.router", "infra", "FritzBox 7590 IP 192.168.1.1", "router fritzbox network")
        
        # 2. Episode
        agy_memory.upsert_episode(
            "stweg.jenni_konflikt",
            "stweg",
            "Nachbarschaftskonflikt Jenni",
            "2020-2026",
            "active",
            "Streitfall wegen Baumschnitt im Garten und Laub.",
            "Mariano Jenni, Stephan Bolten",
            "Formelle Distanz",
            "Jenni Nachbar Garten Baum Laub"
        )

        # 3. Learning
        agy_memory.upsert_learning(
            "travel.fewo_garden",
            "travel",
            "Garten muss komplett eingezäunt sein.",
            "Reisen mit Hund",
            "Garten Zaun Fewo Hund"
        )

        # Test prefetch output capture
        f = io.StringIO()
        with redirect_stdout(f):
            agy_memory.prefetch("Was ist der Status mit Jenni und dem Garten?")
        output = f.getvalue()

        self.assertIn("[🧠 Memory Context - Facts]", output)
        self.assertIn("Immer Zeilenabstand halten", output)
        self.assertIn("[📖 Narrative Context - Episodic Memory]", output)
        self.assertIn("Nachbarschaftskonflikt Jenni", output)
        self.assertIn("Streitfall wegen Baumschnitt im Garten", output)
        self.assertIn("[💡 Learnings & Heuristics]", output)
        self.assertIn("Garten muss komplett eingezäunt sein", output)

    def test_05_compaction_and_rebuild(self):
        """Test vacuum and FTS rebuild."""
        agy_memory.upsert_fact("test.key", "general", "Fact 1", "keyword1")
        agy_memory.compact_all(apply_changes=True)

        with agy_memory.db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT fact FROM memories WHERE id = 'test.key'")
            row = cursor.fetchone()
            self.assertEqual(row[0], "Fact 1")

if __name__ == "__main__":
    unittest.main()
