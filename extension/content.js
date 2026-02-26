// extension/content.js — Prompt Memory v4 (Persistent Sidebar)
// One-click prompt engineering. Conversation-aware. Mode-aware. Platform-aware.

const API_URL = "https://siddhm11-prompt-engine.hf.space";

console.log("Prompt Memory v4: loaded on", window.location.hostname);

// ══════════════════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════════════════

let sidebarOpen = false;
let currentMode = "deep";   // "quick" | "deep" | "creative"
let lastEnhanceResult = null;
let historyPrompts = [];
let selectedContextIds = new Set();  // IDs of history prompts selected as context
let selectedContextTexts = {};       // { id: text } for quick access
let searchQuery = "";
let isRecording = false;
let isDragging = false;
let dragOffset = { x: 0, y: 0 };

// ══════════════════════════════════════════════════════════════
// AUTH HELPERS
// ══════════════════════════════════════════════════════════════

function getAuth() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["user_id", "token", "email"], (result) => {
      resolve(result.token ? result : null);
    });
  });
}

function isTokenExpired(token) {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.exp * 1000 < Date.now();
  } catch {
    return true;
  }
}

function saveAuth(user_id, email, token) {
  return new Promise((resolve) => {
    chrome.storage.local.set({ user_id, email, token }, resolve);
  });
}

function clearAuth() {
  return new Promise((resolve) => {
    chrome.storage.local.remove(["user_id", "email", "token"], resolve);
  });
}

async function authedFetch(url, options = {}) {
  const auth = await getAuth();
  if (!auth) return null;

  if (isTokenExpired(auth.token)) {
    showToast("Session expired — please re-login.", "error");
    return null;
  }

  options.headers = {
    ...options.headers,
    "Content-Type": "application/json",
    Authorization: `Bearer ${auth.token}`,
  };
  try {
    const res = await fetch(url, options);
    if (res.status === 401) {
      showToast("Session expired — please re-login.", "error");
      return null;
    }
    return res;
  } catch (err) {
    console.error("Prompt Memory fetch error:", err);
    return null;
  }
}

// ══════════════════════════════════════════════════════════════
// API
// ══════════════════════════════════════════════════════════════

async function fetchHistory(query = "") {
  const q = query ? `?q=${encodeURIComponent(query)}&limit=30` : "?limit=30";
  const res = await authedFetch(`${API_URL}/prompts/history${q}`);
  if (res && res.ok) {
    const data = await res.json();
    historyPrompts = data.prompts || [];
  }
  return historyPrompts;
}

async function enhancePrompt(prompt, selectedPromptIds, skipSimilarity = true) {
  const conversation = scrapeConversation();
  const body = {
    prompt,
    platform: window.location.hostname,
    mode: currentMode,
    conversation_context: conversation,
    skip_similarity: skipSimilarity,
  };
  if (selectedPromptIds && selectedPromptIds.length > 0) {
    body.selected_prompt_ids = selectedPromptIds;
  }
  const res = await authedFetch(`${API_URL}/enhance`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (res && res.ok) return res.json();
  return null;
}

async function savePromptExplicit(prompt) {
  const res = await authedFetch(`${API_URL}/prompts/save`, {
    method: "POST",
    body: JSON.stringify({ prompt, platform: window.location.hostname }),
  });
  return res && res.ok;
}

async function sendFeedback(logId, rating, original, enhanced) {
  authedFetch(`${API_URL}/enhance/feedback`, {
    method: "POST",
    body: JSON.stringify({ log_id: logId, rating, original, enhanced }),
  });
}

// ══════════════════════════════════════════════════════════════
// CONVERSATION SCRAPING
// ══════════════════════════════════════════════════════════════

function scrapeConversation() {
  const messages = [];
  const hostname = window.location.hostname;

  try {
    if (hostname === "chatgpt.com") {
      document.querySelectorAll("[data-message-author-role]").forEach((el) => {
        const role = el.getAttribute("data-message-author-role");
        const text = el.innerText?.trim();
        if (text && text.length > 2) {
          messages.push(`[${role}]: ${text.substring(0, 500)}`);
        }
      });
    } else if (hostname === "claude.ai") {
      document.querySelectorAll("[class*='Message'], [data-testid*='message']").forEach((el) => {
        const text = el.innerText?.trim();
        if (text && text.length > 2) {
          const isUser = el.className?.includes("human") || el.getAttribute("data-testid")?.includes("human");
          messages.push(`[${isUser ? "user" : "assistant"}]: ${text.substring(0, 500)}`);
        }
      });
    } else if (hostname === "gemini.google.com") {
      document.querySelectorAll("message-content, .model-response-text, .query-text").forEach((el) => {
        const text = el.innerText?.trim();
        if (text && text.length > 2) {
          messages.push(`[message]: ${text.substring(0, 500)}`);
        }
      });
    } else if (hostname === "grok.com" || hostname === "x.com") {
      document.querySelectorAll("[class*='message'], [class*='Message'], [data-testid*='message'], [class*='response'], [class*='query']").forEach((el) => {
        const text = el.innerText?.trim();
        if (text && text.length > 2) {
          messages.push(`[message]: ${text.substring(0, 500)}`);
        }
      });
    } else {
      document.querySelectorAll("[class*='message'], [class*='Message'], [role='presentation']").forEach((el) => {
        const text = el.innerText?.trim();
        if (text && text.length > 5 && text.length < 2000) {
          messages.push(text.substring(0, 500));
        }
      });
    }
  } catch (e) {
    console.log("Prompt Memory: conversation scrape failed", e);
  }

  return messages.slice(-6);
}

// ══════════════════════════════════════════════════════════════
// INPUT DETECTION
// ══════════════════════════════════════════════════════════════

function getCurrentInputText() {
  const selectors = ["#prompt-textarea", "[contenteditable='true']", "textarea"];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.offsetParent !== null) {
      return el.innerText || el.value || "";
    }
  }
  return "";
}

function applyToInput(text) {
  const selectors = ["#prompt-textarea", "[contenteditable='true']", "textarea"];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.offsetParent !== null) {
      if (el.tagName === "TEXTAREA") {
        el.value = text;
        el.dispatchEvent(new Event("input", { bubbles: true }));
      } else {
        el.innerText = text;
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }
      return;
    }
  }
}

// ══════════════════════════════════════════════════════════════
// KEYBOARD SHORTCUT
// ══════════════════════════════════════════════════════════════

function setupKeyboardShortcut() {
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === "E") {
      e.preventDefault();
      handleEnhance(true); // default: prompt only
    }
    if (e.ctrlKey && e.shiftKey && e.key === "V") {
      e.preventDefault();
      toggleVoice();
    }
  });
}

// ══════════════════════════════════════════════════════════════
// UI: FLOATING TRIGGER (draggable)
// ══════════════════════════════════════════════════════════════

function createTrigger() {
  if (document.getElementById("pm-trigger")) return;

  const btn = document.createElement("button");
  btn.id = "pm-trigger";
  btn.className = "pm-trigger";
  btn.innerHTML = "⊕";
  btn.title = "Prompt Memory";

  // Load saved position
  chrome.storage.local.get(["pm_trigger_x", "pm_trigger_y"], (result) => {
    if (result.pm_trigger_x !== undefined) {
      btn.style.right = "auto";
      btn.style.bottom = "auto";
      btn.style.left = result.pm_trigger_x + "px";
      btn.style.top = result.pm_trigger_y + "px";
    }
  });

  // Drag logic
  let startX, startY, startLeft, startTop, hasMoved;

  btn.addEventListener("mousedown", (e) => {
    e.preventDefault();
    isDragging = true;
    hasMoved = false;
    const rect = btn.getBoundingClientRect();
    startX = e.clientX;
    startY = e.clientY;
    startLeft = rect.left;
    startTop = rect.top;
    btn.style.transition = "none";
  });

  document.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) hasMoved = true;
    btn.style.right = "auto";
    btn.style.bottom = "auto";
    btn.style.left = (startLeft + dx) + "px";
    btn.style.top = (startTop + dy) + "px";
  });

  document.addEventListener("mouseup", () => {
    if (!isDragging) return;
    isDragging = false;
    btn.style.transition = "";
    if (hasMoved) {
      // Save position
      const rect = btn.getBoundingClientRect();
      chrome.storage.local.set({ pm_trigger_x: rect.left, pm_trigger_y: rect.top });
    } else {
      // Click — toggle sidebar
      toggleSidebar();
    }
  });

  document.body.appendChild(btn);
}

// ══════════════════════════════════════════════════════════════
// UI: SIDEBAR
// ══════════════════════════════════════════════════════════════

function createSidebar() {
  if (document.getElementById("pm-sidebar")) return;

  const sidebar = document.createElement("div");
  sidebar.id = "pm-sidebar";
  sidebar.className = "pm-sidebar";

  sidebar.innerHTML = `
    <div class="pm-sidebar-header">
      <span class="pm-sidebar-title">⊕ Prompt Memory</span>
      <button class="pm-sidebar-minimize" id="pm-minimize" title="Minimize">−</button>
    </div>
    <div class="pm-sidebar-body" id="pm-sidebar-body"></div>
  `;

  document.body.appendChild(sidebar);

  document.getElementById("pm-minimize").addEventListener("click", () => toggleSidebar(false));
}

function toggleSidebar(force) {
  const sidebar = document.getElementById("pm-sidebar");
  if (!sidebar) return;
  sidebarOpen = force !== undefined ? force : !sidebarOpen;
  sidebar.classList.toggle("pm-sidebar-open", sidebarOpen);

  if (sidebarOpen) {
    renderSidebarContent();
  }
}

async function renderSidebarContent() {
  const body = document.getElementById("pm-sidebar-body");
  if (!body) return;

  const auth = await getAuth();
  if (!auth || isTokenExpired(auth.token)) {
    renderLoginView(body);
  } else {
    renderMainView(body, auth);
  }
}

// ══════════════════════════════════════════════════════════════
// VIEW: LOGIN
// ══════════════════════════════════════════════════════════════

function renderLoginView(container) {
  container.innerHTML = `
    <div class="pm-login-section">
      <div class="pm-login-title">Sign In</div>
      <p class="pm-login-desc">Log in to enhance your prompts with AI.</p>

      <div id="pm-login-step1">
        <input type="email" class="pm-input" id="pm-login-email" placeholder="you@example.com" />
        <button class="pm-btn pm-btn-primary pm-full-width" id="pm-send-otp">Send Code</button>
        <div class="pm-divider"><span>or</span></div>
        <button class="pm-btn pm-btn-google pm-full-width" id="pm-google-login">
          <svg width="16" height="16" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
          Sign in with Google
        </button>
      </div>

      <div id="pm-login-step2" class="pm-hidden">
        <p class="pm-login-desc">Enter the 6-digit code from your email.</p>
        <input type="text" class="pm-input" id="pm-login-otp" placeholder="123456" maxlength="6" />
        <button class="pm-btn pm-btn-primary pm-full-width" id="pm-verify-otp">Verify & Login</button>
        <button class="pm-link-btn" id="pm-back-email">← Back to email</button>
      </div>

      <div class="pm-login-status" id="pm-login-status"></div>
    </div>
  `;

  // Send OTP
  document.getElementById("pm-send-otp").addEventListener("click", async () => {
    const email = document.getElementById("pm-login-email").value.trim();
    if (!email) {
      setLoginStatus("Please enter an email.", "error");
      return;
    }

    const btn = document.getElementById("pm-send-otp");
    btn.disabled = true;
    btn.textContent = "Sending...";
    setLoginStatus("Sending code...", "info");

    try {
      const res = await fetch(`${API_URL}/auth/request-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) throw new Error("Failed to send code.");

      document.getElementById("pm-login-step1").classList.add("pm-hidden");
      document.getElementById("pm-login-step2").classList.remove("pm-hidden");
      setLoginStatus("Code sent! Check your email.", "success");
      document.getElementById("pm-login-otp").focus();
    } catch (err) {
      setLoginStatus("Error: " + err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Send Code";
    }
  });

  // Verify OTP
  document.getElementById("pm-verify-otp").addEventListener("click", async () => {
    const email = document.getElementById("pm-login-email").value.trim();
    const code = document.getElementById("pm-login-otp").value.trim();
    if (code.length < 6) {
      setLoginStatus("Enter full 6-digit code.", "error");
      return;
    }

    const btn = document.getElementById("pm-verify-otp");
    btn.disabled = true;
    btn.textContent = "Verifying...";

    try {
      const res = await fetch(`${API_URL}/auth/verify-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code }),
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Verification failed");
      }
      const data = await res.json();
      await saveAuth(data.user_id, data.email, data.token);
      renderSidebarContent();
    } catch (err) {
      setLoginStatus("❌ " + err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Verify & Login";
    }
  });

  // Back button
  document.getElementById("pm-back-email").addEventListener("click", () => {
    document.getElementById("pm-login-step2").classList.add("pm-hidden");
    document.getElementById("pm-login-step1").classList.remove("pm-hidden");
    setLoginStatus("", "info");
  });

  // Google OAuth
  document.getElementById("pm-google-login").addEventListener("click", async () => {
    try {
      const res = await fetch(`${API_URL}/auth/google/login`);
      const data = await res.json();
      const width = 500, height = 600;
      const left = (screen.width - width) / 2;
      const top = (screen.height - height) / 2;
      window.open(data.url, "GoogleLogin", `width=${width},height=${height},top=${top},left=${left}`);
    } catch (err) {
      setLoginStatus("Google login error: " + err.message, "error");
    }
  });

  // Listen for Google OAuth callback
  window.addEventListener("message", async function googleHandler(event) {
    if (event.data && event.data.type === "GOOGLE_AUTH_SUCCESS") {
      const { token, email, user_id } = event.data;
      await saveAuth(user_id, email, token);
      window.removeEventListener("message", googleHandler);
      renderSidebarContent();
    }
  });
}

function setLoginStatus(msg, type) {
  const el = document.getElementById("pm-login-status");
  if (!el) return;
  el.textContent = msg;
  el.className = `pm-login-status${type === "success" ? " pm-status-success" : type === "error" ? " pm-status-error" : ""}`;
}

// ══════════════════════════════════════════════════════════════
// VIEW: MAIN (logged in)
// ══════════════════════════════════════════════════════════════

async function renderMainView(container, auth) {
  container.innerHTML = `
    <div class="pm-main-section">
      <!-- User Info -->
      <div class="pm-user-bar">
        <span class="pm-user-email">${escHtml(auth.email)}</span>
        <button class="pm-link-btn pm-logout-btn" id="pm-logout">Logout</button>
      </div>

      <!-- Prompt Input -->
      <div class="pm-section">
        <label class="pm-label">Your Prompt</label>
        <textarea class="pm-textarea" id="pm-prompt-input" placeholder="Type your prompt here...">${escHtml(getCurrentInputText())}</textarea>
      </div>

      <!-- Mode Selector -->
      <div class="pm-mode-row">
        <button class="pm-mode-btn${currentMode === 'quick' ? ' pm-mode-active' : ''}" data-mode="quick" title="Short & sharp">⚡ Quick</button>
        <button class="pm-mode-btn${currentMode === 'deep' ? ' pm-mode-active' : ''}" data-mode="deep" title="Full structured enhancement">🎯 Deep</button>
        <button class="pm-mode-btn${currentMode === 'creative' ? ' pm-mode-active' : ''}" data-mode="creative" title="Open-ended, exploratory">✨ Creative</button>
      </div>

      <!-- Action Buttons -->
      <div class="pm-action-buttons">
        <button class="pm-btn pm-btn-primary pm-full-width" id="pm-enhance-only" title="Enhance just your prompt + selected context">Enhance Prompt</button>
        <button class="pm-btn pm-btn-secondary pm-full-width" id="pm-enhance-context" title="Enhance with auto-matched similar prompts from your history">Enhance + Auto-Context</button>
      </div>

      <!-- Voice -->
      <div class="pm-voice-row">
        <button class="pm-btn pm-btn-voice" id="pm-voice-btn" title="Voice to Prompt (Ctrl+Shift+V)">🎤 Voice to Prompt</button>
      </div>

      <!-- Context Count -->
      <div class="pm-context-hint" id="pm-context-hint"></div>

      <!-- History Section -->
      <div class="pm-section">
        <label class="pm-label">Your History</label>
        <input type="text" class="pm-input pm-search-input" id="pm-history-search" placeholder="Search your past prompts..." value="${escHtml(searchQuery)}" />
        <div class="pm-history-list" id="pm-history-list">
          <div class="pm-loading">Loading history...</div>
        </div>
      </div>
    </div>
  `;

  // Logout
  document.getElementById("pm-logout").addEventListener("click", async () => {
    await clearAuth();
    selectedContextIds.clear();
    selectedContextTexts = {};
    renderSidebarContent();
  });

  // Mode buttons
  container.querySelectorAll(".pm-mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentMode = btn.dataset.mode;
      container.querySelectorAll(".pm-mode-btn").forEach((b) => b.classList.remove("pm-mode-active"));
      btn.classList.add("pm-mode-active");
    });
  });

  // Enhance buttons
  document.getElementById("pm-enhance-only").addEventListener("click", () => handleEnhance(true));
  document.getElementById("pm-enhance-context").addEventListener("click", () => handleEnhance(false));

  // Voice
  document.getElementById("pm-voice-btn").addEventListener("click", toggleVoice);

  // History search
  const searchInput = document.getElementById("pm-history-search");
  let searchTimeout;
  searchInput.addEventListener("input", (e) => {
    searchQuery = e.target.value;
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => loadAndRenderHistory(), 300);
  });

  // Load history
  await loadAndRenderHistory();
  updateContextHint();
}

async function loadAndRenderHistory() {
  const listEl = document.getElementById("pm-history-list");
  if (!listEl) return;

  listEl.innerHTML = `<div class="pm-loading">Loading...</div>`;

  await fetchHistory(searchQuery);

  if (historyPrompts.length === 0) {
    listEl.innerHTML = `<div class="pm-history-empty">${searchQuery ? `No results for "${escHtml(searchQuery)}"` : "No saved prompts yet."}</div>`;
    return;
  }

  listEl.innerHTML = "";

  historyPrompts.forEach((p) => {
    const card = document.createElement("div");
    const isSelected = selectedContextIds.has(p.id);
    card.className = `pm-history-card${isSelected ? " pm-history-selected" : ""}`;

    const preview = truncate(p.original, 80);
    const timeStr = p.timestamp ? new Date(p.timestamp).toLocaleDateString() : "";

    card.innerHTML = `
      <div class="pm-history-card-main">
        <div class="pm-history-text">${escHtml(preview)}</div>
        <div class="pm-history-meta">${escHtml(timeStr)}</div>
      </div>
      <div class="pm-history-tooltip">${escHtml(p.original)}</div>
      <div class="pm-history-select-badge">${isSelected ? "✓ Context" : "+ Add"}</div>
    `;

    // Click to toggle as context
    card.addEventListener("click", () => {
      if (selectedContextIds.has(p.id)) {
        selectedContextIds.delete(p.id);
        delete selectedContextTexts[p.id];
        card.classList.remove("pm-history-selected");
        card.querySelector(".pm-history-select-badge").textContent = "+ Add";
      } else {
        selectedContextIds.add(p.id);
        selectedContextTexts[p.id] = p.original;
        card.classList.add("pm-history-selected");
        card.querySelector(".pm-history-select-badge").textContent = "✓ Context";
      }
      updateContextHint();
    });

    listEl.appendChild(card);
  });
}

function updateContextHint() {
  const hint = document.getElementById("pm-context-hint");
  if (!hint) return;
  const count = selectedContextIds.size;
  if (count > 0) {
    hint.textContent = `${count} prompt${count > 1 ? "s" : ""} selected as context`;
    hint.classList.add("pm-context-active");
  } else {
    hint.textContent = "Click on a history prompt to add it as context";
    hint.classList.remove("pm-context-active");
  }
}

// ══════════════════════════════════════════════════════════════
// ENHANCE HANDLERS
// ══════════════════════════════════════════════════════════════

async function handleEnhance(skipSimilarity = true) {
  const auth = await getAuth();
  if (!auth) {
    showToast("Please log in first.", "error");
    return;
  }
  if (isTokenExpired(auth.token)) {
    showToast("Session expired — please re-login.", "error");
    return;
  }

  // Get prompt from sidebar textarea, fallback to chat input
  const promptInput = document.getElementById("pm-prompt-input");
  let inputText = promptInput ? promptInput.value.trim() : "";
  if (!inputText) inputText = getCurrentInputText();

  if (!inputText || inputText.trim().length < 3) {
    showToast("Type a prompt first.", "error");
    return;
  }

  // Disable buttons
  const btn1 = document.getElementById("pm-enhance-only");
  const btn2 = document.getElementById("pm-enhance-context");
  if (btn1) { btn1.disabled = true; btn1.textContent = "Enhancing..."; }
  if (btn2) { btn2.disabled = true; }

  showToast(`Enhancing in ${currentMode} mode...`, "info");

  // Build selected prompt IDs (from history context)
  const selectedIds = Array.from(selectedContextIds);

  const result = await enhancePrompt(inputText, selectedIds, skipSimilarity);

  // Re-enable buttons
  if (btn1) { btn1.disabled = false; btn1.textContent = "Enhance Prompt"; }
  if (btn2) { btn2.disabled = false; }

  if (!result) {
    showToast("Enhancement failed. Check connection.", "error");
    return;
  }

  lastEnhanceResult = result;
  showDiffModal(result);
}

// ══════════════════════════════════════════════════════════════
// DIFF PREVIEW MODAL
// ══════════════════════════════════════════════════════════════

function showDiffModal(result) {
  const overlay = getOrCreateModalOverlay();
  const modal = overlay.querySelector(".pm-modal");

  const contextLine = result.context_used
    ? `${result.context_used.selected || 0} selected · ${result.context_used.auto_matched || 0} auto-matched · ${result.context_used.conversation_messages || 0} conversation msgs`
    : "";

  modal.innerHTML = `
    <div class="pm-modal-header">
      <span class="pm-modal-title">Enhanced Prompt</span>
      <button class="pm-header-close pm-modal-close-btn">×</button>
    </div>
    <div class="pm-modal-body pm-diff-body">
      <div class="pm-diff-section">
        <div class="pm-diff-label">Original</div>
        <div class="pm-diff-original">${escHtml(result.original)}</div>
      </div>
      <div class="pm-diff-arrow">↓ enhanced in ${result.mode || currentMode} mode</div>
      <div class="pm-diff-section">
        <div class="pm-diff-label pm-diff-label-new">Enhanced</div>
        <div class="pm-diff-enhanced">${escHtml(result.enhanced)}</div>
      </div>
      ${contextLine ? `<div class="pm-diff-meta">${escHtml(contextLine)} · ${result.latency}s</div>` : ""}
    </div>
    <div class="pm-modal-footer">
      <button class="pm-btn pm-btn-secondary pm-modal-close-btn">Discard</button>
      <button class="pm-btn pm-btn-save" id="pm-save-original">💾 Save My Prompt</button>
      <button class="pm-btn pm-btn-primary" id="pm-use-enhanced">Use This Prompt</button>
    </div>
  `;

  // Close handlers
  overlay.querySelectorAll(".pm-modal-close-btn").forEach((b) =>
    b.addEventListener("click", closeModal)
  );

  // Use enhanced prompt
  document.getElementById("pm-use-enhanced").addEventListener("click", () => {
    applyToInput(result.enhanced);
    closeModal();
    showFeedbackToast(result);
  });

  // Save original prompt explicitly
  document.getElementById("pm-save-original").addEventListener("click", async () => {
    const btn = document.getElementById("pm-save-original");
    btn.disabled = true;
    btn.textContent = "Saving...";
    const ok = await savePromptExplicit(result.original);
    if (ok) {
      showToast("Prompt saved to your history!", "success");
      loadAndRenderHistory(); // refresh
    } else {
      showToast("Failed to save.", "error");
    }
    btn.disabled = false;
    btn.textContent = "💾 Save My Prompt";
  });

  overlay.classList.add("pm-visible");
}

// ══════════════════════════════════════════════════════════════
// FEEDBACK TOAST
// ══════════════════════════════════════════════════════════════

function showFeedbackToast(result) {
  const existing = document.getElementById("pm-feedback-toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.id = "pm-feedback-toast";
  toast.className = "pm-feedback-toast";
  toast.innerHTML = `
    <span>How was this enhancement?</span>
    <button class="pm-fb-btn pm-fb-up" title="Good">👍</button>
    <button class="pm-fb-btn pm-fb-down" title="Bad">👎</button>
  `;

  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("pm-toast-visible"));

  const autoDismiss = setTimeout(() => {
    toast.classList.remove("pm-toast-visible");
    setTimeout(() => toast.remove(), 300);
  }, 8000);

  toast.querySelector(".pm-fb-up").addEventListener("click", () => {
    clearTimeout(autoDismiss);
    sendFeedback(result.log_id, "up", result.original, result.enhanced);
    toast.innerHTML = `<span>Thanks! 🎯</span>`;
    setTimeout(() => { toast.classList.remove("pm-toast-visible"); setTimeout(() => toast.remove(), 300); }, 1500);
  });

  toast.querySelector(".pm-fb-down").addEventListener("click", () => {
    clearTimeout(autoDismiss);
    sendFeedback(result.log_id, "down", result.original, result.enhanced);
    toast.innerHTML = `<span>Got it — we'll improve. 🙏</span>`;
    setTimeout(() => { toast.classList.remove("pm-toast-visible"); setTimeout(() => toast.remove(), 300); }, 1500);
  });
}

function showToast(message, type = "info") {
  const existing = document.getElementById("pm-toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.id = "pm-toast";
  toast.className = `pm-toast pm-toast-${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add("pm-toast-visible"));

  setTimeout(() => {
    toast.classList.remove("pm-toast-visible");
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ══════════════════════════════════════════════════════════════
// MODAL HELPERS
// ══════════════════════════════════════════════════════════════

function getOrCreateModalOverlay() {
  let overlay = document.getElementById("pm-modal-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "pm-modal-overlay";
    overlay.className = "pm-modal-overlay";
    overlay.innerHTML = `<div class="pm-modal"></div>`;
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeModal();
    });
    document.body.appendChild(overlay);
  }
  return overlay;
}

function closeModal() {
  const overlay = document.getElementById("pm-modal-overlay");
  if (overlay) overlay.classList.remove("pm-visible");
}

// ══════════════════════════════════════════════════════════════
// VOICE-TO-PROMPT ENGINE
// ══════════════════════════════════════════════════════════════

let mediaRecorder = null;
let audioChunks = [];
let recordingStartTime = 0;
let recordingTimer = null;

function toggleVoice() {
  if (isRecording) {
    stopVoice();
  } else {
    startVoice();
  }
}

async function startVoice() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    showToast("Microphone access denied.", "error");
    return;
  }

  audioChunks = [];
  mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });

  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) audioChunks.push(e.data);
  };

  mediaRecorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    clearInterval(recordingTimer);

    if (audioChunks.length === 0) {
      cleanupVoice();
      showToast("No audio recorded.", "error");
      return;
    }

    const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
    audioChunks = [];
    updateVoiceOverlayState("processing");
    await sendAudioToBackend(audioBlob);
  };

  mediaRecorder.start(250);
  isRecording = true;
  recordingStartTime = Date.now();
  updateVoiceUI(true);
  showVoiceOverlay();

  recordingTimer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const mins = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const secs = String(elapsed % 60).padStart(2, "0");
    const timerEl = document.getElementById("pm-voice-timer");
    if (timerEl) timerEl.textContent = `${mins}:${secs}`;
  }, 1000);

  showToast("🎤 Recording... speak your prompt", "info");
}

function stopVoice() {
  if (!mediaRecorder || mediaRecorder.state === "inactive") return;
  isRecording = false;
  updateVoiceUI(false);
  try { mediaRecorder.stop(); } catch (e) { }
}

async function sendAudioToBackend(audioBlob) {
  const auth = await getAuth();
  if (!auth || isTokenExpired(auth.token)) {
    hideVoiceOverlay();
    showToast("Please log in first.", "error");
    return;
  }

  const conversationCtx = scrapeConversation();

  const formData = new FormData();
  formData.append("audio", audioBlob, "recording.webm");
  formData.append("mode", currentMode);
  formData.append("platform", window.location.hostname);
  formData.append("conversation_context", JSON.stringify(conversationCtx));
  formData.append("selected_prompt_ids", JSON.stringify(Array.from(selectedContextIds)));

  try {
    const resp = await fetch(`${API_URL}/voice-enhance`, {
      method: "POST",
      headers: { Authorization: `Bearer ${auth.token}` },
      body: formData,
    });
    const data = await resp.json();

    hideVoiceOverlay();

    if (data.error) {
      showToast(data.error, "error");
      return;
    }

    lastEnhanceResult = {
      original: data.transcription || data.original,
      enhanced: data.enhanced,
      mode: data.mode,
      latency: data.total_time,
      context_used: data.context_used,
      log_id: data.log_id,
    };

    showToast(`Transcribed in ${data.transcription_time}s · Enhanced in ${data.total_time}s`, "success");
    showDiffModal(lastEnhanceResult);
  } catch (e) {
    hideVoiceOverlay();
    console.error("Voice enhance error:", e);
    showToast("Voice enhance failed. Check connection.", "error");
  }
}

function cleanupVoice() {
  isRecording = false;
  mediaRecorder = null;
  audioChunks = [];
  clearInterval(recordingTimer);
  updateVoiceUI(false);
  hideVoiceOverlay();
}

function showVoiceOverlay() {
  let overlay = document.getElementById("pm-voice-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "pm-voice-overlay";
    overlay.className = "pm-voice-overlay";
    document.body.appendChild(overlay);
  }

  overlay.innerHTML = `
    <div class="pm-voice-card">
      <div class="pm-voice-indicator">
        <div class="pm-voice-bars">
          <span class="pm-bar"></span><span class="pm-bar"></span><span class="pm-bar"></span>
          <span class="pm-bar"></span><span class="pm-bar"></span>
        </div>
        <span class="pm-voice-label">Recording</span>
      </div>
      <div class="pm-voice-timer" id="pm-voice-timer">00:00</div>
      <div class="pm-voice-hint">Speak naturally — Whisper AI will transcribe</div>
      <button class="pm-btn pm-btn-primary pm-voice-stop" id="pm-voice-stop">Stop & Enhance</button>
    </div>
  `;

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) stopVoice();
  });
  document.getElementById("pm-voice-stop").addEventListener("click", stopVoice);

  requestAnimationFrame(() => overlay.classList.add("pm-visible"));
}

function updateVoiceOverlayState(state) {
  const card = document.querySelector(".pm-voice-card");
  if (!card) return;

  if (state === "processing") {
    card.innerHTML = `
      <div class="pm-voice-indicator">
        <div class="pm-voice-spinner"></div>
        <span class="pm-voice-label">Transcribing & enhancing...</span>
      </div>
      <div class="pm-voice-hint">Whisper AI is processing your audio</div>
    `;
  }
}

function hideVoiceOverlay() {
  const overlay = document.getElementById("pm-voice-overlay");
  if (overlay) {
    overlay.classList.remove("pm-visible");
    setTimeout(() => overlay.remove(), 300);
  }
}

function updateVoiceUI(recording) {
  const btn = document.getElementById("pm-voice-btn");
  if (btn) {
    btn.classList.toggle("pm-recording", recording);
    btn.innerHTML = recording ? "⏹ Stop Recording" : "🎤 Voice to Prompt";
    btn.title = recording ? "Stop recording" : "Voice to Prompt (Ctrl+Shift+V)";
  }
}

// ══════════════════════════════════════════════════════════════
// HELPERS
// ══════════════════════════════════════════════════════════════

function truncate(str, len) {
  if (!str) return "";
  return str.length > len ? str.substring(0, len) + "..." : str;
}

function escHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ══════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════

async function init() {
  createTrigger();
  createSidebar();
  setupKeyboardShortcut();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 500));
} else {
  setTimeout(init, 500);
}