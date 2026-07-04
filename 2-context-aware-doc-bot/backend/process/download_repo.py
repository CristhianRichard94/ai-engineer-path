



import io
import os
import re
import shutil
import zipfile

import requests

CLONE_DIR = "temp"

def download_repo(input_url):
    match = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", input_url)
    if not match:
        raise ValueError(f"Unsupported URL format: {input_url}")
    owner, repo = match.groups()

    dest = os.path.join(CLONE_DIR, repo)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(CLONE_DIR, exist_ok=True)

    zip_path = os.path.join(CLONE_DIR, f"{repo}.zip")

    last_error = None
    for branch in ("main", "master"):
        zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
        try:
            with requests.get(zip_url, stream=True, timeout=30, allow_redirects=True) as response:
                if response.status_code != 200:
                    last_error = f"HTTP {response.status_code}"
                    continue
                with open(zip_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
        except requests.RequestException as e:
            last_error = str(e)
            continue
        if os.path.exists(zip_path):
            break
    else:
        raise RuntimeError(f"Failed to download {input_url}: {last_error}")

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(CLONE_DIR)
        extracted = z.namelist()[0].split("/")[0]
    os.remove(zip_path)

    extracted_path = os.path.join(CLONE_DIR, extracted)
    if extracted_path != dest:
        os.rename(extracted_path, dest)

    return dest

