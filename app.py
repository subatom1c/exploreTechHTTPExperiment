from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
import uuid

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_USERNAME_LEN = 32
MAX_MESSAGE_LEN = 240
MAX_STORED_MESSAGES = 100
PACKETS_DIR = os.path.join(BASE_DIR, "packets")

USERS: set[str] = set()
MESSAGES: list[dict[str, str]] = []
VOTES: dict[str, int] = {}
VOTERS: set[str] = set()
VOTER_TARGET: dict[str, str] = {}

app = Flask(__name__, template_folder=str(BASE_DIR))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-change-this-secret")

# Create packets directory if it doesn't exist
os.makedirs(PACKETS_DIR, exist_ok=True)


def _write_packet(packet_data: dict[str, str | int]) -> None:
    """Persist packet metadata in the packets directory."""
    # Create a unique filename with uuid and timestamp
    filename = f"packet_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.json"
    filepath = os.path.join(PACKETS_DIR, filename)

    with open(filepath, "w") as f:
        json.dump(packet_data, f, indent=2)


def _log_message_packet(from_username: str, to_username: str, message: str) -> None:
    _write_packet(
        {
            "packet_type": "message",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from_username": from_username,
            "to_username": to_username,
            "message": message,
        }
    )


def _log_vote_packet(from_username: str, target_username: str) -> None:
    _write_packet(
        {
            "packet_type": "vote",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from_username": from_username,
            "target_username": target_username,
            "vote_delta": 1,
        }
    )



def _load_users() -> list[str]:
    return sorted(USERS)


def _register_user(username: str) -> None:
    normalized = username.lower()
    USERS.add(normalized)
    VOTES.setdefault(normalized, 0)


def _user_exists(username: str) -> bool:
    return username.lower() in USERS


def _increment_vote(username: str) -> int:
    normalized = username.lower()
    VOTES[normalized] = VOTES.get(normalized, 0) + 1
    return VOTES[normalized]


def _build_vote_winner_message() -> str:
    users = _load_users()
    if not users:
        return "No users are available to determine a winner."

    ranking = sorted(((user, VOTES.get(user, 0)) for user in users), key=lambda item: (-item[1], item[0]))
    top_votes = ranking[0][1]

    if top_votes == 0:
        return "No winner yet because nobody has any votes."

    winners = [user for user, vote_count in ranking if vote_count == top_votes]
    if len(winners) == 1:
        return f"Winner: {winners[0]} with {top_votes} vote{'s' if top_votes != 1 else ''}."

    winners_text = ", ".join(winners)
    return f"Tie for winner between {winners_text} with {top_votes} vote{'s' if top_votes != 1 else ''} each."


def _broadcast_system_message(message_text: str) -> None:
    recipients = _load_users()
    if not recipients:
        return

    all_messages = _load_messages()
    timestamp_iso = datetime.now(timezone.utc).isoformat()

    for recipient in recipients:
        all_messages.append(
            {
                "from_username": "system",
                "to_username": recipient,
                "message": message_text,
                "timestamp_iso": timestamp_iso,
            }
        )

    _save_messages(all_messages)

    for recipient in recipients:
        _log_message_packet("system", recipient, message_text)


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
    username = request.form.get("username", "").strip().lower()

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

    recipient = request.form.get("recipient", "").strip().lower()
    text = request.form.get("message", "").strip()

    if not text:
        return _redirect_with_notice("messages", "Message cannot be empty.", "error")

    if len(text) > MAX_MESSAGE_LEN:
        return _redirect_with_notice("messages", f"Message must be {MAX_MESSAGE_LEN} characters or fewer.", "error")

    if text.lower() == "show":
        winner_message = _build_vote_winner_message()
        _broadcast_system_message(f"Vote result: {winner_message}")
        return _redirect_with_notice("messages", "Winner announcement sent to everyone.", "success")

    if not recipient:
        return _redirect_with_notice("messages", "Recipient username is required.", "error")

    if len(recipient) > MAX_USERNAME_LEN:
        return _redirect_with_notice("messages", f"Recipient must be {MAX_USERNAME_LEN} characters or fewer.", "error")

    if recipient == username:
        return _redirect_with_notice("messages", "You cannot message yourself.", "error")

    if not _user_exists(recipient):
        return _redirect_with_notice("messages", "Recipient is not registered yet.", "error")

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
    
    # Log packet to file
    _log_message_packet(username, recipient, text)

    return _redirect_with_notice("messages", f"Message sent to {recipient}.", "success")


@app.post("/vote")
def vote() -> tuple[str, int] | str:
    username = session.get("username")
    if not username:
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"error": "unauthorized"}), 401
        return _redirect_with_notice("index", "Please authenticate first.", "error")

    if username in VOTERS:
        voted_for = VOTER_TARGET.get(username)
        repeated_vote_message = "You have already used your one vote."
        if voted_for:
            repeated_vote_message = f"You already voted for {voted_for}."
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"error": repeated_vote_message}), 400
        return _redirect_with_notice("messages", repeated_vote_message, "error")

    target = request.form.get("target", "").strip().lower()

    if not target:
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"error": "Target username is required."}), 400
        return _redirect_with_notice("messages", "Target username is required.", "error")

    if target == username:
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"error": "You cannot vote for yourself."}), 400
        return _redirect_with_notice("messages", "You cannot vote for yourself.", "error")

    if not _user_exists(target):
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"error": "Target user is not registered yet."}), 404
        return _redirect_with_notice("messages", "Target user is not registered yet.", "error")

    new_total = _increment_vote(target)
    VOTERS.add(username)
    VOTER_TARGET[username] = target
    _log_vote_packet(username, target)

    if request.accept_mimetypes.best == "application/json":
        return jsonify(
            {
                "ok": True,
                "target": target,
                "vote_count": new_total,
                "notice": f"Vote sent to {target}.",
            }
        )

    return _redirect_with_notice("messages", f"Vote sent to {target}.", "success")


@app.post("/logout")
def logout() -> str:
    session.pop("username", None)
    return _redirect_with_notice("index", "You have been logged out.", "success")


@app.get("/api/session")
def session_state() -> tuple[str, int] | str:
    username = session.get("username")
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(
        {
            "username": username,
            "has_voted": username in VOTERS,
            "voted_for": VOTER_TARGET.get(username),
        }
    )


@app.get("/api/messages")
def messages_api() -> tuple[str, int] | str:
    username = session.get("username")
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    stored = _load_messages()
    inbox = [item for item in stored if item.get("to_username") == username]
    return jsonify({"messages": _format_for_view(inbox)})


@app.get("/api/users")
def users_api() -> tuple[str, int] | str:
    username = session.get("username")
    if not username:
        return jsonify({"error": "unauthorized"}), 401

    # Get all users except the current user
    all_users = [u for u in _load_users() if u != username]
    users_with_votes = [{"username": u, "vote_count": VOTES.get(u, 0)} for u in all_users]
    return jsonify({"users": users_with_votes})


@app.get("/api/leaderboard")
def leaderboard_api() -> tuple[str, int] | str:
    if not session.get("username"):
        return jsonify({"error": "unauthorized"}), 401
    
    stored = _load_messages()
    message_counts: dict[str, int] = {}
    
    # Initialize all users with 0 messages
    for user in _load_users():
        message_counts[user] = 0
    
    # Count messages sent by each user
    for item in stored:
        sender = item.get("from_username", "")
        if sender:
            message_counts[sender] = message_counts.get(sender, 0) + 1
    
    # Sort by message count (descending), then by username (ascending)
    leaderboard = sorted(
        [{"username": user, "message_count": count} for user, count in message_counts.items()],
        key=lambda x: (-x["message_count"], x["username"])
    )
    
    return jsonify({"leaderboard": leaderboard})


@app.get("/api/vote-leaderboard")
def vote_leaderboard_api() -> tuple[str, int] | str:
    if not session.get("username"):
        return jsonify({"error": "unauthorized"}), 401

    leaderboard = sorted(
        [{"username": user, "vote_count": VOTES.get(user, 0)} for user in _load_users()],
        key=lambda x: (-x["vote_count"], x["username"]),
    )

    return jsonify({"leaderboard": leaderboard})


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
