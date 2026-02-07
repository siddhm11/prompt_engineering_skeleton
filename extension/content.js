// extension/content.js - FINAL ROBUST VERSION

// const API_URL = "https://siddhm11-prompt-engine.hf.space";
const API_URL = "https://siddhm11-prompt-engine.hf.space";

console.log("🚀 Prompt Memory: Script loaded on", window.location.hostname);

// --- 1. EXISTING BUTTON LOGIC ---
function createButton(targetArea) {
  // Prevent adding multiple buttons
  if (targetArea.parentElement.querySelector(".ai-enhance-btn")) return;

  const btn = document.createElement("button");
  btn.innerText = "✨ Memory";
  btn.className = "ai-enhance-btn";

  btn.onclick = async (e) => {
    e.preventDefault();

    // 1. GET TOKEN FROM STORAGE
    chrome.storage.local.get(["user_id", "token"], async (result) => {
      if (!result.token) {
        alert("⚠️ Please click the extension icon and Log In first!");
        return;
      }

      const originalText = targetArea.innerText || targetArea.value;
      if (!originalText) return alert("Please type a prompt first!");

      btn.innerText = "🧠 Thinking...";

      try {
        const response = await fetch(`${API_URL}/enhance`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${result.token}` // <--- JWT HEADER
          },
          body: JSON.stringify({
            user_id: result.user_id,
            prompt: originalText,
            platform: window.location.hostname,
          }),
        });

        const data = await response.json();
        const useEnhanced = confirm(
          `ORIGINAL:\n${data.original}\n\n✨ ENHANCED:\n${data.enhanced}\n\nPress OK to use Enhanced.`
        );

        if (useEnhanced) {
          if (targetArea.tagName === "TEXTAREA") {
            targetArea.value = data.enhanced;
            targetArea.dispatchEvent(new Event("input", { bubbles: true }));
          } else {
            targetArea.innerText = data.enhanced;
          }
        }
      } catch (error) {
        alert("Error: " + error.message);
      } finally {
        btn.innerText = "✨ Memory";
      }
    });
  };

  // Ensure positioning works relative to the container
  if (getComputedStyle(targetArea.parentElement).position === 'static') {
    targetArea.parentElement.style.position = "relative";
  }
  targetArea.parentElement.appendChild(btn);

  // ✅ Attach the new Robust Tracker
  setupPassiveTracking(targetArea);
}


// --- 2. ROBUST PASSIVE TRACKING (Keys + Clicks) ---
// --- 2. ROBUST PASSIVE TRACKING (Keys + Clicks) ---
function setupPassiveTracking(inputElement) {
  if (inputElement.dataset.hasTracker) return;
  inputElement.dataset.hasTracker = "true";

  console.log("🕵️ Passive tracker attached");

  // A. Track text AS YOU TYPE (to handle instant-clearing on send)
  let lastTypedText = "";
  inputElement.addEventListener("input", (e) => {
    lastTypedText = e.target.value || e.target.innerText;
  });

  // Helper: Send to Backend
  const sendToMemory = (text) => {
    if (text && text.trim().length > 5) {

      // Check auth first
      chrome.storage.local.get(["user_id"], (result) => {
        if (!result.user_id) return; // Don't track if not logged in

        console.log("📡 Passive tracking for user:", result.user_id);
        fetch(`${API_URL}/track`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: result.user_id, // <--- DYNAMIC ID
            prompt: text,
            platform: window.location.hostname
          })
        }).catch(err => console.error("Tracker failed:", err));
      });
    }
  };

  // B. Listener 1: The "Enter" Key
  inputElement.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      // Use the variable we've been tracking
      sendToMemory(lastTypedText);
    }
  });

  // C. Listener 2: The "Send" Button Click
  // We listen to the parent container for ANY button click
  const parentForm = inputElement.closest("form") || inputElement.parentElement.parentElement;

  if (parentForm) {
    parentForm.addEventListener("click", (e) => {
      // 1. Find the closest button to what was clicked
      const clickedBtn = e.target.closest("button");

      // 2. If a button was clicked, and it's NOT our "Memory" button
      if (clickedBtn && !clickedBtn.classList.contains("ai-enhance-btn")) {
        console.log("🖱️ Send button clicked!");
        sendToMemory(lastTypedText);
      }
    }, { capture: true }); // 'capture' helps catch it before other scripts stop it
  }
}


// --- 3. OBSERVER LOGIC ---
function checkForInput() {
  const selectors = [
    "#prompt-textarea",           // ChatGPT
    "[contenteditable='true']",   // Claude/Gemini
    "textarea"                    // Fallback
  ];

  selectors.forEach((sel) => {
    document.querySelectorAll(sel).forEach((el) => {
      // Check if it's visible and doesn't have a button yet
      if (el.offsetParent !== null && !el.parentElement.querySelector(".ai-enhance-btn")) {
        createButton(el);
      }
    });
  });
}

// Start
checkForInput();
const observer = new MutationObserver(() => checkForInput());
observer.observe(document.body, { childList: true, subtree: true });