



import io
import os
import re
import shutil
import subprocess
import zipfile

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

    # ponytail: PowerShell download — bypasses broken OpenSSL, uses .NET TLS stack
    for branch in ("main", "master"):
        zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
        result = subprocess.run(
            ["curl.exe", "-L", "-s", "-o", zip_path, zip_url],
            capture_output=True, text=True
        )
        if result.returncode == 0 and os.path.exists(zip_path):
            break
    else:
        raise RuntimeError(f"Failed to download {input_url}: {result.stderr}")

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(CLONE_DIR)
        extracted = z.namelist()[0].split("/")[0]
    os.remove(zip_path)

    extracted_path = os.path.join(CLONE_DIR, extracted)
    if extracted_path != dest:
        os.rename(extracted_path, dest)

    return dest

