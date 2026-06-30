import json
import os
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter, RecursiveJsonSplitter

from .download_repo import download_repo
from model.vector_db import upload_chunks_to_db

WHITELIST_EXTENSIONS = {".md", ".txt", ".js", ".json", ".py", ".java", ".html", ".css", ".ts", ".jsx", ".tsx"}
IGNORE_DIRS = {"node_modules", "dist", "build", "out", "target", "vendor", "bin", "obj", "logs", "temp", ".git"}
IGNORE_FILES = {".DS_Store", "Thumbs.db", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"}

LANG_MAP = {
    ".py": Language.PYTHON, ".java": Language.JAVA, ".html": Language.HTML,
    ".js": Language.JS, ".jsx": Language.JS, ".ts": Language.TS, ".tsx": Language.TS,
}


def ignore_file(file_path: str) -> bool:
    p = Path(file_path)
    if p.name in IGNORE_FILES:
        return True
    if any(part in IGNORE_DIRS for part in p.parts):
        return True
    return p.suffix.lower() not in WHITELIST_EXTENSIONS


def _read(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _chunk_file(file_path: str) -> list[str]:
    ext = Path(file_path).suffix.lower()

    if ext == ".json":
        try:
            data = json.loads(_read(file_path))
            return RecursiveJsonSplitter(max_chunk_size=1000).split_text(json.dumps(data))
        except json.JSONDecodeError:
            pass

    text = _read(file_path)
    lang = LANG_MAP.get(ext)

    if lang:
        splitter = RecursiveCharacterTextSplitter.from_language(lang, chunk_size=800, chunk_overlap=100)
    else:
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    return splitter.split_text(text)


def process_repo(input_url):
    repo_path = download_repo(input_url)

    files_nodes = []
    for root, _, files in os.walk(repo_path):
        for file in files:
            file_path = os.path.join(root, file)
            if ignore_file(file_path):
                continue
            try:
                chunks = _chunk_file(file_path)
                if chunks:
                    files_nodes.append({
                        "file_path": file_path,
                        "file_type": Path(file).suffix.lower(),
                        "nodes": chunks,
                    })
            except Exception as e:
                print(f"Skipping {file_path}: {e}")

    upload_chunks_to_db(files_nodes, repo_id=input_url)
