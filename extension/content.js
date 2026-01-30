// content.js - FINAL VERSION

// PASTE YOUR LOCALTUNNEL URL HERE
const API_URL = "https://stale-peaches-check.loca.lt";

function createButton(targetArea) {
  if (targetArea.parentElement.querySelector(".ai-enhance-btn")) return;

  const btn = document.createElement("button");
  btn.innerText = "✨ Memory";
  btn.className = "ai-enhance-btn";

  btn.onclick = async (e) => {
    e.preventDefault();
    const originalText = targetArea.innerText || targetArea.value;

    if (!originalText) return alert("Please type a prompt first!");

    btn.innerText = "🧠 Thinking...";

    try {
      const response = await fetch(`${API_URL}/enhance`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Bypass-Tunnel-Reminder": "true", // <--- THE FIX
        },
        body: JSON.stringify({
          user_id: "user_001",
          prompt: originalText,
          platform: window.location.hostname,
        }),
      });

      if (!response.ok) throw new Error("Server Error: " + response.statusText);

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
      alert("Error: Is your Python server running? " + error.message);
    } finally {
      btn.innerText = "✨ Memory";
    }
  };

  targetArea.parentElement.style.position = "relative";
  targetArea.parentElement.appendChild(btn);
}

const observer = new MutationObserver(() => {
  // Selectors for different platforms
  const selectors = [
    "#prompt-textarea",                 // ChatGPT
    ".ql-editor[contenteditable='true']", // Gemini
    "div[contenteditable='true']",      // Claude & others
    "textarea"                          // Standard fallbacks
  ];
  
  selectors.forEach((sel) => {
    document.querySelectorAll(sel).forEach((el) => {
      // Prevent adding multiple buttons to the same container
      if (!el.parentElement.querySelector(".ai-enhance-btn")) {
        createButton(el);
      }
    });
  });
});
