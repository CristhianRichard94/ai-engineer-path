import os
from .download_repo import download_repo
from model.vector_db import upload_chunks_to_db


from pathlib import Path
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter, RecursiveJsonSplitter
import json



def ignore_file(filename):
    white_list_extensions = [".md", ".txt", ".pdf", ".csv", ".js", "json", ".py", ".java", ".html", ".css"]
    ignore_list = ["node_modules", "dist", "build", "out", "target", "vendor", "bin", "obj", "logs", "temp"]
    ignore_files = [".DS_Store", "Thumbs.db", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"]
    if any(filename.endswith(ext) for ext in white_list_extensions):
        if not any(ignore_dir in filename for ignore_dir in ignore_list):
            if filename not in ignore_files:
                return False
    return True


def process_repo(input_url):
    download_repo(input_url)

    os.mkdir("results") if not os.path.exists("results") else None

    files_nodes = []
    for root, _, files in os.walk(os.path.basename(input_url)):
        for file in files:
            if ignore_file(file):
                continue
            file_path = os.path.join(root, file)
            ext = Path(file).suffix.lower()
            file_data = {
            "file_path": file_path,
            "file_type": ext,
            "nodes": []
            }

            try:
                language = None
                doc = None
                if ext in ['.py', '.java', '.html', '.css']:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        code_content = f.read()
                    language = ext[1:]
                    doc = Document(text=code_content, metadata={"source": file_path, "type": "code"})

                if ext in ['.js', '.ts', '.jsx', '.tsx']:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        code_content = f.read()
                    doc = Document(text=code_content, metadata={"source": file_path, "type": "code"})
                    language = 'js' if ext in ['.js', '.jsx'] else 'ts'

                elif ext == '.json':
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    language = 'json'
                    json_str = json.dumps(data, indent=2)
                    doc = Document(text=f"\n```json\n{json_str}\n```",
                                   metadata={"source": file_path, "type": "config"})
                elif ext in ['.md', '.txt']:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text_content = f.read()
                    language = 'text'
                    doc = Document(text=text_content, metadata={"source": file_path, "type": "doc"})

                chunks = get_splitter_for_extension(language).split_documents([doc])
                file_data["nodes"].extend(chunks)
                files_nodes.append(file_data)
            except Exception as e:
                print(f"Skipping {file_path} due to error: {e}")
    upload_chunks_to_db(files_nodes, repo_id=os.path.basename(input_url))




def get_splitter_for_extension(lang: Language):
    if lang == 'text':
        return RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    if lang == 'json':
        return RecursiveJsonSplitter(chunk_size=1000, chunk_overlap=200)
    else:
        return RecursiveCharacterTextSplitter.from_language(
                language=lang, chunk_size=800, chunk_overlap=100
                )