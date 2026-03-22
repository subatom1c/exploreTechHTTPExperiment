function showNotice() {
    const flashArea = document.getElementById("flash-area");
    if (!flashArea) {
        return;
    }

    const params = new URLSearchParams(window.location.search);
    const text = params.get("notice");
    const level = params.get("level") || "success";

    if (!text) {
        flashArea.hidden = true;
        return;
    }

    const p = document.createElement("p");
    p.className = `flash flash-${level}`;
    p.textContent = text;

    flashArea.replaceChildren(p);
    flashArea.hidden = false;

    params.delete("notice");
    params.delete("level");
    const nextQuery = params.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}`;
    window.history.replaceState({}, "", nextUrl);
}

async function fetchJson(url) {
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) {
        throw new Error(`Request failed for ${url}`);
    }
    return response.json();
}

function renderMessages(items) {
    const list = document.getElementById("messages-list");
    const empty = document.getElementById("empty-state");
    if (!list || !empty) {
        return;
    }

    list.replaceChildren();

    if (!items.length) {
        empty.hidden = false;
        return;
    }

    empty.hidden = true;

    for (const item of items) {
        const li = document.createElement("li");

        const row = document.createElement("div");
        row.className = "message-row";

        const user = document.createElement("strong");
        user.textContent = item.username;

        const time = document.createElement("time");
        time.setAttribute("datetime", item.timestamp_iso);
        time.textContent = item.timestamp_display;

        row.append(user, time);

        const text = document.createElement("p");
        text.textContent = item.message;

        li.append(row, text);
        list.append(li);
    }
}

async function bootstrapMessagingPage() {
    try {
        const sessionState = await fetchJson("/api/session");
        const usernameNode = document.getElementById("active-username");
        if (usernameNode) {
            usernameNode.textContent = sessionState.username;
        }

        const payload = await fetchJson("/api/messages");
        renderMessages(payload.messages || []);
    } catch {
        const params = new URLSearchParams({
            notice: "Please authenticate first.",
            level: "error",
        });
        window.location.replace(`/?${params.toString()}`);
    }
}

function init() {
    showNotice();

    const page = document.body.dataset.page;
    if (page === "messaging") {
        bootstrapMessagingPage();
    }
}

document.addEventListener("DOMContentLoaded", init);
