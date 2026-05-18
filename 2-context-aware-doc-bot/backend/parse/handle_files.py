
import os

from langchain_text_splitters import RecursiveCharacterTextSplitter
from parse.prompt_ia import prompt_ia
from llama_cloud import LlamaCloud

openai_api_key = os.getenv("LLAMA_CLOUD_API_KEY")

client = LlamaCloud()


def parse_file(file_path):
    file = client.files.create(file=file_path, purpose="parse")
    parse_result = client.parsing.parse(
        file_id=file.id,
        tier="agentic",
        version="latest",
        expand=["markdown"],
    )
    return parse_result.markdown.pages[0].markdown

def handle_document(filename):
    parse_result = parse_file(filename)
    return parse_result

def handle_json(document):
    prompt = "Extract the key information from this JSON document and summarize it in a concise manner."
    summary = prompt_ia(prompt, document)
    summary_path = "temp/summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    parse_result = parse_file(summary_path)
    return parse_result


def handle_code_file(document):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=0)
    return text_splitter.split_text(document)


def handle_file(file_path):
    file_content = open(file_path, "r").read()
    if file_path.endswith(".json"):
        result = handle_json(file_content)
    elif file_path.endswith(".csv") or file_path.endswith(".txt") or file_path.endswith(".md") or file_path.endswith(".pdf"):
        result = handle_document(file_path)
    elif file_path.endswith(".js") or file_path.endswith(".py") or file_path.endswith(".java") or file_path.endswith(".html") or file_path.endswith(".css"):
        result = handle_code_file(file_content)
    else:
        print(f"Unsupported file type: {file_path}")
        result = None
    return result
