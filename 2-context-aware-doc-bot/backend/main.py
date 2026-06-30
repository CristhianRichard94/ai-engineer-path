from flask import Flask, request, jsonify
from flask_cors import CORS
from parse.main import parse_repo
from model.vector_db import query_repository


app = Flask(__name__)
CORS(app)

@app.route('/prompt', methods=['POST'])
def parse():
    data = request.get_json()
    input_url = data.get('url')
    prompt = data.get('prompt')
    if not input_url:
        return jsonify({"error": "URL is required"}), 400

    try:
        parse_repo(input_url)
        context = query_repository(prompt, repo_id=input_url)
        augmented_prompt = f"{prompt}\n\nContext:\n" + "\n".join([f"- {item['text']} (from {item['file']})" for item in context])
        return jsonify({"response": augmented_prompt}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)