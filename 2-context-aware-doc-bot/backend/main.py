import json
import os
import uuid

import yaml
from flask import Flask, request, jsonify, redirect, Response
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from logger import get_logger
from worker.tasks import index_repo_task, get_latest_commit, get_stored_commit
from model.vector_db import query_repository, is_repo_indexed
from services.llm import llm_prompt, llm_prompt_stream

log = get_logger()
app = Flask(__name__)
CORS(app)
BASE_API_PREFIX = "/api"

SWAGGER_URL = "/api/docs"
API_SPEC_URL = "/api/docs/openapi.yaml"
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL, API_SPEC_URL, config={"app_name": "API docs"}
)
app.register_blueprint(swaggerui_blueprint)


@app.route(API_SPEC_URL)
def openapi_spec():
    spec_path = os.path.join(os.path.dirname(__file__), "openapi.yaml")
    with open(spec_path) as f:
        return jsonify(yaml.safe_load(f))


@app.route("/")
def root_redirect():
    return redirect("/api/docs")


@app.route(f"{BASE_API_PREFIX}/index", methods=["POST"])
def index_repo():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "request body must be valid JSON"}), 400
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    url = data.get("url")
    if not url:
        return jsonify({"error": "url is required"}), 400
    if not isinstance(url, str):
        return jsonify({"error": "url must be a string"}), 400

    try:
        current_commit = get_latest_commit(url)
        stored_commit = get_stored_commit(url)

        if current_commit and current_commit == stored_commit and is_repo_indexed(url):
            log.info("repo already up to date: url=%s commit=%s", url, current_commit)
            return jsonify({"status": "already_indexed", "commit": current_commit}), 200

        log.info("dispatching index task: url=%s commit=%s", url, current_commit)
        task = index_repo_task.delay(url)
        return jsonify({"job_id": task.id, "commit": current_commit}), 202
    except Exception as e:
        log.exception("index error: url=%s", url)
        return jsonify({"error": "internal server error"}), 500


@app.route(f"{BASE_API_PREFIX}/index/<job_id>", methods=["GET"])
def index_status(job_id):
    try:
        parsed = uuid.UUID(job_id)
    except ValueError:
        return jsonify({"error": "invalid job_id format"}), 400
    if parsed.version != 4:
        return jsonify({"error": "invalid job_id format"}), 400

    try:
        result = index_repo_task.AsyncResult(job_id)
        body = {"job_id": job_id, "status": result.status.lower()}
        if result.failed():
            log.exception("index task failed: job_id=%s", job_id, exc_info=result.result)
            body["error"] = "task failed, see server logs for details"
        elif result.successful():
            body.update(result.result)
        return jsonify(body)
    except Exception as e:
        log.exception("index status error: job_id=%s", job_id)
        return jsonify({"error": "unable to retrieve job status, try again shortly"}), 500


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


def _build_augmented_prompt(url, user_prompt):
    context = query_repository(user_prompt, repo_id=url)
    return f"{user_prompt}\n\nContext:\n" + "\n".join(
        [f"- {item['text']} (from {item['file']})" for item in context]
    )


@app.route(f"{BASE_API_PREFIX}/prompt", methods=["POST"])
def retrieve_augmented_generation():
    data = request.get_json()
    url, user_prompt, error_response = _validate_prompt_request(data)
    if error_response:
        return error_response

    log.info("prompt request: url=%s", url)
    try:
        augmented = _build_augmented_prompt(url, user_prompt)
        response = llm_prompt(augmented)
        log.info("prompt success: url=%s", url)
        return jsonify({"response": response}), 200
    except Exception as e:
        log.exception("prompt error: url=%s", url)
        return jsonify({"error": "internal server error"}), 500


@app.route(f"{BASE_API_PREFIX}/prompt/stream", methods=["POST"])
def retrieve_augmented_generation_stream():
    data = request.get_json()
    url, user_prompt, error_response = _validate_prompt_request(data)
    if error_response:
        return error_response

    log.info("prompt stream request: url=%s", url)
    augmented = _build_augmented_prompt(url, user_prompt)

    def generate():
        try:
            for delta in llm_prompt_stream(augmented):
                yield f"data: {json.dumps({'delta': delta})}\n\n"
            log.info("prompt stream success: url=%s", url)
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            log.exception("prompt stream error: url=%s", url)
            yield f"data: {json.dumps({'error': 'internal server error'})}\n\n"

    response = Response(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.direct_passthrough = True
    return response


if __name__ == "__main__":
    # Bind to 0.0.0.0 and read PORT from env so this works both locally
    # (docker-compose maps 5000:5000) and on cloud platforms like Fly.io
    # that assign the port dynamically.
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("APP_ENV", "development") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
