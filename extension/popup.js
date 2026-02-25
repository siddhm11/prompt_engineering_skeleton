const API_URL = "https://siddhm11-prompt-engine.hf.space";

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

const googleBtn = document.getElementById("google-login-btn");

// 1. Check logged in state on load
chrome.storage.local.get(["user_id", "email"], (result) => {
    if (result.user_id && result.email) {
        showProfile(result.email, result.user_id);
    }
});

// Google Login
googleBtn.addEventListener("click", () => {
    // Open a popup window
    const width = 500;
    const height = 600;
    const left = (screen.width - width) / 2;
    const top = (screen.height - height) / 2;

    // 1. Get URL from backend
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

        // Save to Storage
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

        // Show Step 2
        step1.classList.add("hidden");
        step2.classList.remove("hidden");
        statusText.innerText = "Code sent! Check backend console.";
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

        // Save to Storage (Token!)
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
    chrome.storage.local.remove(["user_id", "email"], () => {
        showLogin();
    });
});

// Helper: Show Profile UI
function showProfile(email, uuid) {
    loginSection.classList.add("hidden");
    profileSection.classList.remove("hidden");
    userDisplay.innerText = email;
    uuidDisplay.innerText = uuid;
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
