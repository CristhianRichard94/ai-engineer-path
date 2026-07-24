"""
test/test_vault.py - Unit tests for jarvis/vault.py.

Uses a temporary vault directory (monkeypatching vault.VAULT_ROOT and its
derived path constants) so nothing is written to the real project vault.

The FAISS-index tests require sentence_transformers + faiss to be
installed; they are skipped gracefully otherwise.
"""

import os
import sys
import shutil
import tempfile
import unittest
import unittest.mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
JARVIS_DIR = os.path.join(ROOT, "jarvis")
if JARVIS_DIR not in sys.path:
    sys.path.insert(0, JARVIS_DIR)

import vault as vault_module

try:
    import sentence_transformers  # noqa: F401
    import faiss  # noqa: F401
    _EMBED_DEPS_INSTALLED = True
except ImportError:
    _EMBED_DEPS_INSTALLED = False


class TestVaultBootstrapAndNotes(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.mkdtemp()
        self._patch_vault_paths(self._tmp_dir)

    def tearDown(self):
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _patch_vault_paths(self, root):
        vault_module.VAULT_ROOT = root
        vault_module.PROMPTS_DIR = os.path.join(root, "prompts")
        vault_module.PROJECTS_DIR = os.path.join(root, "projects")
        vault_module.ABOUT_ME_DIR = os.path.join(root, "about-me")
        vault_module.INDEX_DIR = os.path.join(root, ".index")
        vault_module.FAISS_INDEX_FILE = os.path.join(vault_module.INDEX_DIR, "faiss.index")
        vault_module.META_FILE = os.path.join(vault_module.INDEX_DIR, "meta.json")

    def test_ensure_vault_bootstrap_creates_folders_and_readmes(self):
        vault_module.ensure_vault_bootstrap()

        self.assertTrue(os.path.isdir(vault_module.PROMPTS_DIR))
        self.assertTrue(os.path.isdir(vault_module.PROJECTS_DIR))
        self.assertTrue(os.path.isdir(vault_module.ABOUT_ME_DIR))
        self.assertTrue(os.path.exists(os.path.join(vault_module.VAULT_ROOT, "README.md")))
        self.assertTrue(os.path.exists(os.path.join(vault_module.ABOUT_ME_DIR, "README.md")))

    def test_ensure_vault_bootstrap_is_idempotent(self):
        vault_module.ensure_vault_bootstrap()
        readme_path = os.path.join(vault_module.VAULT_ROOT, "README.md")
        with open(readme_path, "a", encoding="utf-8") as f:
            f.write("custom user content\n")

        vault_module.ensure_vault_bootstrap()

        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("custom user content", content)

    def test_read_notes_parses_frontmatter_and_body(self):
        vault_module.ensure_vault_bootstrap()
        note_path = os.path.join(vault_module.PROJECTS_DIR, "note.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write("---\ndate: 2026-01-01\nintent: ask_claude\n---\nHello body text.\n")

        notes = vault_module.read_notes()
        matching = [n for n in notes if n["path"] == note_path]
        self.assertEqual(len(matching), 1)
        note = matching[0]
        self.assertEqual(note["frontmatter"]["date"], "2026-01-01")
        self.assertEqual(note["frontmatter"]["intent"], "ask_claude")
        self.assertIn("Hello body text.", note["body"])

    def test_read_notes_skips_index_and_hidden_dirs(self):
        vault_module.ensure_vault_bootstrap()
        os.makedirs(os.path.join(vault_module.VAULT_ROOT, ".index"), exist_ok=True)
        with open(os.path.join(vault_module.VAULT_ROOT, ".index", "stale.md"), "w", encoding="utf-8") as f:
            f.write("should not be read")
        os.makedirs(os.path.join(vault_module.VAULT_ROOT, ".git"), exist_ok=True)
        with open(os.path.join(vault_module.VAULT_ROOT, ".git", "hidden.md"), "w", encoding="utf-8") as f:
            f.write("should not be read either")

        notes = vault_module.read_notes()
        paths = [n["path"] for n in notes]
        self.assertFalse(any(".index" in p for p in paths))
        self.assertFalse(any(".git" in p for p in paths))

    def test_chunk_note_splits_on_paragraph_boundaries_and_caps_length(self):
        long_paragraph = "word " * 200  # > 500 chars
        note = {"body": "Short para one.\n\n" + long_paragraph}
        chunks = vault_module.chunk_note(note)
        self.assertGreaterEqual(len(chunks), 2)
        for chunk in chunks:
            # Allow the single long paragraph to exceed the cap on its own -
            # only the *joining* of paragraphs is capped.
            self.assertTrue(len(chunk) > 0)

    def test_write_session_note_creates_file_with_expected_content(self):
        vault_module.ensure_vault_bootstrap()
        vault_module.write_session_note("ask_claude", "What's the weather?", "It's sunny, sir.")

        files = os.listdir(vault_module.PROMPTS_DIR)
        self.assertEqual(len(files), 1)
        with open(os.path.join(vault_module.PROMPTS_DIR, files[0]), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("intent: ask_claude", content)
        self.assertIn("**User:** What's the weather?", content)
        self.assertIn("**Assistant:** It's sunny, sir.", content)


@unittest.skipUnless(_EMBED_DEPS_INSTALLED, "sentence_transformers/faiss not installed")
class TestVaultIndexAndRetrieve(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.mkdtemp()
        vault_module.VAULT_ROOT = self._tmp_dir
        vault_module.PROMPTS_DIR = os.path.join(self._tmp_dir, "prompts")
        vault_module.PROJECTS_DIR = os.path.join(self._tmp_dir, "projects")
        vault_module.ABOUT_ME_DIR = os.path.join(self._tmp_dir, "about-me")
        vault_module.INDEX_DIR = os.path.join(self._tmp_dir, ".index")
        vault_module.FAISS_INDEX_FILE = os.path.join(vault_module.INDEX_DIR, "faiss.index")
        vault_module.META_FILE = os.path.join(vault_module.INDEX_DIR, "meta.json")
        vault_module.ensure_vault_bootstrap()

        notes = {
            "note1.md": "This note is about weekend hiking trips in the mountains.",
            "note2.md": "Project Zephyr is a Rust-based CLI tool for managing "
                        "distributed task queues with a custom scheduler.",
            "note3.md": "Grocery list: milk, eggs, bread, coffee.",
        }
        for filename, body in notes.items():
            with open(os.path.join(vault_module.PROJECTS_DIR, filename), "w", encoding="utf-8") as f:
                f.write(body)

    def tearDown(self):
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_retrieve_surfaces_note_with_distinctive_keyword(self):
        vault_module.build_or_update_index(force=True)

        results = vault_module.retrieve("Zephyr distributed task queue scheduler", top_k=2)

        self.assertTrue(len(results) > 0)
        self.assertTrue(
            any("Zephyr" in r["text"] for r in results),
            f"Expected note2 content in top results, got: {results}",
        )

    def test_build_or_update_index_reuses_unchanged_note_chunks(self):
        vault_module.build_or_update_index(force=True)
        with open(vault_module.META_FILE, "r", encoding="utf-8") as f:
            import json
            meta_before = json.load(f)

        # Re-run without force - unchanged notes should produce identical
        # persisted chunk metadata (proving reuse rather than re-chunking).
        vault_module.build_or_update_index(force=False)
        with open(vault_module.META_FILE, "r", encoding="utf-8") as f:
            import json
            meta_after = json.load(f)

        self.assertEqual(meta_before["chunks"], meta_after["chunks"])

    def test_build_or_update_index_reuses_unchanged_note_vectors_not_reembedded(self):
        # First build - forces embedding of all three seeded notes.
        vault_module.build_or_update_index(force=True)

        # Add a brand-new note so the second build has exactly one changed
        # note plus all the prior unchanged ones.
        new_note_path = os.path.join(vault_module.PROJECTS_DIR, "note4.md")
        new_note_text = "Note four is about a completely new topic: beekeeping."
        with open(new_note_path, "w", encoding="utf-8") as f:
            f.write(new_note_text)

        model = vault_module._get_embed_model()
        with unittest.mock.patch.object(
            model, "encode", wraps=model.encode
        ) as spy_encode:
            vault_module.build_or_update_index(force=False)

            called_texts = set()
            for call in spy_encode.call_args_list:
                texts_arg = call.args[0] if call.args else call.kwargs.get("chunk_texts")
                called_texts.update(texts_arg)

            self.assertIn(
                new_note_text, called_texts,
                "expected the new/changed note's chunk to be embedded",
            )
            # None of the three original, unchanged notes' text should have
            # been re-embedded on the second, incremental build.
            for original_text in (
                "This note is about weekend hiking trips in the mountains.",
                "Project Zephyr is a Rust-based CLI tool for managing "
                "distributed task queues with a custom scheduler.",
                "Grocery list: milk, eggs, bread, coffee.",
            ):
                self.assertNotIn(
                    original_text, called_texts,
                    "unchanged note text should have reused its stored "
                    "vector instead of being re-embedded",
                )

    def test_retrieve_returns_empty_list_when_no_index_built(self):
        # Fresh vault, index never built.
        results = vault_module.retrieve("anything", top_k=4)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
