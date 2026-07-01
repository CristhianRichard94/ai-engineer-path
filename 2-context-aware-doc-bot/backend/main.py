import json

from flask import Flask, request, jsonify, redirect, Response
from flask_cors import CORS
from celery.result import AsyncResult
from swagger_ui import flask_api_doc
from logger import get_logger
from worker.tasks import index_repo_task, get_latest_commit, get_stored_commit
from model.vector_db import query_repository, is_repo_indexed
from services.llm import llm_prompt, llm_prompt_stream

log = get_logger()
app = Flask(__name__)
CORS(app)
BASE_API_PREFIX = "/api"
flask_api_doc(app, config_path="./openapi.yaml", url_prefix="/api/docs", title="API docs")


@app.route("/")
def root_redirect():
    return redirect("/api/docs")


@app.route(f"{BASE_API_PREFIX}/index", methods=["POST"])
def index_repo():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "url is required"}), 400

    current_commit = get_latest_commit(url)
    stored_commit = get_stored_commit(url)

    if current_commit and current_commit == stored_commit and is_repo_indexed(url):
        log.info("repo already up to date: url=%s commit=%s", url, current_commit)
        return jsonify({"status": "already_indexed", "commit": current_commit}), 200

    log.info("dispatching index task: url=%s commit=%s", url, current_commit)
    task = index_repo_task.delay(url)
    return jsonify({"job_id": task.id, "commit": current_commit}), 202


@app.route(f"{BASE_API_PREFIX}/index/<job_id>", methods=["GET"])
def index_status(job_id):
    result = AsyncResult(job_id)
    body = {"job_id": job_id, "status": result.status.lower()}
    if result.failed():
        body["error"] = str(result.result)
    elif result.successful():
        body.update(result.result)
    return jsonify(body)


def _validate_prompt_request(data):
    """Returns (url, user_prompt, error_response) — error_response is a
    (jsonify(...), status) tuple if validation failed, else None."""
    url = data.get("url")
    user_prompt = data.get("prompt")
    if not url:
        return url, user_prompt, (jsonify({"error": "url is required"}), 400)
    if not user_prompt:
        return url, user_prompt, (jsonify({"error": "prompt is required"}), 400)
    if not is_repo_indexed(url):
        return url, user_prompt, (
            jsonify({"error": "repo not indexed, call POST /api/index first"}),
            400,
        )
    return url, user_prompt, None


def _build_augmented_prompt(url, user_prompt, history=None):
    context = query_repository(user_prompt, repo_id=url)
    context_text = "\n".join(
        [f"- {item['text']} (from {item['file']})" for item in context]
    )

    if history:
        history_lines = ["Previous conversation:"]
        for entry in history:
            role = entry.get("role", "user").capitalize()
            content = entry.get("content", "")
            history_lines.append(f"{role}: {content}")
        history_text = "\n".join(history_lines)
        augmented = (
            f"{history_text}\n\nCurrent question: {user_prompt}\n\nContext:\n{context_text}"
        )
    else:
        augmented = f"{user_prompt}\n\nContext:\n{context_text}"

    return augmented


@app.route(f"{BASE_API_PREFIX}/prompt", methods=["POST"])
def retrieve_augmented_generation():
    data = request.get_json()
    url, user_prompt, error_response = _validate_prompt_request(data)
    if error_response:
        return error_response

    history = data.get("history", [])
    log.info("prompt request: url=%s", url)
    try:
        augmented = _build_augmented_prompt(url, user_prompt, history)
        response = llm_prompt(augmented)
        log.info("prompt success: url=%s", url)
        return jsonify({"response": response}), 200
    except Exception as e:
        log.exception("prompt error: url=%s", url)
        return jsonify({"error": str(e)}), 500


@app.route(f"{BASE_API_PREFIX}/prompt/stream", methods=["POST"])
def retrieve_augmented_generation_stream():
    data = request.get_json()
    url, user_prompt, error_response = _validate_prompt_request(data)
    if error_response:
        return error_response

    history = data.get("history", [])
    log.info("prompt stream request: url=%s", url)
    augmented = _build_augmented_prompt(url, user_prompt, history)

    def generate():
        try:
            for delta in llm_prompt_stream(augmented):
                yield f"data: {json.dumps({'delta': delta})}\n\n"
            log.info("prompt stream success: url=%s", url)
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            log.exception("prompt stream error: url=%s", url)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    response = Response(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.direct_passthrough = True
    return response


if __name__ == "__main__":
    app.run(debug=True)
