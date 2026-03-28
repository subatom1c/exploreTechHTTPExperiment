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

async function postForm(url, payload) {
    const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            Accept: "application/json",
        },
        body: new URLSearchParams(payload),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || `Request failed for ${url}`);
    }
    return data;
}

function showInlineNotice(text, level = "success") {
    const flashArea = document.getElementById("flash-area");
    if (!flashArea || !text) {
        return;
    }

    const p = document.createElement("p");
    p.className = `flash flash-${level}`;
    p.textContent = text;
    flashArea.replaceChildren(p);
    flashArea.hidden = false;
}

let userVoteState = {
    hasVoted: false,
    votedFor: null,
};
let activeUsername = null;

async function refreshVotePanels() {
    const [usersPayload, leaderboardPayload] = await Promise.all([
        fetchJson("/api/users"),
        fetchJson("/api/vote-leaderboard"),
    ]);

    renderUsers(usersPayload.users || []);
    renderLeaderboard(leaderboardPayload.leaderboard || []);
}

async function submitVote(username) {
    return postForm("/vote", { target: username });
}

function setupShowCommandForm() {
    const composeForm = document.getElementById("compose-form");
    const recipientInput = composeForm?.querySelector('input[name="recipient"]');
    const messageInput = composeForm?.querySelector('input[name="message"]');
    if (!composeForm || !recipientInput || !messageInput) {
        return;
    }

    const recipientDefaultPlaceholder = "Send to username";

    const syncCommandMode = () => {
        const isShowCommand = messageInput.value.trim().toLowerCase() === "show";
        recipientInput.required = !isShowCommand;
        recipientInput.placeholder = isShowCommand ? "Recipient ignored for show command" : recipientDefaultPlaceholder;
    };

    messageInput.addEventListener("input", syncCommandMode);
    composeForm.addEventListener("submit", syncCommandMode);
    syncCommandMode();
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

function renderLeaderboard(items) {
    const list = document.getElementById("vote-leaderboard-list");
    const empty = document.getElementById("vote-leaderboard-empty");
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
        li.className = "leaderboard-item";

        const details = document.createElement("div");
        details.className = "lb-details";

        const nameSpan = document.createElement("span");
        nameSpan.className = "lb-name";
        nameSpan.textContent = item.username;

        const countSpan = document.createElement("span");
        countSpan.className = "lb-count";
        countSpan.textContent = `${item.vote_count} vote${item.vote_count !== 1 ? "s" : ""}`;

        details.append(nameSpan, countSpan);

        const voteButton = document.createElement("button");
        voteButton.type = "button";
        voteButton.className = "vote-button";

        if (item.username === activeUsername) {
            voteButton.textContent = "You";
            voteButton.disabled = true;
        } else if (userVoteState.hasVoted) {
            const didVoteForCurrentItem = userVoteState.votedFor === item.username;
            voteButton.textContent = didVoteForCurrentItem ? "Voted" : "Vote";
            voteButton.disabled = true;
        } else {
            voteButton.textContent = "Vote";
        }

        voteButton.addEventListener("click", async () => {
            if (item.username === activeUsername) {
                showInlineNotice("You cannot vote for yourself.", "error");
                return;
            }

            if (userVoteState.hasVoted) {
                showInlineNotice("You already used your one vote.", "error");
                return;
            }

            voteButton.disabled = true;
            try {
                const payload = await submitVote(item.username);
                userVoteState.hasVoted = true;
                userVoteState.votedFor = payload.target || item.username;
                showInlineNotice(payload.notice || `Vote sent to ${item.username}.`, "success");
                await refreshVotePanels();
            } catch (error) {
                const message = error instanceof Error ? error.message : "Failed to vote.";
                showInlineNotice(message, "error");
            } finally {
                voteButton.disabled = false;
            }
        });

        li.append(details, voteButton);
        list.append(li);
    }
}

function renderUsers(items) {
    const list = document.getElementById("users-list");
    const empty = document.getElementById("users-empty");
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
        const username = typeof item === "string" ? item : item.username;

        const li = document.createElement("li");
        li.className = "user-item";
        li.tabIndex = 0;
        li.setAttribute("role", "button");
        li.setAttribute("aria-label", `Select ${username} as recipient`);

        const identity = document.createElement("span");
        identity.className = "user-name-button";
        identity.textContent = username;
        identity.title = "Click row to fill recipient";

        const selectRecipient = () => {
            const recipientInput = document.querySelector('input[name="recipient"]');
            if (recipientInput) {
                recipientInput.value = username;
                recipientInput.focus();
            }
        };

        li.addEventListener("click", selectRecipient);
        li.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectRecipient();
            }
        });

        li.append(identity);
        list.append(li);
    }
}

async function subscribeToUpdates() {
    const page = document.body.dataset.page;
    if (page !== "messaging") return;

    const updateData = async () => {
        try {
            const payload = await fetchJson("/api/messages");
            renderMessages(payload.messages || []);
        } catch (error) {
            console.error("Failed to fetch messages:", error);
        }

        try {
            await refreshVotePanels();
        } catch (error) {
            console.error("Failed to fetch users or vote leaderboard:", error);
        }
    };

    // Initial update
    await updateData();

    // Poll for updates every 3 seconds
    setInterval(updateData, 3000);
}

async function bootstrapMessagingPage() {
    try {
        const sessionState = await fetchJson("/api/session");
        const usernameNode = document.getElementById("active-username");
        if (usernameNode) {
            usernameNode.textContent = sessionState.username;
        }
        activeUsername = sessionState.username;

        userVoteState = {
            hasVoted: Boolean(sessionState.has_voted),
            votedFor: sessionState.voted_for || null,
        };

        setupShowCommandForm();

        // Start subscribing to updates
        await subscribeToUpdates();
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
