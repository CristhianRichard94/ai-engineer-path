import re
import redis
import requests

from config import settings
from worker.app import celery
from process.main import process_repo
from logger import get_logger

log = get_logger("worker.tasks")
_redis = redis.from_url(settings.redis_url)


def _commit_key(url: str) -> str:
    return f"last_commit:{url}"


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
    val = _redis.get(_commit_key(url))
    return val.decode() if val else None


def store_commit(url: str, sha: str):
    _redis.set(_commit_key(url), sha)


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
