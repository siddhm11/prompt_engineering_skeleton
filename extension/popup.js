// popup.js — Minimal: just shows login status
const statusEl = document.getElementById("status-value");

chrome.storage.local.get(["email", "token"], (result) => {
  if (result.email && result.token) {
    statusEl.textContent = `Logged in as ${result.email}`;
    statusEl.classList.add("logged-in");
  } else {
    statusEl.textContent = "Not logged in — use the sidebar on an AI chat page.";
    statusEl.classList.add("logged-out");
  }
});
