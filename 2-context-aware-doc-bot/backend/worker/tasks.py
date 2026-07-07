import hashlib
import json
import os
import re
import tempfile
import requests

from config import settings
from worker.app import celery
from process.main import process_repo
from logger import get_logger

log = get_logger("worker.tasks")

os.makedirs(settings.commit_cache_dir, exist_ok=True)


def _commit_key(url: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()
    return os.path.join(settings.commit_cache_dir, f"{digest}.json")


def get_latest_commit(url: str) -> str | None:
    match = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if not match:
        return None
    owner, repo = match.groups()
    api_url = f"{settings.github_api_url}/repos/{owner}/{repo}/commits/HEAD"
    try:
        response = requests.get(
            api_url,
            headers={"Accept": "application/vnd.github.sha"},
            timeout=10,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    sha = response.text.strip().strip('"')
    return sha if len(sha) == 40 else None


def get_stored_commit(url: str) -> str | None:
    path = _commit_key(url)
    try:
        with open(path, "r") as f:
            return json.load(f).get("sha")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def store_commit(url: str, sha: str):
    path = _commit_key(url)
    fd, tmp_path = tempfile.mkstemp(
        dir=settings.commit_cache_dir, prefix=".tmp-", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"sha": sha}, f)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


@celery.task(bind=True)
def index_repo_task(self, url: str):
    log.info("indexing start: url=%s task=%s", url, self.request.id)
    try:
        process_repo(url)
        sha = get_latest_commit(url)
        if sha:
            store_commit(url, sha)
        log.info("indexing done: url=%s", url)
        return {"status": "done", "url": url}
    except Exception as e:
        log.exception("indexing failed: url=%s", url)
        raise
