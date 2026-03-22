from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MESSAGES_FILE = DATA_DIR / "messages.json"
MAX_USERNAME_LEN = 32
MAX_MESSAGE_LEN = 240

app = Flask(__name__, template_folder=str(BASE_DIR))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-change-this-secret")


def _ensure_data_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not MESSAGES_FILE.exists():
        MESSAGES_FILE.write_text("[]", encoding="utf-8")


def _load_messages() -> list[dict[str, str]]:
    _ensure_data_file()
    try:
        data = json.loads(MESSAGES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = []

    if not isinstance(data, list):
        return []

    cleaned: list[dict[str, str]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        username = str(entry.get("username", "")).strip()
        message = str(entry.get("message", "")).strip()
        timestamp_iso = str(entry.get("timestamp_iso", "")).strip()
        if username and message and timestamp_iso:
            cleaned.append(
                {
                    "username": username,
                    "message": message,
                    "timestamp_iso": timestamp_iso,
                }
            )
    return cleaned[-100:]


def _save_messages(messages: list[dict[str, str]]) -> None:
    _ensure_data_file()
    MESSAGES_FILE.write_text(json.dumps(messages[-100:], indent=2), encoding="utf-8")


def _format_for_view(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    formatted: list[dict[str, str]] = []
    for entry in messages:
        timestamp_iso = entry["timestamp_iso"]
        try:
            dt = datetime.fromisoformat(timestamp_iso)
        except ValueError:
            dt = datetime.now(timezone.utc)

        formatted.append(
            {
                "username": entry["username"],
                "message": entry["message"],
                "timestamp_iso": timestamp_iso,
                "timestamp_display": dt.astimezone().strftime("%b %d, %H:%M"),
            }
        )

    return list(reversed(formatted))


def _redirect_with_notice(endpoint: str, text: str, level: str) -> str:
    target = url_for(endpoint)
    query = urlencode({"notice": text, "level": level})
    return redirect(f"{target}?{query}")


@app.get("/")
def index() -> str:
    if session.get("username"):
        return redirect(url_for("messages"))
    return render_template("authPage.html")


@app.get("/authPage.html")
def auth_page_alias() -> str:
    return redirect(url_for("index"))


@app.post("/authentication")
def authenticate() -> str:
    username = request.form.get("username", "").strip()

    if not username:
        return _redirect_with_notice("index", "Username is required.", "error")

    if len(username) > MAX_USERNAME_LEN:
        return _redirect_with_notice("index", f"Username must be {MAX_USERNAME_LEN} characters or fewer.", "error")

    session["username"] = username
    return _redirect_with_notice("messages", f"Welcome, {username}.", "success")


@app.get("/messages")
def messages() -> str:
    username = session.get("username")
    if not username:
        return _redirect_with_notice("index", "Please authenticate first.", "error")

    return render_template("messagingPage.html")


@app.get("/messagingPage.html")
def messaging_page_alias() -> str:
    return redirect(url_for("messages"))


@app.post("/message")
def message() -> str:
    username = session.get("username")
    if not username:
        return _redirect_with_notice("index", "Please authenticate first.", "error")

    text = request.form.get("message", "").strip()
    if not text:
        return _redirect_with_notice("messages", "Message cannot be empty.", "error")

    if len(text) > MAX_MESSAGE_LEN:
        return _redirect_with_notice("messages", f"Message must be {MAX_MESSAGE_LEN} characters or fewer.", "error")

    all_messages = _load_messages()
    all_messages.append(
        {
            "username": username,
            "message": text,
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save_messages(all_messages)

    return redirect(url_for("messages"))


@app.post("/logout")
def logout() -> str:
    session.pop("username", None)
    return _redirect_with_notice("index", "You have been logged out.", "success")


@app.get("/api/session")
def session_state() -> tuple[str, int] | str:
    username = session.get("username")
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"username": username})


@app.get("/api/messages")
def messages_api() -> tuple[str, int] | str:
    username = session.get("username")
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    stored = _load_messages()
    return jsonify({"messages": _format_for_view(stored)})


@app.get("/styles.css")
def stylesheet() -> str:
    return send_from_directory(str(BASE_DIR), "styles.css")


@app.get("/frontend.js")
def frontend_script() -> str:
    return send_from_directory(str(BASE_DIR), "frontend.js")


if __name__ == "__main__":
    _ensure_data_file()
    app.run(debug=True)
