# website app

import os
from pathlib import Path

import requests
from dotenv import dotenv_values
from flask import Flask, render_template, request, jsonify
import time

from logger import export_daily_backup, init_db, log_interaction, log_user_credentials

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
init_db()



def is_placeholder_value(value):
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized in {
        "your_hugging_face_token_here",
        "your_groq_api_key_here",
        "your_openai_api_key_here",
        "changeme",
        "placeholder",
    } or normalized.startswith("your_") or normalized.startswith("changeme")


ENV_FILE_VALUES = {}


def refresh_env_values():
    global ENV_FILE_VALUES
    ENV_FILE_VALUES = {}
    for env_path in (BASE_DIR / ".env", BASE_DIR / ".env.example"):
        if env_path.exists():
            parsed = dotenv_values(env_path)
            for key, value in parsed.items():
                if value is not None and key not in ENV_FILE_VALUES:
                    ENV_FILE_VALUES[key] = value.strip()

    for key, value in ENV_FILE_VALUES.items():
        current_value = os.environ.get(key)
        if not current_value or is_placeholder_value(current_value):
            os.environ[key] = value


refresh_env_values()

START_TIME = time.time()

HF_MODEL = "google/flan-t5-small"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
DEFAULT_OPENAI_MODEL = "gpt-3.5-turbo"


def get_env_value(name, default=None):
    refresh_env_values()
    value = os.environ.get(name)
    if value is None or is_placeholder_value(value):
        value = ENV_FILE_VALUES.get(name, default)
    if value is None:
        return None
    return value.strip() or None


def get_hf_token():
    return get_env_value("HUGGINGFACE_API_TOKEN") or get_env_value("HF_API_TOKEN")


def get_groq_key():
    return get_env_value("GROQ_API_KEY") or get_env_value("GROQ_API_TOKEN")


def get_groq_model():
    return get_env_value("GROQ_MODEL") or get_env_value("GROQ-MODEL") or DEFAULT_GROQ_MODEL


def get_openai_key():
    return get_env_value("OPENAI_API_KEY") or get_env_value("OPENAI_TOKEN")


def get_openai_model():
    return get_env_value("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)


def has_real_value(value):
    if not value:
        return False
    return value.strip().lower() not in {"your_hugging_face_token_here", "your_groq_api_key_here", "your_openai_api_key_here", "changeme", "placeholder"}


def get_hf_response(user_message):
    hf_token = get_hf_token()
    if not has_real_value(hf_token):
        return None

    url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {
        "Authorization": f"Bearer {hf_token}",
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
    groq_key = get_groq_key()
    if not has_real_value(groq_key):
        return None

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": get_groq_model(),
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
    if not (get_groq_key() or get_hf_token() or get_openai_key()):
        app.logger.warning("AI credentials are not configured; using fallback reply")

    groq_result = get_groq_response(user_message)
    if groq_result:
        return {"reply": groq_result, "provider": "groq"}

    hf_result = get_hf_response(user_message)
    if hf_result:
        return {"reply": hf_result, "provider": "huggingface"}

    openai_result = get_openai_response(user_message)
    if openai_result:
        return {"reply": openai_result, "provider": "openai"}

    fallback = [
        "I'm ready to help. Tell me more about what you need.",
        "Thanks for your message! What would you like to talk about next?",
        "I can answer questions or help you brainstorm ideas.",
        "Let's keep going. What should we discuss now?",
    ]
    return {
        "reply": fallback[hash(user_message) % len(fallback)],
        "provider": "fallback",
        "debug": "No provider responded successfully. Check API keys and quotas.",
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message") or "").strip()
    user_id = (payload.get("user_id") or "anonymous").strip()

    if not user_message:
        log_interaction(
            prompt="",
            response="Please enter a message.",
            error="empty_message",
            model_used="chat",
            user_id=user_id,
        )
        return jsonify({"reply": "Please enter a message."}), 400

    try:
        result = get_bot_response(user_message)
        payload = {"reply": result["reply"], "provider": result["provider"]}
        if result.get("debug"):
            payload["debug"] = result["debug"]

        log_interaction(
            prompt=user_message,
            response=result["reply"],
            model_used=result.get("provider", "unknown"),
            user_id=user_id,
        )
        return jsonify(payload)
    except Exception as exc:
        log_interaction(
            prompt=user_message,
            response=None,
            error=str(exc),
            model_used="chat",
            user_id=user_id,
        )
        app.logger.exception("Chat request failed")
        return jsonify({"reply": "Sorry, something went wrong while processing your message."}), 500


@app.route("/admin/logs")
def admin_logs():
    import sqlite3

    conn = sqlite3.connect("chat_logs.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, timestamp, user_id, model_used, prompt, response, error, status FROM interaction_logs ORDER BY id DESC LIMIT 100"
    ).fetchall()
    conn.close()

    return render_template("admin_logs.html", logs=rows)


@app.route("/backup-logs")
def backup_logs():
    folder_name = (request.args.get("folder_name") or "chat_log_backups").strip() or "chat_log_backups"
    backup_dir = Path.home() / "Desktop" / folder_name

    try:
        backup_path = export_daily_backup(backup_dir=str(backup_dir))
        return jsonify({"status": "ok", "folder": folder_name, "backup_path": backup_path})
    except Exception as exc:
        app.logger.exception("Failed to create backup")
        return jsonify({"status": "error", "message": str(exc)}), 500


def get_openai_response(user_message):
    openai_key = get_openai_key()
    if not has_real_value(openai_key):
        return None

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openai_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": get_openai_model(),
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


@app.route('/status', methods=['GET'])
def status():
    """Return basic service status and simple AI endpoint reachability/latency."""
    checks = {}

    # uptime
    checks['uptime_seconds'] = int(time.time() - START_TIME)
    checks['time'] = int(time.time())

    checks['env'] = {
        'groq_configured': bool(get_groq_key()),
        'huggingface_configured': bool(get_hf_token()),
        'openai_configured': bool(get_openai_key()),
    }

    # check groq reachability
    groq_key = get_groq_key()
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
    hf_key = get_hf_token()
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

    # check openai reachability
    openai_key = get_openai_key()
    if openai_key:
        try:
            t0 = time.time()
            resp = requests.get('https://api.openai.com/v1/models', headers={
                'Authorization': f'Bearer {openai_key}',
            }, timeout=3)
            latency = int((time.time() - t0) * 1000)
            checks['openai'] = {'reachable': resp.ok, 'latency_ms': latency}
        except requests.RequestException:
            checks['openai'] = {'reachable': False, 'latency_ms': None}
    else:
        checks['openai'] = {'reachable': False, 'latency_ms': None}

    # aggregate status
    providers = []
    if checks['groq']['reachable']:
        providers.append('groq')
    if checks['huggingface']['reachable']:
        providers.append('huggingface')
    if checks['openai']['reachable']:
        providers.append('openai')

    checks['providers_available'] = providers
    checks['overall'] = 'online' if providers else 'degraded'

    return jsonify(checks)


if __name__ == "__main__":
    print("Starting app")
    app.run(debug=True)