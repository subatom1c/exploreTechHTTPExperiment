from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlencode

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_USERNAME_LEN = 32
MAX_MESSAGE_LEN = 240
MAX_STORED_MESSAGES = 100

USERS: set[str] = set()
MESSAGES: list[dict[str, str]] = []

app = Flask(__name__, template_folder=str(BASE_DIR))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-change-this-secret")


def _load_users() -> list[str]:
    return sorted(USERS)


def _register_user(username: str) -> None:
    USERS.add(username)


def _user_exists(username: str) -> bool:
    return username in USERS


def _load_messages() -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for entry in MESSAGES:
        if not isinstance(entry, dict):
            continue
        sender = str(entry.get("from_username", entry.get("username", ""))).strip()
        recipient = str(entry.get("to_username", "")).strip()
        message = str(entry.get("message", "")).strip()
        timestamp_iso = str(entry.get("timestamp_iso", "")).strip()
        if sender and recipient and message and timestamp_iso:
            cleaned.append(
                {
                    "from_username": sender,
                    "to_username": recipient,
                    "message": message,
                    "timestamp_iso": timestamp_iso,
                }
            )
    return cleaned[-100:]


def _save_messages(messages: list[dict[str, str]]) -> None:
    global MESSAGES
    MESSAGES = messages[-MAX_STORED_MESSAGES:]


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
                "username": entry["from_username"],
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

    _register_user(username)
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

    recipient = request.form.get("recipient", "").strip()
    text = request.form.get("message", "").strip()

    if not recipient:
        return _redirect_with_notice("messages", "Recipient username is required.", "error")

    if len(recipient) > MAX_USERNAME_LEN:
        return _redirect_with_notice("messages", f"Recipient must be {MAX_USERNAME_LEN} characters or fewer.", "error")

    if recipient == username:
        return _redirect_with_notice("messages", "You cannot message yourself.", "error")

    if not _user_exists(recipient):
        return _redirect_with_notice("messages", "Recipient is not registered yet.", "error")

    if not text:
        return _redirect_with_notice("messages", "Message cannot be empty.", "error")

    if len(text) > MAX_MESSAGE_LEN:
        return _redirect_with_notice("messages", f"Message must be {MAX_MESSAGE_LEN} characters or fewer.", "error")

    all_messages = _load_messages()
    all_messages.append(
        {
            "from_username": username,
            "to_username": recipient,
            "message": text,
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save_messages(all_messages)

    return _redirect_with_notice("messages", f"Message sent to {recipient}.", "success")


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
    inbox = [item for item in stored if item.get("to_username") == username]
    return jsonify({"messages": _format_for_view(inbox)})


@app.get("/styles.css")
def stylesheet() -> str:
    return send_from_directory(BASE_DIR, "styles.css")


@app.get("/frontend.js")
def frontend_script() -> str:
    return send_from_directory(BASE_DIR, "frontend.js")

@app.before_request
def log_request():
    print("HIT:", request.method, request.path)

@app.get("/ping")
def ping():
    return "pong", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=50444, debug=True)
