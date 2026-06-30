from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from process.main import process_repo
from model.vector_db import query_repository
from swagger_ui import flask_api_doc
from logger import get_logger

log = get_logger()

app = Flask(__name__)
CORS(app)
BASE_API_PREFIX = '/api'
flask_api_doc(app, config_path='./openapi.yaml', url_prefix='/api/docs', title='API docs')


@app.route('/')
def root_redirect():
    return redirect('/api/docs')


@app.route(f'{BASE_API_PREFIX}/prompt', methods=['POST'])
def retrieve_augmented_generation():
    data = request.get_json()
    input_url = data.get('url')
    prompt = data.get('prompt')
    if not input_url:
        return jsonify({"error": "URL is required"}), 400

    log.info("prompt request: url=%s", input_url)
    try:
        process_repo(input_url)
        context = query_repository(prompt, repo_id=input_url)
        response = f"{prompt}\n\nContext:\n" + "\n".join([f"- {item['text']} (from {item['file']})" for item in context])
        log.info("prompt success: url=%s", input_url)
        return jsonify({"response": response}), 200
    except Exception as e:
        log.exception("prompt error: url=%s", input_url)
        return jsonify({"error": str(e)}), 500



if __name__ == '__main__':
    app.run(debug=True)
