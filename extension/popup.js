// Default API URL — overridden by chrome.storage.local['api_url']
const DEFAULT_API_URL = "http://localhost:8000";
let API_URL = DEFAULT_API_URL;

const step1 = document.getElementById("step-1");
const step2 = document.getElementById("step-2");
const emailInput = document.getElementById("email");
const otpInput = document.getElementById("otp-code");

const sendOtpBtn = document.getElementById("send-otp-btn");
const verifyOtpBtn = document.getElementById("verify-otp-btn");
const backBtn = document.getElementById("back-to-email");
const logoutBtn = document.getElementById("logout-btn");

const statusText = document.getElementById("status");
const loginSection = document.getElementById("login-section");
const profileSection = document.getElementById("profile-section");
const userDisplay = document.getElementById("user-display");
const uuidDisplay = document.getElementById("uuid-display");
const serverDisplay = document.getElementById("server-display");
const serverStatus = document.getElementById("server-status");

const googleBtn = document.getElementById("google-login-btn");

// Load API URL from storage first, then check login state
chrome.storage.local.get(["user_id", "email", "token", "api_url"], async (result) => {
    if (result.api_url) API_URL = result.api_url;

    if (result.user_id && result.email) {
        showProfile(result.email, result.user_id);

        // Auto-refresh token if expiring within 2 days
        if (result.token && isTokenExpiringSoon(result.token, 2)) {
            await tryRefreshToken(result.token);
        }
    }
});

// Token refresh helper
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
            console.log("Popup: token auto-refreshed");
            return true;
        }
    } catch (e) {
        console.log("Popup: token refresh failed", e);
    }
    return false;
}

// Server health check
async function checkServerHealth() {
    if (!serverStatus) return;
    try {
        const res = await fetch(`${API_URL}/`, { method: "GET" });
        if (res.ok) {
            serverStatus.textContent = "● Connected";
            serverStatus.className = "server-status connected";
        } else {
            serverStatus.textContent = "● Error";
            serverStatus.className = "server-status error";
        }
    } catch {
        serverStatus.textContent = "● Offline";
        serverStatus.className = "server-status offline";
    }
}

// Google Login
googleBtn.addEventListener("click", () => {
    const width = 500;
    const height = 600;
    const left = (screen.width - width) / 2;
    const top = (screen.height - height) / 2;

    fetch(`${API_URL}/auth/google/login`)
        .then(res => res.json())
        .then(data => {
            window.open(data.url, "GoogleLogin", `width=${width},height=${height},top=${top},left=${left}`);
        })
        .catch(err => statusText.innerText = "Google Error: " + err.message);
});

// Listen for message from the Google Popup
window.addEventListener("message", (event) => {
    if (event.data.type === "GOOGLE_AUTH_SUCCESS") {
        const { token, email, user_id } = event.data;

        chrome.storage.local.set({ user_id, email, token }, () => {
            statusText.innerText = "";
            showProfile(email, user_id);
        });
    }
});

// 2. Step 1: Send OTP
sendOtpBtn.addEventListener("click", async () => {
    const email = emailInput.value.trim();
    if (!email) {
        statusText.innerText = "Please enter an email.";
        return;
    }

    statusText.innerText = "Sending code...";
    sendOtpBtn.disabled = true;

    try {
        const res = await fetch(`${API_URL}/auth/request-otp`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email })
        });

        if (!res.ok) throw new Error("Failed to send code.");

        step1.classList.add("hidden");
        step2.classList.remove("hidden");
        statusText.innerText = "Code sent! Check your email.";
        otpInput.focus();

    } catch (err) {
        statusText.innerText = "Error: " + err.message;
    } finally {
        sendOtpBtn.disabled = false;
    }
});

// 3. Step 2: Verify OTP
verifyOtpBtn.addEventListener("click", async () => {
    const email = emailInput.value.trim();
    const code = otpInput.value.trim();

    if (code.length < 6) {
        statusText.innerText = "Enter full 6-digit code.";
        return;
    }

    statusText.innerText = "Verifying...";
    verifyOtpBtn.disabled = true;

    try {
        const res = await fetch(`${API_URL}/auth/verify-otp`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, code: code })
        });

        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail || "Verification failed");
        }

        const data = await res.json();

        chrome.storage.local.set({
            user_id: data.user_id,
            email: data.email,
            token: data.token
        }, () => {
            statusText.innerText = "";
            showProfile(data.email, data.user_id);
        });

    } catch (err) {
        statusText.innerText = "❌ " + err.message;
    } finally {
        verifyOtpBtn.disabled = false;
    }
});

// Back Button
backBtn.addEventListener("click", () => {
    step2.classList.add("hidden");
    step1.classList.remove("hidden");
    statusText.innerText = "";
});

// 4. Logout Logic
logoutBtn.addEventListener("click", () => {
    chrome.storage.local.remove(["user_id", "email", "token"], () => {
        showLogin();
    });
});

// Helper: Show Profile UI
function showProfile(email, uuid) {
    loginSection.classList.add("hidden");
    profileSection.classList.remove("hidden");
    userDisplay.innerText = email;
    uuidDisplay.innerText = uuid;

    // Show server info
    const urlLabel = API_URL.replace(/^https?:\/\//, "").replace(/\/$/, "");
    if (serverDisplay) serverDisplay.innerText = urlLabel;
    checkServerHealth();
}

// Helper: Show Login UI
function showLogin() {
    profileSection.classList.add("hidden");
    loginSection.classList.remove("hidden");
    step1.classList.remove("hidden");
    step2.classList.add("hidden");

    emailInput.value = "";
    otpInput.value = "";
    statusText.innerText = "";
}

