#!/usr/bin/env python3
"""
Comprehensive Unit & Integration Test Suite for agy-memory-engine

Tests:
- Database initialization & schema creation (memories, episodes, learnings)
- FTS5 indexing & automatic trigger synchronization
- Multi-layer Prefetch (Facts + Episodes + Learnings + Preferences)
- Upsert logic (conflict resolution & in-place updates)
- Fuzzy & typo matching
- Protected categories guard
- Empty database / edge cases
- Unicode & special characters
- Trivial prompt filtering
- Optimization lifecycle (backup, rebuild, vacuum)
- Schema initialization efficiency (only once per process)
"""

import os
import sys
import tempfile
import unittest
import json
import io
from contextlib import redirect_stdout, redirect_stderr

# Set temporary test database environment variable before importing engine
TEST_DIR = tempfile.mkdtemp()
TEST_DB = os.path.join(TEST_DIR, "test_memory.db")
os.environ["AGY_MEMORY_DB"] = TEST_DB

# Must set env before importing schema module
import schema
schema.DB_PATH = TEST_DB
schema._SCHEMA_INITIALIZED.clear()

import agy_memory


class TestFactLifecycle(unittest.TestCase):
    """Tests for Layer 1: Atomic Facts."""

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def test_create_and_query_fact(self):
        """Basic fact creation and FTS5 indexing."""
        agy_memory.upsert_fact("infra.test_ip", "infra", "Server IP 192.168.1.50", "server ip network test")
        
        with schema.db_session(TEST_DB) as conn:
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

    def test_upsert_overwrites_existing(self):
        """Upsert should overwrite an existing fact with the same ID."""
        agy_memory.upsert_fact("test.key", "general", "Original value", "kw1")
        agy_memory.upsert_fact("test.key", "updated_cat", "Updated value", "kw2")
        
        with schema.db_session(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT category, fact, keywords FROM memories WHERE id = 'test.key'")
            row = cursor.fetchone()
            self.assertEqual(row[0], "updated_cat")
            self.assertEqual(row[1], "Updated value")
            self.assertEqual(row[2], "kw2")
            
            # Ensure only one row exists (no duplication)
            cursor.execute("SELECT COUNT(*) FROM memories WHERE id = 'test.key'")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_unicode_umlauts_in_facts(self):
        """Facts with German umlauts and special characters should be stored and searchable."""
        agy_memory.upsert_fact("test.umlaut", "test", "Zürich Höhenweg Strässchen", "zürich höhe ö ä ü")
        
        with schema.db_session(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM memories_fts WHERE memories_fts MATCH 'Zürich'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "test.umlaut")


class TestEpisodeLifecycle(unittest.TestCase):
    """Tests for Layer 2: Narrative Chronicles & Episodes."""

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def test_create_and_query_episode(self):
        """Episode creation and FTS5 indexing."""
        agy_memory.upsert_episode(
            episode_id="stweg.test",
            topic="stweg",
            title="STWEG Höhenweg 15 Streitfall",
            period="2020-2026",
            status="active",
            narrative="Laufender Nachbarschaftskonflikt bezüglich Baumschnitt und Kamin.",
            entities="Herr Jenni, Familie Bolten",
            stance="Nur schriftliche Anwaltskommunikation",
            keywords="Jenni Baum Garten Kamin Streit"
        )

        with schema.db_session(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, stance FROM episodes WHERE id = 'stweg.test'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "STWEG Höhenweg 15 Streitfall")
            self.assertEqual(row[1], "Nur schriftliche Anwaltskommunikation")

            cursor.execute("SELECT id FROM episodes_fts WHERE episodes_fts MATCH 'Baumschnitt'")
            fts_row = cursor.fetchone()
            self.assertIsNotNone(fts_row)

    def test_episode_upsert_updates_in_place(self):
        """Upserting an episode should update all fields without creating duplicates."""
        agy_memory.upsert_episode("ep.test", "general", "Title V1", "Narrative V1", status="active")
        agy_memory.upsert_episode("ep.test", "general", "Title V2", "Narrative V2", status="resolved")
        
        with schema.db_session(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, narrative, status FROM episodes WHERE id = 'ep.test'")
            row = cursor.fetchone()
            self.assertEqual(row[0], "Title V2")
            self.assertEqual(row[1], "Narrative V2")
            self.assertEqual(row[2], "resolved")
            
            cursor.execute("SELECT COUNT(*) FROM episodes WHERE id = 'ep.test'")
            self.assertEqual(cursor.fetchone()[0], 1)


class TestLearningLifecycle(unittest.TestCase):
    """Tests for Layer 3: Experiential Learnings."""

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def test_create_and_query_learning(self):
        """Learning creation and FTS5 indexing."""
        agy_memory.upsert_learning(
            learning_id="travel.dog_ferienhaus",
            category="travel",
            insight="Immer Zaunhöhe vorab prüfen für Hund.",
            context="Erfahrungen mit Abbie in Italien",
            keywords="Ferienhaus Hund Zaun Italien"
        )

        with schema.db_session(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT insight FROM learnings WHERE id = 'travel.dog_ferienhaus'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "Immer Zaunhöhe vorab prüfen für Hund.")

            cursor.execute("SELECT id FROM learnings_fts WHERE learnings_fts MATCH 'Zaunhöhe'")
            fts_row = cursor.fetchone()
            self.assertIsNotNone(fts_row)


class TestMultiLayerPrefetch(unittest.TestCase):
    """Tests for cross-layer prefetch functionality."""

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def test_multi_layer_prefetch(self):
        """Prefetch should return results from all three layers."""
        agy_memory.upsert_fact("pref.text", "preference", "Immer Zeilenabstand halten", "format text layout")
        agy_memory.upsert_episode(
            "stweg.jenni", "stweg", "Nachbarschaftskonflikt Jenni",
            "Streitfall wegen Baumschnitt im Garten und Laub.",
            period="2020-2026", status="active",
            keywords="Jenni Nachbar Garten Baum Laub"
        )
        agy_memory.upsert_learning(
            "travel.fewo_garden", "travel",
            "Garten muss komplett eingezäunt sein.",
            "Reisen mit Hund",
            "Garten Zaun Fewo Hund"
        )

        f = io.StringIO()
        with redirect_stdout(f):
            agy_memory.prefetch("Was ist der Status mit Jenni und dem Garten?")
        output = f.getvalue()

        self.assertIn("[🧠 Memory Context - Facts]", output)
        self.assertIn("Immer Zeilenabstand halten", output)
        self.assertIn("[📖 Narrative Context - Episodic Memory]", output)
        self.assertIn("Nachbarschaftskonflikt Jenni", output)
        self.assertIn("[💡 Learnings & Heuristics]", output)
        self.assertIn("Garten muss komplett eingezäunt sein", output)

    def test_prefetch_on_empty_database(self):
        """Prefetch on an empty database should not crash."""
        f = io.StringIO()
        with redirect_stdout(f):
            agy_memory.prefetch("Wo ist der Server?")
        output = f.getvalue()
        # Should produce no output (empty DB), but not crash
        self.assertEqual(output, "")

    def test_preferences_always_loaded(self):
        """Preferences should always appear even for unrelated queries."""
        agy_memory.upsert_fact("pref.rule1", "preferences", "Always speak German", "sprache deutsch")
        agy_memory.upsert_fact("infra.server", "infra", "Server 10.0.0.1", "server ip")

        f = io.StringIO()
        with redirect_stdout(f):
            agy_memory.prefetch("Erzähl mir einen Witz")
        output = f.getvalue()
        # Preferences should load even though query doesn't match them
        self.assertIn("Always speak German", output)


class TestTrivialPromptFilter(unittest.TestCase):
    """Tests for the trivial prompt rejection filter."""

    def test_trivial_prompts(self):
        """Known trivial inputs should be filtered."""
        trivial = ["ok", "yes", "no", "thanks!", "y", "cool", "next", "lgtm", "/help", ""]
        for t in trivial:
            self.assertTrue(agy_memory.is_trivial_prompt(t), f"'{t}' should be trivial")

    def test_non_trivial_prompts(self):
        """Real questions should not be filtered."""
        non_trivial = [
            "Was ist der Status mit Jenni?",
            "Wie geht es Abbie?",
            "Update the server IP to 10.0.0.1",
            "Show me the Tesla charging stats",
        ]
        for t in non_trivial:
            self.assertFalse(agy_memory.is_trivial_prompt(t), f"'{t}' should NOT be trivial")


class TestProtectedCategories(unittest.TestCase):
    """Tests for the protected category guard."""

    def test_health_key_is_protected(self):
        self.assertTrue(agy_memory._is_protected_key("health.abbie.epilepsie"))

    def test_finance_key_is_protected(self):
        self.assertTrue(agy_memory._is_protected_key("finance.etf"))

    def test_pension_key_is_protected(self):
        self.assertTrue(agy_memory._is_protected_key("pension.vz.planning"))

    def test_user_key_is_protected(self):
        self.assertTrue(agy_memory._is_protected_key("user.dog.abbie"))

    def test_infra_key_is_not_protected(self):
        self.assertFalse(agy_memory._is_protected_key("infra.server.ip"))

    def test_trading_key_is_not_protected(self):
        self.assertFalse(agy_memory._is_protected_key("trading.tpa"))


class TestDiffFormatting(unittest.TestCase):
    """Tests for the diff output formatting used in dry-run mode."""

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def test_new_entry_diff(self):
        """A new entry should be marked as [NEW]."""
        diff = agy_memory._format_diff(None, {"id": "test.new", "fact": "hello"}, "Fact")
        self.assertIn("[NEW]", diff)
        self.assertIn("test.new", diff)

    def test_update_diff_shows_changes(self):
        """An update should show old → new values."""
        old = {"id": "test.key", "fact": "old value", "category": "general"}
        new = {"id": "test.key", "fact": "new value", "category": "general"}
        diff = agy_memory._format_diff(old, new, "Fact")
        self.assertIn("[UPDATE]", diff)
        self.assertIn("old value", diff)
        self.assertIn("new value", diff)

    def test_protected_update_shows_marker(self):
        """Updates to protected keys should show the 🔒 marker."""
        old = {"id": "health.abbie", "fact": "old dose"}
        new = {"id": "health.abbie", "fact": "new dose"}
        diff = agy_memory._format_diff(old, new, "Fact")
        self.assertIn("PROTECTED", diff)
        self.assertIn("🔒", diff)


class TestOptimizeDB(unittest.TestCase):
    """Tests for the optimize/compact lifecycle."""

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def test_optimize_creates_backup_and_succeeds(self):
        """Optimize should create backup, rebuild FTS, and report stats."""
        agy_memory.upsert_fact("test.key", "general", "Fact 1", "keyword1")
        
        f = io.StringIO()
        with redirect_stdout(f):
            agy_memory.optimize_db(apply_changes=True)
        output = f.getvalue()

        self.assertIn("[BACKUP]", output)
        self.assertIn("[STATS]", output)
        self.assertIn("[OPTIMIZE]", output)
        self.assertIn("[SUCCESS]", output)
        self.assertIn("Facts: 1", output)

        # Verify data survived
        with schema.db_session(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT fact FROM memories WHERE id = 'test.key'")
            row = cursor.fetchone()
            self.assertEqual(row[0], "Fact 1")

    def test_compact_alias_works(self):
        """The backward-compat 'compact_all' alias should call optimize_db."""
        agy_memory.upsert_fact("test.compat", "general", "Compat test", "")
        f = io.StringIO()
        with redirect_stdout(f):
            agy_memory.compact_all(apply_changes=True)
        output = f.getvalue()
        self.assertIn("[SUCCESS]", output)


class TestSchemaInitOnce(unittest.TestCase):
    """Test that schema is only initialized once per process per DB path."""

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def test_schema_initialized_flag_set(self):
        """After first db_session, the path should be in _SCHEMA_INITIALIZED."""
        with schema.db_session(TEST_DB) as conn:
            pass
        self.assertIn(TEST_DB, schema._SCHEMA_INITIALIZED)

    def test_multiple_sessions_no_error(self):
        """Multiple sequential db_session calls should work without errors."""
        for _ in range(5):
            with schema.db_session(TEST_DB) as conn:
                conn.execute("SELECT 1")


class TestEntityLinking(unittest.TestCase):
    """Tests for Entity Graph Linking and Multi-hop Retrieval."""

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def test_link_and_list_entities(self):
        """Test creating and listing directional entity links."""
        agy_memory.link_entities("infra.beelink", "service.immich", "hosts")
        agy_memory.link_entities("infra.beelink", "service.jellyfin", "hosts")
        
        links = agy_memory.list_entity_links("infra.beelink")
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0], ("infra.beelink", "service.immich", "hosts"))

    def test_unlink_entities(self):
        """Test unlinking relations."""
        agy_memory.link_entities("user.stephan", "device.fenix8", "owns")
        self.assertEqual(len(agy_memory.list_entity_links("user.stephan")), 1)
        
        agy_memory.unlink_entities("user.stephan", "device.fenix8", "owns")
        self.assertEqual(len(agy_memory.list_entity_links("user.stephan")), 0)

    def test_prefetch_with_entity_expansion(self):
        """Prefetching for a service pulls in linked host fact."""
        agy_memory.upsert_fact("infra.beelink.ip", "infra", "Beelink IP 100.114.118.47", "beelink host server ip")
        agy_memory.upsert_fact("service.immich.port", "infra", "Immich Port 2283", "immich photos port")
        agy_memory.link_entities("service.immich.port", "infra.beelink.ip", "hosted_on")

        f = io.StringIO()
        with redirect_stdout(f):
            agy_memory.prefetch("Wie lautet der Port von Immich?")
        output = f.getvalue()

        self.assertIn("Immich Port 2283", output)
        self.assertIn("[🔗 Linked Entity Relations]", output)
        self.assertIn("Beelink IP 100.114.118.47", output)


class TestEpisodeAging(unittest.TestCase):
    """Tests for Episode Aging and State Decay."""

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def test_episode_aging_transition(self):
        """Test that old episodes transition active -> cooling -> historic."""
        agy_memory.upsert_episode("ep.old_1", "travel", "Spain Trip", "Trip completed in June.", status="active")
        agy_memory.upsert_episode("ep.old_2", "hardware", "TrueNAS Setup", "Setup cooled down.", status="cooling")

        # Manually backdate updated_at in database
        with schema.db_session(TEST_DB) as conn:
            conn.execute("UPDATE episodes SET updated_at = datetime('now', '-35 days') WHERE id = 'ep.old_1'")
            conn.execute("UPDATE episodes SET updated_at = datetime('now', '-95 days') WHERE id = 'ep.old_2'")
            conn.commit()

        res = agy_memory.age_episodes(days_to_cooling=30, days_to_historic=90)
        self.assertEqual(len(res["cooled"]), 1)
        self.assertEqual(res["cooled"][0][0], "ep.old_1")
        self.assertEqual(len(res["historied"]), 1)
        self.assertEqual(res["historied"][0][0], "ep.old_2")

        # Verify status in database
        with schema.db_session(TEST_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM episodes WHERE id = 'ep.old_1'")
            self.assertEqual(cursor.fetchone()[0], "cooling")
            cursor.execute("SELECT status FROM episodes WHERE id = 'ep.old_2'")
            self.assertEqual(cursor.fetchone()[0], "historic")


class TestConsolidation(unittest.TestCase):
    """Tests for Semantic Memory Consolidation and Audit Logging."""

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def test_consolidation_audit_logging(self):
        """Test that consolidation correctly writes to consolidation_log and merges entries."""
        agy_memory.upsert_fact("health.creatine.1", "health", "Takes 5g creatine monohydrate daily.", "creatine supplement")
        agy_memory.upsert_fact("health.creatine.2", "health", "Lee-Sport Creapure Creatine 5g.", "creapure lee-sport")

        # Mock LLM response for consolidation
        mock_response = json.dumps({
            "merges": [
                {
                    "target_id": "health.creatine.daily",
                    "category": "health",
                    "fact": "Takes 5g Creapure Creatine Monohydrate (Lee-Sport) daily.",
                    "keywords": "creatine creapure lee-sport supplement",
                    "merged_ids": ["health.creatine.1", "health.creatine.2"],
                    "rationale": "Merged dosage and brand info into one canonical record."
                }
            ]
        })

        import unittest.mock as mock
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(stdout=mock_response, returncode=0)
            merges = agy_memory.consolidate_memories(dry_run=False)

        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0]["target_id"], "health.creatine.daily")

        with schema.db_session(TEST_DB) as conn:
            cursor = conn.cursor()
            # 1. Target ID exists
            cursor.execute("SELECT fact FROM memories WHERE id = 'health.creatine.daily'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertIn("Lee-Sport", row[0])

            # 2. Merged IDs are deleted
            cursor.execute("SELECT COUNT(*) FROM memories WHERE id IN ('health.creatine.1', 'health.creatine.2')")
            self.assertEqual(cursor.fetchone()[0], 0)

            # 3. Audit log contains the merge action
            cursor.execute("SELECT action, category, target_id, diff_summary, rationale FROM consolidation_log")
            log_row = cursor.fetchone()
            self.assertIsNotNone(log_row)
            self.assertEqual(log_row[0], "merge")
            self.assertEqual(log_row[1], "health")
            self.assertEqual(log_row[2], "health.creatine.daily")
            self.assertIn("health.creatine.1", log_row[3])
            self.assertEqual(log_row[4], "Merged dosage and brand info into one canonical record.")


class TestMultilingualCompoundAndStemming(unittest.TestCase):
    """Tests for multilingual token expansion, morphological stemming, and compound splitting with vocabulary validation."""

    def setUp(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def tearDown(self):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        schema._SCHEMA_INITIALIZED.discard(TEST_DB)

    def test_extract_multilingual_tokens_compounds(self):
        """Test compound noun splitting with interfix / Fugenmorphemes."""
        mock_vocab = {"hund", "versicherung", "zweitwohnung", "steuer", "zimmer", "reservierung", "hond", "verzekering"}
        
        # German compounds
        tokens_de = agy_memory.extract_multilingual_tokens("Hundeversicherung für Abbie", mock_vocab)
        self.assertIn("hund", tokens_de)
        self.assertIn("versicherung", tokens_de)

        tokens_fugen = agy_memory.extract_multilingual_tokens("Zweitwohnungssteuer in Graubünden", mock_vocab)
        self.assertIn("zweitwohnung", tokens_fugen)
        self.assertIn("steuer", tokens_fugen)

        # Dutch compounds
        tokens_nl = agy_memory.extract_multilingual_tokens("Wat is de hondenverzekering voor huisdieren", mock_vocab)
        self.assertIn("hond", tokens_nl)
        self.assertIn("verzekering", tokens_nl)

    def test_extract_multilingual_tokens_stemming(self):
        """Test morphological inflection/suffix stemming across multiple languages."""
        mock_vocab = {"hotel", "madrid", "voiture", "albergo"}

        # English plural stemming
        tokens_en = agy_memory.extract_multilingual_tokens("What are the pet insurances", mock_vocab)
        self.assertIn("pet", tokens_en)
        self.assertTrue("insur" in tokens_en or "insuranc" in tokens_en or "insurances" in tokens_en)

        # French plural & stopwords
        tokens_fr = agy_memory.extract_multilingual_tokens("Quelle est l assurance pour mes voitures", mock_vocab)
        self.assertIn("assurance", tokens_fr)
        self.assertIn("voitur", tokens_fr)
        self.assertNotIn("pour", tokens_fr)
        self.assertNotIn("mes", tokens_fr)

        # Italian stopwords & inflection
        tokens_it = agy_memory.extract_multilingual_tokens("Mostrami la prenotazione alberghiera", mock_vocab)
        self.assertIn("prenot", tokens_it)
        self.assertNotIn("la", tokens_it)

        # Spanish stopwords & inflection
        tokens_es = agy_memory.extract_multilingual_tokens("Buscar reservaciones de hotel en Madrid", mock_vocab)
        self.assertIn("hotel", tokens_es)
        self.assertIn("madrid", tokens_es)
        self.assertIn("reserv", tokens_es)
        self.assertNotIn("de", tokens_es)
        self.assertNotIn("en", tokens_es)

    def test_multilingual_prefetch_end_to_end(self):
        """End-to-end test verifying that multilingual compound and inflected queries match stored facts."""
        agy_memory.upsert_fact("insurance.dog.ch", "insurance", "Hundeversicherung bei der Helvetia Police 12345.", "hund versicherung helvetia")
        agy_memory.upsert_fact("tax.sent.zweitwohnung", "tax", "Zweitwohnungssteuer in Sent ist 1.5 Promille.", "zweitwohnung steuer sent")
        agy_memory.upsert_fact("travel.madrid.hotel", "travel", "Hotel Urban Madrid gebucht für Oktober.", "hotel madrid reservation")

        # 1. German compound query should match "Hundeversicherung" via "hund" + "versicherung"
        f = io.StringIO()
        with redirect_stdout(f):
            res = agy_memory.prefetch("Gibt es eine Hundeleine oder Hundeversicherung?")
        output = f.getvalue()
        self.assertIn("Hundeversicherung bei der Helvetia", output)

        # 2. English inflected query should match "hotel madrid reservation"
        f2 = io.StringIO()
        with redirect_stdout(f2):
            res2 = agy_memory.prefetch("Show me my hotel reservations in Madrid")
        output2 = f2.getvalue()
        self.assertIn("Hotel Urban Madrid gebucht", output2)

        # 3. Italian query should match "tax.sent.zweitwohnung"
        f3 = io.StringIO()
        with redirect_stdout(f3):
            res3 = agy_memory.prefetch("Qual è la tassa sulla seconda casa a Sent?")
        output3 = f3.getvalue()
        self.assertIn("Zweitwohnungssteuer in Sent", output3)


if __name__ == "__main__":
    unittest.main()

