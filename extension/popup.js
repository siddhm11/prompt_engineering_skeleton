// ════════════════════════════════════════════════════════════════
// Prompt Memory — Extension Popup (Google OAuth Only)
// ════════════════════════════════════════════════════════════════

const DEFAULT_API_URL = "https://siddhm11-prompt-engine.hf.space";  // ← production
// const DEFAULT_API_URL = "http://localhost:8000";  // ← local testing
let API_URL = DEFAULT_API_URL;

const loginSection = document.getElementById("login-section");
const profileSection = document.getElementById("profile-section");
const statusText = document.getElementById("status");
const userDisplay = document.getElementById("user-display");
const profileAvatar = document.getElementById("profile-avatar");
const googleBtn = document.getElementById("google-login-btn");
const logoutBtn = document.getElementById("logout-btn");

// ── Init: Load API URL + check login state ──
chrome.storage.local.get(["user_id", "email", "token", "api_url"], async (result) => {
    if (result.api_url) API_URL = result.api_url;

    if (result.user_id && result.email && result.token) {
        // Auto-refresh token if expiring within 2 days
        if (isTokenExpiringSoon(result.token, 2)) {
            await tryRefreshToken(result.token);
        }
        showProfile(result.email);
    }
});

// ── Token helpers ──
function isTokenExpiringSoon(token, days = 2) {
    try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        const expiresAt = payload.exp * 1000;
        return expiresAt < Date.now() + days * 24 * 60 * 60 * 1000;
    } catch {
        return false;
    }
}

async function tryRefreshToken(token) {
    try {
        const res = await fetch(`${API_URL}/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token }),
        });
        if (res.ok) {
            const data = await res.json();
            chrome.storage.local.set({ token: data.token, email: data.email, user_id: data.user_id });
            return true;
        }
    } catch (e) {
        console.log("Popup: token refresh failed", e);
    }
    return false;
}

// ── Google Login ──
googleBtn.addEventListener("click", () => {
    statusText.innerText = "Opening Google...";
    const width = 500;
    const height = 600;
    const left = (screen.width - width) / 2;
    const top = (screen.height - height) / 2;

    fetch(`${API_URL}/auth/google/login`)
        .then(res => res.json())
        .then(data => {
            window.open(data.url, "GoogleLogin", `width=${width},height=${height},top=${top},left=${left}`);
            statusText.innerText = "Complete sign-in in the popup...";
        })
        .catch(err => {
            statusText.innerText = "Connection error. Try again.";
            console.error("Google login error:", err);
        });
});

// ── Listen for Google callback message ──
window.addEventListener("message", (event) => {
    if (event.data.type === "GOOGLE_AUTH_SUCCESS") {
        const { token, email, user_id } = event.data;
        chrome.storage.local.set({ user_id, email, token }, () => {
            statusText.innerText = "";
            showProfile(email);
        });
    }
});

// ── Logout ──
logoutBtn.addEventListener("click", () => {
    chrome.storage.local.remove(["user_id", "email", "token"], () => {
        showLogin();
    });
});

// ════════════════════════════════════════════════════════════════
// BYOK — the user's own free API key
// ════════════════════════════════════════════════════════════════
//
// Kept in chrome.storage.local, deliberately NOT chrome.storage.sync: sync
// replicates through the user's Google account to every browser they are
// signed into, which is not somewhere an API key should travel silently.
//
// The key is read here and by the service worker. The content script — which
// runs alongside chatgpt.com and claude.ai — never receives it.

const PROVIDER_INFO = {
    groq: {
        label: "Groq",
        keysUrl: "https://console.groq.com/keys",
        privacy: "Your prompts go straight from your browser to Groq. Groq does not train on API inputs.",
        models: [
            ["qwen/qwen3.8-27b", "Qwen 3.8 27B — fastest, best Hinglish"],
            ["qwen/qwen3.6-27b", "Qwen 3.6 27B"],
            ["openai/gpt-oss-120b", "GPT-OSS 120B — strongest English"],
            ["openai/gpt-oss-20b", "GPT-OSS 20B"],
        ],
    },
    gemini: {
        label: "Google Gemini",
        keysUrl: "https://aistudio.google.com/apikey",
        // Stated up front rather than buried: Google's own pricing table marks
        // free-tier data "Used to improve our products: Yes" (paid tier: "No").
        privacy: "Free, but Google may use free-tier prompts to improve their products. Groq does not.",
        models: [
            ["gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite — fastest"],
            ["gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite"],
            ["gemini-3.5-flash", "Gemini 3.5 Flash"],
        ],
    },
    openrouter: {
        label: "OpenRouter",
        keysUrl: "https://openrouter.ai/keys",
        privacy: "Data policy depends on the upstream provider you route to.",
        models: [["", "Type a model id below"]],
    },
};

const providerSel = document.getElementById("key-provider");
const modelSel = document.getElementById("key-model");
const keyInput = document.getElementById("key-input");
const keyStatus = document.getElementById("key-status");
const keyPill = document.getElementById("key-pill");
const keyLink = document.getElementById("key-get-link");
const keyPrivacy = document.getElementById("key-privacy");

function renderProvider(providerId, selectedModel) {
    const info = PROVIDER_INFO[providerId] || PROVIDER_INFO.groq;
    keyLink.href = info.keysUrl;
    keyLink.textContent = `Get a free ${info.label} key →`;
    keyPrivacy.textContent = info.privacy;

    modelSel.innerHTML = "";
    for (const [id, label] of info.models) {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = label;
        modelSel.appendChild(opt);
    }
    if (selectedModel && info.models.some(([id]) => id === selectedModel)) {
        modelSel.value = selectedModel;
    }
}

function setKeyStatus(text, kind) {
    keyStatus.textContent = text || "";
    keyStatus.className = `key-status ${kind || ""}`;
}

function setPill(connected, providerLabel) {
    keyPill.textContent = connected ? `${providerLabel} connected` : "Not set";
    keyPill.className = `key-pill ${connected ? "on" : "off"}`;
}

chrome.storage.local.get(["byok_provider", "byok_key", "byok_model"], (r) => {
    const provider = r.byok_provider || "groq";
    providerSel.value = provider;
    renderProvider(provider, r.byok_model);
    if (r.byok_key) {
        // Never re-display the stored secret. Show a length-accurate mask so it
        // is obvious something is saved without putting the key back on screen.
        keyInput.value = "";
        keyInput.placeholder = `Saved — ${"•".repeat(12)}${r.byok_key.slice(-4)}`;
        setPill(true, (PROVIDER_INFO[provider] || {}).label || provider);
    }
});

providerSel.addEventListener("change", () => {
    renderProvider(providerSel.value);
    setKeyStatus("", "");
});

document.getElementById("key-save").addEventListener("click", async () => {
    const provider = providerSel.value;
    const key = keyInput.value.trim();
    const model = modelSel.value;

    if (!key) {
        setKeyStatus("Paste your key first.", "err");
        return;
    }

    const btn = document.getElementById("key-save");
    btn.disabled = true;
    setKeyStatus("Testing your key…", "busy");

    // The service worker owns validation so the key is exercised in the same
    // context that will later use it.
    chrome.runtime.sendMessage({ type: "PM_VALIDATE_KEY", provider, key }, (res) => {
        btn.disabled = false;

        if (chrome.runtime.lastError || !res) {
            setKeyStatus("Could not reach the extension worker. Try reloading the extension.", "err");
            return;
        }
        if (!res.ok) {
            setKeyStatus(res.detail || "That key did not work.", "err");
            return;
        }

        chrome.storage.local.set(
            { byok_provider: provider, byok_key: key, byok_model: model },
            () => {
                const label = (PROVIDER_INFO[provider] || {}).label || provider;
                setPill(true, label);
                setKeyStatus(`${res.detail} You now get your own free allowance.`, "ok");
                keyInput.value = "";
                keyInput.placeholder = `Saved — ${"•".repeat(12)}${key.slice(-4)}`;
            }
        );
    });
});

document.getElementById("key-clear").addEventListener("click", () => {
    chrome.storage.local.remove(["byok_provider", "byok_key", "byok_model"], () => {
        keyInput.value = "";
        keyInput.placeholder = "Paste your key here";
        setPill(false);
        setKeyStatus("Key removed from this browser.", "");
    });
});

// Opened from the post-install tab: focus the one field that matters.
if (new URLSearchParams(location.search).get("onboarding")) {
    keyInput.focus();
}

// ── UI Helpers ──
function showProfile(email) {
    loginSection.classList.add("hidden");
    profileSection.classList.remove("hidden");
    userDisplay.innerText = email;

    // Set avatar to first letter of email
    const initial = email.charAt(0).toUpperCase();
    profileAvatar.innerText = initial;
}

function showLogin() {
    profileSection.classList.add("hidden");
    loginSection.classList.remove("hidden");
    statusText.innerText = "";
}
