// extension/content.js — Prompt Memory v3 (Revolutionary)
// One-click prompt engineering. Conversation-aware. Mode-aware. Platform-aware.

const API_URL = "http://localhost:8000";

console.log("Prompt Memory v3: loaded on", window.location.hostname);

// ══════════════════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════════════════

let savedPrompts = [];
let selectedIds = new Set();
let panelOpen = false;
let currentTab = "context"; // "context" | "save"
let currentMode = "deep";   // "quick" | "deep" | "creative"
let lastEnhanceResult = null;
let searchQuery = "";
let isRecording = false;
let recognition = null;
let voiceFinalTranscript = "";
let voiceInterimTranscript = "";

// ══════════════════════════════════════════════════════════════
// AUTH HELPERS
// ══════════════════════════════════════════════════════════════

function getAuth() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["user_id", "token"], (result) => {
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

async function authedFetch(url, options = {}) {
  const auth = await getAuth();
  if (!auth) return null;

  // Check token expiry
  if (isTokenExpired(auth.token)) {
    showToast("Session expired — please re-login from the extension popup.", "error");
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
      showToast("Session expired — please re-login from the extension popup.", "error");
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

async function fetchSavedPrompts() {
  const res = await authedFetch(`${API_URL}/saved-prompts`);
  if (res && res.ok) {
    const data = await res.json();
    savedPrompts = data.prompts || [];
  }
  return savedPrompts;
}

async function createSavedPrompt(content, title, tags) {
  const body = { content };
  if (title && title.trim()) body.title = title.trim();
  if (tags && tags.length > 0) body.tags = tags;
  const res = await authedFetch(`${API_URL}/saved-prompts`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return res && res.ok;
}

async function updateSavedPrompt(id, fields) {
  const res = await authedFetch(`${API_URL}/saved-prompts/${id}`, {
    method: "PUT",
    body: JSON.stringify(fields),
  });
  return res && res.ok;
}

async function deleteSavedPrompt(id) {
  const res = await authedFetch(`${API_URL}/saved-prompts/${id}`, {
    method: "DELETE",
  });
  return res && res.ok;
}

async function enhancePrompt(prompt, selectedPromptIds) {
  const conversation = scrapeConversation();
  const body = {
    prompt,
    platform: window.location.hostname,
    mode: currentMode,
    conversation_context: conversation,
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

async function sendFeedback(logId, rating, original, enhanced) {
  authedFetch(`${API_URL}/enhance/feedback`, {
    method: "POST",
    body: JSON.stringify({ log_id: logId, rating, original, enhanced }),
  });
}

async function trackPrompt(prompt) {
  const auth = await getAuth();
  if (!auth || !prompt || prompt.trim().length <= 5) return;
  authedFetch(`${API_URL}/track`, {
    method: "POST",
    body: JSON.stringify({
      user_id: auth.user_id,
      prompt,
      platform: window.location.hostname,
    }),
  });
}

// ══════════════════════════════════════════════════════════════
// CONVERSATION SCRAPING
// Reads the visible chat history from the page DOM
// ══════════════════════════════════════════════════════════════

function scrapeConversation() {
  const messages = [];
  const hostname = window.location.hostname;

  try {
    if (hostname === "chatgpt.com") {
      // ChatGPT: messages in [data-message-author-role]
      document.querySelectorAll("[data-message-author-role]").forEach((el) => {
        const role = el.getAttribute("data-message-author-role");
        const text = el.innerText?.trim();
        if (text && text.length > 2) {
          messages.push(`[${role}]: ${text.substring(0, 500)}`);
        }
      });
    } else if (hostname === "claude.ai") {
      // Claude: user and assistant message containers
      document.querySelectorAll("[class*='Message'], [data-testid*='message']").forEach((el) => {
        const text = el.innerText?.trim();
        if (text && text.length > 2) {
          const isUser = el.className?.includes("human") || el.getAttribute("data-testid")?.includes("human");
          messages.push(`[${isUser ? "user" : "assistant"}]: ${text.substring(0, 500)}`);
        }
      });
    } else if (hostname === "gemini.google.com") {
      // Gemini: message-content containers
      document.querySelectorAll("message-content, .model-response-text, .query-text").forEach((el) => {
        const text = el.innerText?.trim();
        if (text && text.length > 2) {
          messages.push(`[message]: ${text.substring(0, 500)}`);
        }
      });
    } else if (hostname === "grok.com" || hostname === "x.com") {
      // Grok: message containers
      document.querySelectorAll("[class*='message'], [class*='Message'], [data-testid*='message'], [class*='response'], [class*='query']").forEach((el) => {
        const text = el.innerText?.trim();
        if (text && text.length > 2) {
          messages.push(`[message]: ${text.substring(0, 500)}`);
        }
      });
    } else {
      // Generic fallback: try common patterns
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

  // Return last 6 messages (context window)
  return messages.slice(-6);
}

// ══════════════════════════════════════════════════════════════
// UI: TRIGGER BUTTON
// ══════════════════════════════════════════════════════════════

function createTrigger() {
  if (document.getElementById("pm-trigger")) return;
  const btn = document.createElement("button");
  btn.id = "pm-trigger";
  btn.className = "pm-trigger";
  btn.innerHTML = "⊕";
  btn.title = "Prompt Memory (Ctrl+Shift+E to enhance)";
  btn.addEventListener("click", () => togglePanel());
  document.body.appendChild(btn);
}

// ══════════════════════════════════════════════════════════════
// KEYBOARD SHORTCUT: Ctrl+Shift+E = Instant Enhance
// ══════════════════════════════════════════════════════════════

function setupKeyboardShortcut() {
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === "E") {
      e.preventDefault();
      handleEnhance();
    }
    if (e.ctrlKey && e.shiftKey && e.key === "V") {
      e.preventDefault();
      toggleVoice();
    }
  });
}

// ══════════════════════════════════════════════════════════════
// UI: PANEL
// ══════════════════════════════════════════════════════════════

function createPanel() {
  if (document.getElementById("pm-panel")) return;

  const panel = document.createElement("div");
  panel.id = "pm-panel";
  panel.className = "pm-panel";

  panel.innerHTML = `
    <div class="pm-header">
      <span class="pm-header-title">Prompt Memory</span>
      <button class="pm-header-close" id="pm-close">×</button>
    </div>
    <div class="pm-tabs">
      <button class="pm-tab pm-active" data-tab="context">Context</button>
      <button class="pm-tab" data-tab="save">Save</button>
    </div>
    <div class="pm-tab-content" id="pm-tab-body"></div>
    <div class="pm-enhance-section">
      <div class="pm-mode-row">
        <button class="pm-mode-btn" data-mode="quick" title="Short & sharp">⚡ Quick</button>
        <button class="pm-mode-btn pm-mode-active" data-mode="deep" title="Full structured enhancement">🎯 Deep</button>
        <button class="pm-mode-btn" data-mode="creative" title="Open-ended, exploratory">✨ Creative</button>
      </div>
      <div class="pm-enhance-row">
        <button class="pm-enhance-btn" id="pm-enhance-btn">Enhance Current Prompt</button>
        <button class="pm-voice-btn" id="pm-voice-btn" title="Voice to Prompt (Ctrl+Shift+V)">🎤</button>
      </div>
      <div class="pm-enhance-hint" id="pm-enhance-hint">Ctrl+Shift+E to enhance · Ctrl+Shift+V to speak</div>
    </div>
  `;

  document.body.appendChild(panel);

  // Close
  document.getElementById("pm-close").addEventListener("click", () => togglePanel(false));

  // Tabs
  panel.querySelectorAll(".pm-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      currentTab = tab.dataset.tab;
      panel.querySelectorAll(".pm-tab").forEach((t) => t.classList.remove("pm-active"));
      tab.classList.add("pm-active");
      renderTabContent();
    });
  });

  // Mode buttons
  panel.querySelectorAll(".pm-mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentMode = btn.dataset.mode;
      panel.querySelectorAll(".pm-mode-btn").forEach((b) => b.classList.remove("pm-mode-active"));
      btn.classList.add("pm-mode-active");
    });
  });

  // Enhance
  document.getElementById("pm-enhance-btn").addEventListener("click", handleEnhance);

  // Voice
  document.getElementById("pm-voice-btn").addEventListener("click", toggleVoice);
}

function togglePanel(force) {
  const panel = document.getElementById("pm-panel");
  if (!panel) return;
  panelOpen = force !== undefined ? force : !panelOpen;
  panel.classList.toggle("pm-open", panelOpen);
  if (panelOpen) {
    fetchSavedPrompts().then(() => renderTabContent());
  }
}

// ══════════════════════════════════════════════════════════════
// RENDER: CONTEXT TAB (with search + checkboxes)
// ══════════════════════════════════════════════════════════════

function renderTabContent() {
  const body = document.getElementById("pm-tab-body");
  if (!body) return;

  if (currentTab === "context") {
    renderContextTab(body);
  } else {
    renderSaveTab(body);
  }
}

function renderContextTab(container) {
  let html = `<div class="pm-search-row">
    <input type="text" class="pm-search-input" id="pm-search" placeholder="Search saved prompts..." value="${escHtml(searchQuery)}" />
  </div>`;

  // Filter prompts
  const filtered = savedPrompts.filter((p) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    const matchTitle = (p.title || "").toLowerCase().includes(q);
    const matchContent = (p.content || "").toLowerCase().includes(q);
    const matchTags = (p.tags || []).some((t) => t.toLowerCase().includes(q));
    return matchTitle || matchContent || matchTags;
  });

  if (savedPrompts.length === 0) {
    html += `<div class="pm-prompts-empty">No saved prompts yet.<br>Switch to the Save tab to add one.</div>`;
    container.innerHTML = html;
    _bindSearch(container);
    return;
  }

  if (filtered.length === 0) {
    html += `<div class="pm-prompts-empty">No prompts match "${escHtml(searchQuery)}"</div>`;
    container.innerHTML = html;
    _bindSearch(container);
    return;
  }

  container.innerHTML = html;
  _bindSearch(container);

  filtered.forEach((p) => {
    const item = document.createElement("div");
    item.className = `pm-prompt-item${selectedIds.has(p.id) ? " pm-checked" : ""}`;

    const displayTitle = p.title || truncate(p.content, 40);
    const preview = truncate(p.content, 80);
    const tagsHtml =
      p.tags && p.tags.length > 0
        ? `<div class="pm-tags">${p.tags.map((t) => `<span class="pm-tag">${escHtml(t)}</span>`).join("")}</div>`
        : "";

    item.innerHTML = `
      <input type="checkbox" class="pm-checkbox" ${selectedIds.has(p.id) ? "checked" : ""}>
      <div class="pm-prompt-body">
        <div class="pm-prompt-title">${escHtml(displayTitle)}</div>
        <div class="pm-prompt-preview">${escHtml(preview)}</div>
        ${tagsHtml}
      </div>
      <div class="pm-prompt-actions">
        <button class="pm-action-btn pm-view" title="View">◎</button>
        <button class="pm-action-btn pm-edit" title="Edit">✎</button>
        <button class="pm-action-btn pm-delete" title="Delete">✕</button>
      </div>
    `;

    // Checkbox toggle
    const checkbox = item.querySelector(".pm-checkbox");
    item.addEventListener("click", (e) => {
      if (e.target.closest(".pm-action-btn")) return;
      if (e.target !== checkbox) checkbox.checked = !checkbox.checked;
      if (checkbox.checked) {
        selectedIds.add(p.id);
        item.classList.add("pm-checked");
      } else {
        selectedIds.delete(p.id);
        item.classList.remove("pm-checked");
      }
      updateEnhanceHint();
    });

    // View
    item.querySelector(".pm-view").addEventListener("click", (e) => {
      e.stopPropagation();
      showModal("Saved Prompt", p.content, [{ label: "Close", action: "close", style: "secondary" }]);
    });

    // Edit
    item.querySelector(".pm-edit").addEventListener("click", (e) => {
      e.stopPropagation();
      showEditModal(p);
    });

    // Delete
    item.querySelector(".pm-delete").addEventListener("click", (e) => {
      e.stopPropagation();
      showModal(
        "Delete Prompt",
        `Are you sure you want to delete this prompt?\n\n"${truncate(p.content, 100)}"`,
        [
          { label: "Cancel", action: "close", style: "secondary" },
          {
            label: "Delete",
            style: "danger",
            action: async () => {
              const ok = await deleteSavedPrompt(p.id);
              if (ok) {
                selectedIds.delete(p.id);
                await fetchSavedPrompts();
                renderTabContent();
              }
              closeModal();
            },
          },
        ]
      );
    });

    container.appendChild(item);
  });

  updateEnhanceHint();
}

function _bindSearch(container) {
  const input = container.querySelector("#pm-search");
  if (input) {
    input.addEventListener("input", (e) => {
      searchQuery = e.target.value;
      renderContextTab(container);
      // Re-focus and restore cursor
      const newInput = container.querySelector("#pm-search");
      if (newInput) {
        newInput.focus();
        newInput.selectionStart = newInput.selectionEnd = searchQuery.length;
      }
    });
  }
}

function updateEnhanceHint() {
  const hint = document.getElementById("pm-enhance-hint");
  if (!hint) return;
  const count = selectedIds.size;
  if (count > 0) {
    hint.textContent = `${count} prompt${count > 1 ? "s" : ""} selected · Ctrl+Shift+E`;
  } else {
    hint.textContent = "Ctrl+Shift+E for instant enhance";
  }
}

// ══════════════════════════════════════════════════════════════
// RENDER: SAVE TAB
// ══════════════════════════════════════════════════════════════

function renderSaveTab(container) {
  const currentText = getCurrentInputText();

  container.innerHTML = `
    <div class="pm-save-form">
      <div class="pm-field">
        <label class="pm-label">Prompt content</label>
        <textarea class="pm-textarea" id="pm-save-content" placeholder="Paste or type the prompt you want to save...">${escHtml(currentText)}</textarea>
      </div>
      <div class="pm-field">
        <label class="pm-label">Title <span style="color:var(--pm-text-muted)">(optional)</span></label>
        <input class="pm-input" id="pm-save-title" placeholder="e.g. Code review template" />
      </div>
      <div class="pm-field">
        <label class="pm-label">Tags <span style="color:var(--pm-text-muted)">(optional, comma-separated)</span></label>
        <input class="pm-input" id="pm-save-tags" placeholder="e.g. coding, review" />
      </div>
      <div class="pm-btn-row">
        <button class="pm-btn pm-btn-primary" id="pm-save-btn" style="flex:1">Save Prompt</button>
      </div>
      <div class="pm-status" id="pm-save-status"></div>
    </div>
  `;

  document.getElementById("pm-save-btn").addEventListener("click", async () => {
    const content = document.getElementById("pm-save-content").value.trim();
    if (!content) {
      setStatus("pm-save-status", "Please enter prompt content.", "error");
      return;
    }
    const title = document.getElementById("pm-save-title").value.trim();
    const tagsRaw = document.getElementById("pm-save-tags").value.trim();
    const tags = tagsRaw ? tagsRaw.split(",").map((t) => t.trim()).filter((t) => t) : [];

    const btn = document.getElementById("pm-save-btn");
    btn.disabled = true;
    btn.textContent = "Saving...";

    const ok = await createSavedPrompt(content, title, tags);
    if (ok) {
      setStatus("pm-save-status", "Prompt saved successfully.", "success");
      document.getElementById("pm-save-content").value = "";
      document.getElementById("pm-save-title").value = "";
      document.getElementById("pm-save-tags").value = "";
      await fetchSavedPrompts();
    } else {
      setStatus("pm-save-status", "Failed to save. Check login status.", "error");
    }
    btn.disabled = false;
    btn.textContent = "Save Prompt";
  });
}

// ══════════════════════════════════════════════════════════════
// ENHANCE HANDLER
// ══════════════════════════════════════════════════════════════

async function handleEnhance() {
  const auth = await getAuth();
  if (!auth) {
    showToast("Please log in first (click the extension icon).", "error");
    return;
  }
  if (isTokenExpired(auth.token)) {
    showToast("Session expired — re-login from extension popup.", "error");
    return;
  }

  const inputText = getCurrentInputText();
  if (!inputText || inputText.trim().length < 3) {
    showToast("Type a prompt in the chat input first.", "error");
    return;
  }

  // Show enhancing state
  const btn = document.getElementById("pm-enhance-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Enhancing...";
  }
  showToast(`Enhancing in ${currentMode} mode...`, "info");

  const result = await enhancePrompt(inputText, Array.from(selectedIds));

  if (btn) {
    btn.disabled = false;
    btn.textContent = "Enhance Current Prompt";
  }

  if (!result) {
    showToast("Enhancement failed. Check connection.", "error");
    return;
  }

  lastEnhanceResult = result;

  // Show diff-style preview modal
  showDiffModal(result);
}

// ══════════════════════════════════════════════════════════════
// DIFF PREVIEW MODAL — Shows original vs enhanced
// ══════════════════════════════════════════════════════════════

function showDiffModal(result) {
  const overlay = getOrCreateModalOverlay();
  const modal = overlay.querySelector(".pm-modal");

  const contextLine = result.context_used
    ? `${result.context_used.selected} selected · ${result.context_used.auto_matched} auto-matched · ${result.context_used.conversation_messages} conversation msgs`
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
      <button class="pm-btn pm-btn-secondary" id="pm-save-enhanced">Save</button>
      <button class="pm-btn pm-btn-primary" id="pm-use-enhanced">Use This Prompt</button>
    </div>
  `;

  overlay.querySelectorAll(".pm-modal-close-btn").forEach((b) =>
    b.addEventListener("click", closeModal)
  );

  // Use enhanced prompt
  document.getElementById("pm-use-enhanced").addEventListener("click", () => {
    applyToInput(result.enhanced);
    closeModal();
    showFeedbackToast(result);
  });

  // Save enhanced prompt
  document.getElementById("pm-save-enhanced").addEventListener("click", async () => {
    const ok = await createSavedPrompt(result.enhanced, null, []);
    if (ok) {
      showToast("Enhanced prompt saved!", "success");
      await fetchSavedPrompts();
    }
    closeModal();
  });

  overlay.classList.add("pm-visible");
}

// ══════════════════════════════════════════════════════════════
// SMART SAVE + FEEDBACK TOASTS
// ══════════════════════════════════════════════════════════════

function showFeedbackToast(result) {
  // After applying the enhanced prompt, show a subtle feedback bar
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

  // Auto-show
  requestAnimationFrame(() => toast.classList.add("pm-toast-visible"));

  // Auto-dismiss after 8 seconds
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
// EDIT MODAL
// ══════════════════════════════════════════════════════════════

function showEditModal(prompt) {
  const overlay = getOrCreateModalOverlay();
  const modal = overlay.querySelector(".pm-modal");

  modal.innerHTML = `
    <div class="pm-modal-header">
      <span class="pm-modal-title">Edit Prompt</span>
      <button class="pm-header-close pm-modal-close-btn">×</button>
    </div>
    <div class="pm-modal-body">
      <label class="pm-label">Content</label>
      <textarea class="pm-edit-textarea" id="pm-edit-content">${escHtml(prompt.content)}</textarea>
      <label class="pm-label">Title <span style="color:var(--pm-text-muted)">(optional)</span></label>
      <input class="pm-edit-input" id="pm-edit-title" value="${escHtml(prompt.title || "")}" placeholder="Optional title" />
      <label class="pm-label">Tags <span style="color:var(--pm-text-muted)">(optional, comma-separated)</span></label>
      <input class="pm-edit-input" id="pm-edit-tags" value="${escHtml((prompt.tags || []).join(", "))}" placeholder="e.g. coding, review" />
    </div>
    <div class="pm-modal-footer">
      <button class="pm-btn pm-btn-secondary pm-modal-close-btn">Cancel</button>
      <button class="pm-btn pm-btn-primary" id="pm-edit-save">Save Changes</button>
    </div>
  `;

  overlay.querySelectorAll(".pm-modal-close-btn").forEach((b) =>
    b.addEventListener("click", closeModal)
  );

  document.getElementById("pm-edit-save").addEventListener("click", async () => {
    const content = document.getElementById("pm-edit-content").value.trim();
    const title = document.getElementById("pm-edit-title").value.trim();
    const tagsRaw = document.getElementById("pm-edit-tags").value.trim();
    const tags = tagsRaw ? tagsRaw.split(",").map((t) => t.trim()).filter((t) => t) : [];
    if (!content) return;

    const fields = {};
    if (content !== prompt.content) fields.content = content;
    if (title !== (prompt.title || "")) fields.title = title || null;
    if (JSON.stringify(tags) !== JSON.stringify(prompt.tags || [])) fields.tags = tags;

    if (Object.keys(fields).length === 0) { closeModal(); return; }

    const btn = document.getElementById("pm-edit-save");
    btn.disabled = true;
    btn.textContent = "Saving...";

    const ok = await updateSavedPrompt(prompt.id, fields);
    if (ok) {
      await fetchSavedPrompts();
      renderTabContent();
    }
    closeModal();
  });

  overlay.classList.add("pm-visible");
}

// ══════════════════════════════════════════════════════════════
// GENERIC MODAL
// ══════════════════════════════════════════════════════════════

function showModal(title, body, buttons = []) {
  const overlay = getOrCreateModalOverlay();
  const modal = overlay.querySelector(".pm-modal");

  const footerBtns = buttons
    .map(
      (b, i) =>
        `<button class="pm-btn pm-btn-${b.style || "primary"}" data-idx="${i}">${escHtml(b.label)}</button>`
    )
    .join("");

  modal.innerHTML = `
    <div class="pm-modal-header">
      <span class="pm-modal-title">${escHtml(title)}</span>
      <button class="pm-header-close pm-modal-close-btn">×</button>
    </div>
    <div class="pm-modal-body">${escHtml(body)}</div>
    <div class="pm-modal-footer">${footerBtns}</div>
  `;

  overlay.querySelector(".pm-modal-close-btn").addEventListener("click", closeModal);

  buttons.forEach((b, i) => {
    const el = modal.querySelector(`[data-idx="${i}"]`);
    if (b.action === "close") {
      el.addEventListener("click", closeModal);
    } else if (typeof b.action === "function") {
      el.addEventListener("click", b.action);
    }
  });

  overlay.classList.add("pm-visible");
}

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
// INPUT DETECTION & PASSIVE TRACKING
// ══════════════════════════════════════════════════════════════

function getCurrentInputText() {
  const selectors = [
    "#prompt-textarea",
    "[contenteditable='true']",
    "textarea",
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.offsetParent !== null) {
      return el.innerText || el.value || "";
    }
  }
  return "";
}

function applyToInput(text) {
  const selectors = [
    "#prompt-textarea",
    "[contenteditable='true']",
    "textarea",
  ];
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

function setupPassiveTracking() {
  let lastText = "";

  document.addEventListener("input", (e) => {
    const el = e.target;
    if (
      el.matches("#prompt-textarea, [contenteditable='true'], textarea") &&
      el.offsetParent !== null
    ) {
      lastText = el.innerText || el.value || "";
    }
  }, true);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && lastText.trim().length > 5) {
      trackPrompt(lastText);
      lastText = "";
    }
  }, true);

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (
      btn &&
      !btn.classList.contains("pm-trigger") &&
      !btn.closest("#pm-panel") &&
      !btn.closest("#pm-modal-overlay") &&
      lastText.trim().length > 5
    ) {
      const nearInput = btn.closest("form") || btn.parentElement;
      if (nearInput && nearInput.querySelector("textarea, [contenteditable='true']")) {
        trackPrompt(lastText);
        lastText = "";
      }
    }
  }, true);
}

// ══════════════════════════════════════════════════════════════
// VOICE-TO-PROMPT ENGINE (Web Speech API)
// Speak → Transcribe live → Auto-enhance → Preview → Apply
// ══════════════════════════════════════════════════════════════

function toggleVoice() {
  if (isRecording) {
    stopVoice();
  } else {
    startVoice();
  }
}

function startVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showToast("Voice not supported in this browser.", "error");
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";

  voiceFinalTranscript = "";
  voiceInterimTranscript = "";
  let silenceTimer = null;

  // Show live transcript overlay
  showVoiceOverlay();
  isRecording = true;
  updateVoiceUI(true);

  recognition.onresult = (event) => {
    voiceInterimTranscript = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        voiceFinalTranscript += t + " ";
      } else {
        voiceInterimTranscript += t;
      }
    }
    updateVoiceOverlay(voiceFinalTranscript, voiceInterimTranscript);

    // Reset silence timer — auto-stop after 2s of silence
    clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => {
      if (isRecording) {
        stopVoice();
      }
    }, 2500);
  };

  recognition.onerror = (event) => {
    console.log("Voice error:", event.error);
    if (event.error === "not-allowed") {
      showToast("Microphone access denied. Allow it in browser settings.", "error");
    } else if (event.error !== "aborted") {
      showToast("Voice error: " + event.error, "error");
    }
    cleanupVoice();
  };

  recognition.onend = () => {
    clearTimeout(silenceTimer);
    if (isRecording) {
      // Ended naturally — process via finishVoice
      finishVoice();
    }
  };

  try {
    recognition.start();
    showToast("🎤 Listening... speak your prompt", "info");
  } catch (e) {
    showToast("Could not start voice. Try again.", "error");
    cleanupVoice();
  }
}

function stopVoice() {
  if (!recognition) return;
  isRecording = false;
  try { recognition.stop(); } catch (e) { }
  finishVoice();
}

function finishVoice() {
  isRecording = false;
  updateVoiceUI(false);
  hideVoiceOverlay();

  // Combine finalized text + any in-progress interim text
  const text = (voiceFinalTranscript + voiceInterimTranscript).trim();

  recognition = null;
  voiceFinalTranscript = "";
  voiceInterimTranscript = "";

  if (text.length > 2) {
    showToast("Transcribed! Enhancing...", "info");
    handleVoiceEnhance(text);
  } else {
    showToast("Didn't catch anything. Try speaking louder.", "error");
  }
}

function cleanupVoice() {
  isRecording = false;
  recognition = null;
  voiceFinalTranscript = "";
  voiceInterimTranscript = "";
  updateVoiceUI(false);
  hideVoiceOverlay();
}

async function handleVoiceEnhance(transcribedText) {
  // Put transcribed text into the chat input first
  applyToInput(transcribedText);

  // Now enhance it
  const auth = await getAuth();
  if (!auth || isTokenExpired(auth.token)) {
    showToast("Please log in first.", "error");
    return;
  }

  const result = await enhancePrompt(transcribedText, Array.from(selectedIds));

  if (!result) {
    showToast("Enhancement failed.", "error");
    return;
  }

  lastEnhanceResult = result;
  showDiffModal(result);
}

// ── Voice UI: Overlay with live transcript ──

function showVoiceOverlay() {
  let overlay = document.getElementById("pm-voice-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "pm-voice-overlay";
    overlay.className = "pm-voice-overlay";
    overlay.innerHTML = `
      <div class="pm-voice-card">
        <div class="pm-voice-indicator">
          <div class="pm-voice-pulse"></div>
          <span class="pm-voice-label">Listening...</span>
        </div>
        <div class="pm-voice-transcript" id="pm-voice-transcript">Say something...</div>
        <button class="pm-btn pm-btn-secondary pm-voice-stop" id="pm-voice-stop">Stop & Enhance</button>
      </div>
    `;
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) stopVoice();
    });
    document.body.appendChild(overlay);
    document.getElementById("pm-voice-stop").addEventListener("click", stopVoice);
  }
  requestAnimationFrame(() => overlay.classList.add("pm-visible"));
}

function updateVoiceOverlay(final, interim) {
  const el = document.getElementById("pm-voice-transcript");
  if (!el) return;
  const display = final + (interim ? `<span class="pm-voice-interim">${escHtml(interim)}</span>` : "");
  el.innerHTML = display || "Say something...";
  // Auto-scroll
  el.scrollTop = el.scrollHeight;
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
    btn.innerHTML = recording ? "⏹" : "🎤";
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

function setStatus(id, msg, type) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.className = `pm-status${type === "success" ? " pm-status-success" : type === "error" ? " pm-status-error" : ""}`;
}

// ══════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════

async function init() {
  const auth = await getAuth();
  if (!auth) {
    console.log("Prompt Memory: not logged in, panel will prompt login.");
  }

  createTrigger();
  createPanel();
  setupKeyboardShortcut();
  setupPassiveTracking();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => setTimeout(init, 500));
} else {
  setTimeout(init, 500);
}