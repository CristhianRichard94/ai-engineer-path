
import os


def save(file_path, result):
    # Recursively create directories if they don't exist
    os.makedirs(os.path.dirname(f"results/{file_path}.md"), exist_ok=True)
    with open(f"results/{file_path}.md", "a", encoding="utf-8") as f:
        f.write(result)