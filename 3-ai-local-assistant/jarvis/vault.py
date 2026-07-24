"""
vault.py - Local Obsidian-style vault memory subsystem for JARVIS.

The vault is a plain folder of markdown notes:
  vault/prompts/    - auto-generated session notes (one per turn)
  vault/projects/   - hand-written project notes
  vault/about-me/   - hand-written personal info

This module builds a small local FAISS index over the notes so
`ask_claude` can retrieve relevant context. `sentence_transformers` and
`faiss` are optional dependencies - if they aren't installed, indexing
and retrieval no-op gracefully instead of crashing JARVIS.
"""

import json
import os
import time

VAULT_ROOT = os.getenv("JARVIS_VAULT_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "vault"
)
VAULT_ROOT = os.path.abspath(VAULT_ROOT)

PROMPTS_DIR   = os.path.join(VAULT_ROOT, "prompts")
PROJECTS_DIR  = os.path.join(VAULT_ROOT, "projects")
ABOUT_ME_DIR  = os.path.join(VAULT_ROOT, "about-me")
INDEX_DIR     = os.path.join(VAULT_ROOT, ".index")
FAISS_INDEX_FILE = os.path.join(INDEX_DIR, "faiss.index")
META_FILE         = os.path.join(INDEX_DIR, "meta.json")

_SKIP_DIRS = {".index", ".git", ".obsidian"}

_CHUNK_MAX_CHARS = 500

_EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
_embed_model = None  # lazy singleton

try:
    import sentence_transformers  # noqa: F401
    import faiss  # noqa: F401
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False


def ensure_vault_bootstrap():
    """Create vault folders + starter README files if they don't exist yet."""
    for d in (VAULT_ROOT, PROMPTS_DIR, PROJECTS_DIR, ABOUT_ME_DIR):
        os.makedirs(d, exist_ok=True)

    root_readme = os.path.join(VAULT_ROOT, "README.md")
    if not os.path.exists(root_readme):
        with open(root_readme, "w", encoding="utf-8") as f:
            f.write(
                "# JARVIS Vault\n\n"
                "This folder is JARVIS's local memory vault.\n\n"
                "- `prompts/` - auto-generated session notes (one per turn), do not edit\n"
                "- `projects/` - hand-written notes about your projects\n"
                "- `about-me/` - hand-written personal info used as context for Claude\n"
            )

    about_me_readme = os.path.join(ABOUT_ME_DIR, "README.md")
    if not os.path.exists(about_me_readme):
        with open(about_me_readme, "w", encoding="utf-8") as f:
            f.write(
                "# About Me\n\n"
                "- **Name**: \n"
                "- **Role**: \n"
                "- **Preferences**: \n"
                "- **Current Projects**: \n"
            )


def _split_frontmatter(text):
    """Hand-rolled frontmatter split - no PyYAML.

    Parses a leading '---\\n...\\n---' block as simple `key: value` lines.
    Returns (frontmatter_dict, body_str).
    """
    frontmatter = {}
    body = text

    if text.startswith("---"):
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            end_idx = None
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    end_idx = i
                    break
            if end_idx is not None:
                fm_lines = lines[1:end_idx]
                for line in fm_lines:
                    if ":" in line:
                        key, _, value = line.partition(":")
                        frontmatter[key.strip()] = value.strip()
                body = "\n".join(lines[end_idx + 1:]).lstrip("\n")

    return frontmatter, body


def read_notes():
    """Walk the vault for *.md files, skipping index/git/obsidian/hidden entries.

    Returns list of {path, frontmatter, body, mtime}.
    """
    notes = []
    if not os.path.isdir(VAULT_ROOT):
        return notes

    for dirpath, dirnames, filenames in os.walk(VAULT_ROOT):
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]

        for filename in filenames:
            if not filename.endswith(".md"):
                continue
            if filename.startswith("."):
                continue

            full_path = os.path.join(dirpath, filename)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    text = f.read()
                mtime = os.path.getmtime(full_path)
            except OSError:
                continue

            frontmatter, body = _split_frontmatter(text)
            notes.append({
                "path": full_path,
                "frontmatter": frontmatter,
                "body": body,
                "mtime": mtime,
            })

    return notes


def chunk_note(note):
    """Split a note's body into paragraph-boundary chunks, capped at ~500 chars.

    No overlap logic - simple, cheap chunking.
    """
    body = note.get("body", "")
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

    chunks = []
    current = ""
    for para in paragraphs:
        candidate = (current + "\n\n" + para) if current else para
        if len(candidate) > _CHUNK_MAX_CHARS and current:
            chunks.append(current)
            current = para
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def _source_for_path(path):
    """Return the top-level vault subfolder ('prompts'/'projects'/'about-me'/
    'unknown') a note path belongs to, used to tag retrieved chunks by
    provenance/trust level.
    """
    try:
        rel = os.path.relpath(path, VAULT_ROOT)
    except ValueError:
        return "unknown"
    parts = rel.replace(os.sep, "/").split("/")
    return parts[0] if parts else "unknown"


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
    return _embed_model


def build_or_update_index(force=False):
    """Incrementally (re)build the FAISS index over all vault note chunks.

    Both chunking AND embedding are incremental: unchanged notes reuse their
    prior chunk texts *and* their prior embedding vectors (persisted in
    meta.json), so `model.encode()` is only ever called on chunks belonging
    to notes that are new or changed since the last index build. The FAISS
    index object itself is always rebuilt from the full current chunk set -
    cheap at this scale.

    No-ops silently if sentence_transformers/faiss aren't installed.
    """
    if not _DEPS_AVAILABLE:
        return

    import numpy as np
    import faiss
    from sentence_transformers import SentenceTransformer  # noqa: F401

    os.makedirs(INDEX_DIR, exist_ok=True)

    prior_meta = {}
    if not force and os.path.exists(META_FILE):
        try:
            with open(META_FILE, "r", encoding="utf-8") as f:
                prior_meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            prior_meta = {}

    # path -> {mtime, chunks: [text,...], vectors: [[float,...],...]}
    prior_notes = prior_meta.get("notes", {})

    notes = read_notes()
    model = _get_embed_model()

    all_chunk_texts = []
    all_chunk_sources = []
    all_vectors = []

    for note in notes:
        path = note["path"]
        mtime = note["mtime"]

        prior_entry = prior_notes.get(path, {})
        reuse = (
            not force
            and prior_entry.get("mtime") == mtime
            and prior_entry.get("chunks")
            and prior_entry.get("vectors")
            and len(prior_entry.get("vectors")) == len(prior_entry.get("chunks"))
        )

        if reuse:
            chunk_texts = prior_entry["chunks"]
            vectors = [np.array(v, dtype="float32") for v in prior_entry["vectors"]]
        else:
            chunk_texts = chunk_note(note)
            if chunk_texts:
                vectors = list(model.encode(chunk_texts, convert_to_numpy=True))
            else:
                vectors = []

        if not chunk_texts:
            continue

        for text, vector in zip(chunk_texts, vectors):
            all_chunk_texts.append(text)
            all_chunk_sources.append(path)
            all_vectors.append(vector)

        prior_notes[path] = {
            "mtime": mtime,
            "chunks": chunk_texts,
            "vectors": [np.asarray(v, dtype="float32").tolist() for v in vectors],
        }

    # Drop notes that no longer exist from the persisted meta.
    current_paths = {note["path"] for note in notes}
    prior_notes = {p: v for p, v in prior_notes.items() if p in current_paths}

    if not all_vectors:
        # Nothing to index - write empty meta and remove any stale index.
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump({"notes": prior_notes, "chunks": []}, f)
        if os.path.exists(FAISS_INDEX_FILE):
            try:
                os.remove(FAISS_INDEX_FILE)
            except OSError:
                pass
        return

    matrix = np.array(all_vectors, dtype="float32")
    faiss.normalize_L2(matrix)

    dim = matrix.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(matrix)

    faiss.write_index(index, FAISS_INDEX_FILE)

    chunk_meta = [
        {"path": src, "text": text, "source": _source_for_path(src)}
        for src, text in zip(all_chunk_sources, all_chunk_texts)
    ]
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump({"notes": prior_notes, "chunks": chunk_meta}, f)


def retrieve(query: str, top_k: int = 4):
    """Embed the query and search the FAISS index for the top-k chunks.

    Returns [] gracefully if deps/index are unavailable.
    """
    if not _DEPS_AVAILABLE:
        return []
    if not os.path.exists(FAISS_INDEX_FILE) or not os.path.exists(META_FILE):
        return []

    try:
        import numpy as np
        import faiss

        with open(META_FILE, "r", encoding="utf-8") as f:
            meta = json.load(f)
        chunk_meta = meta.get("chunks", [])
        if not chunk_meta:
            return []

        index = faiss.read_index(FAISS_INDEX_FILE)
        model = _get_embed_model()

        query_vec = model.encode([query], convert_to_numpy=True).astype("float32")
        faiss.normalize_L2(query_vec)

        k = min(top_k, len(chunk_meta))
        if k <= 0:
            return []

        _, indices = index.search(query_vec, k)

        results = []
        for idx in indices[0]:
            if idx < 0 or idx >= len(chunk_meta):
                continue
            entry = chunk_meta[idx]
            results.append({
                "path": entry["path"],
                "text": entry["text"],
                "source": entry.get("source") or _source_for_path(entry["path"]),
            })
        return results
    except Exception as e:
        print("[VAULT] retrieve failed: {}".format(e))
        return []


def write_session_note(intent: str, user_text: str, assistant_reply: str):
    """Write a session note under vault/prompts/ for the given turn."""
    os.makedirs(PROMPTS_DIR, exist_ok=True)

    now = time.localtime()
    filename = time.strftime("%Y-%m-%d_%H%M%S", now) + ".md"
    file_path = os.path.join(PROMPTS_DIR, filename)

    content = (
        "---\n"
        "date: {date}\n"
        "intent: {intent}\n"
        "---\n"
        "**User:** {user_text}\n\n"
        "**Assistant:** {assistant_reply}\n"
    ).format(
        date=time.strftime("%Y-%m-%d %H:%M:%S", now),
        intent=intent,
        user_text=user_text,
        assistant_reply=assistant_reply,
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
