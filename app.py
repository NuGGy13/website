# website app

import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
import time

app = Flask(__name__)
load_dotenv(Path(__file__).resolve().parent / ".env")
START_TIME = time.time()

HF_MODEL = "google/flan-t5-small"
HF_API_TOKEN = os.environ.get("HUGGINGFACE_API_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")


def has_real_value(value):
    if not value:
        return False
    return value.strip().lower() not in {"your_hugging_face_token_here", "your_groq_api_key_here", "changeme", "placeholder"}


def get_hf_response(user_message):
    if not has_real_value(HF_API_TOKEN):
        return None

    url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {
        "Authorization": f"Bearer {HF_API_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "inputs": (
            "You are a helpful assistant. Answer the user's question clearly.\n"
            f"User: {user_message}\n"
            "Assistant:"
        )
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        output = response.json()

        if isinstance(output, list) and output and "generated_text" in output[0]:
            return output[0]["generated_text"].strip()

        if isinstance(output, dict) and "error" in output:
            return None
    except requests.RequestException:
        return None

    return None


def get_groq_response(user_message):
    if not has_real_value(GROQ_API_KEY):
        return None

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.7,
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        output = response.json()
        if output.get("choices"):
            return output["choices"][0]["message"]["content"].strip()
    except requests.RequestException:
        return None

    return None


def get_bot_response(user_message):
    groq_result = get_groq_response(user_message)
    if groq_result:
        return groq_result

    hf_result = get_hf_response(user_message)
    if hf_result:
        return hf_result

    fallback = [
        "I'm ready to help. Tell me more about what you need.",
        "Thanks for your message! What would you like to talk about next?",
        "I can answer questions or help you brainstorm ideas.",
        "Let's keep going. What should we discuss now?",
    ]
    return fallback[hash(user_message) % len(fallback)]


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message") or "").strip()

    if not user_message:
        return jsonify({"reply": "Please enter a message."}), 400

    reply = get_bot_response(user_message)
    return jsonify({"reply": reply})


@app.route('/status', methods=['GET'])
def status():
    """Return basic service status and simple AI endpoint reachability/latency."""
    checks = {}

    # uptime
    checks['uptime_seconds'] = int(time.time() - START_TIME)
    checks['time'] = int(time.time())

    # check groq reachability
    groq_key = os.environ.get('GROQ_API_KEY')
    if groq_key:
        try:
            t0 = time.time()
            resp = requests.head('https://api.groq.com/', timeout=2)
            latency = int((time.time() - t0) * 1000)
            checks['groq'] = {'reachable': resp.ok, 'latency_ms': latency}
        except requests.RequestException:
            checks['groq'] = {'reachable': False, 'latency_ms': None}
    else:
        checks['groq'] = {'reachable': False, 'latency_ms': None}

    # check huggingface reachability
    hf_key = os.environ.get('HUGGINGFACE_API_TOKEN')
    if hf_key:
        try:
            t0 = time.time()
            resp = requests.head('https://api-inference.huggingface.co/', timeout=2)
            latency = int((time.time() - t0) * 1000)
            checks['huggingface'] = {'reachable': resp.ok, 'latency_ms': latency}
        except requests.RequestException:
            checks['huggingface'] = {'reachable': False, 'latency_ms': None}
    else:
        checks['huggingface'] = {'reachable': False, 'latency_ms': None}

    # aggregate status
    providers = []
    if checks['groq']['reachable']:
        providers.append('groq')
    if checks['huggingface']['reachable']:
        providers.append('huggingface')

    checks['providers_available'] = providers
    checks['overall'] = 'online' if providers else 'degraded'

    return jsonify(checks)


if __name__ == "__main__":
    print("Starting app")
    app.run(debug=True)