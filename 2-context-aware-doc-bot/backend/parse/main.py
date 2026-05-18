from parse.save_results import save

from parse.handle_files import handle_file
from dotenv import load_dotenv
from parse.download_repo import download_repo
import os



load_dotenv()


def get_clean_file_list(repo_name):
    file_list = os.listdir(f"temp{os.sep}{repo_name}")
    clean_file_list = []
    white_list_extensions = [".md", ".txt", ".pdf", ".csv", ".js", "json", ".py", ".java", ".html", ".css"]
    ignore_list = ["node_modules", "dist", "build", "out", "target", "vendor", "bin", "obj", "logs", "temp"]
    ignore_files = [".DS_Store", "Thumbs.db", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"]
    for filename in file_list:
        if any(filename.endswith(ext) for ext in white_list_extensions):
            if not any(ignore_dir in filename for ignore_dir in ignore_list):
                if filename not in ignore_files:
                    clean_file_list.append(filename)
    return clean_file_list


def parse_files(input_url):
    #get folder-safe repo name
    repo_name = os.path.basename(input_url)
    download_repo(input_url)
    clean_file_list = get_clean_file_list(repo_name)

    os.mkdir("results") if not os.path.exists("results") else None

    for filename in clean_file_list:
        file_path = f"{repo_name}{os.sep}{filename}"
        print(f"Parsing file: {filename}")
        result = handle_file("temp"+ os.sep + file_path)
        save(file_path, result)

