// extension/background.js — MV3 service worker
//
// Two jobs:
//
// 1. KEYBOARD SHORTCUTS. manifest.json declares a "commands" block, and Chrome
//    intercepts a registered command chord at the browser level — it never
//    reaches the page, so the content script's own keydown listener could not
//    see it. Previously there was no service worker at all, so nothing handled
//    chrome.commands.onCommand and the declared shortcuts did nothing on the
//    platforms where Chrome won the race. The handler below closes that gap by
//    forwarding the command to the active tab.
//
// 2. API KEY CUSTODY. The user's own provider key lives here and only here.
//    The content script runs in an isolated world on chatgpt.com, claude.ai and
//    other third-party origins; that is the wrong place for a credential. The
//    content script asks this worker to perform an enhancement and receives
//    only text back — it never learns the key.

import {
  PROVIDERS,
  DEFAULT_PROVIDER,
  DEFAULT_MODEL,
  streamCompletion,
  completion,
  validateKey,
} from "./lib/providers.js";

const DEFAULT_API_URL = "https://siddhm11-prompt-engine.hf.space";

// ─────────────────────────────────────────────────────────────
// SHORTCUTS
// ─────────────────────────────────────────────────────────────

chrome.commands.onCommand.addListener(async (command) => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  try {
    await chrome.tabs.sendMessage(tab.id, { type: "PM_COMMAND", command });
  } catch {
    // No content script on this tab (not one of our matched sites). Nothing to do.
  }
});

// ─────────────────────────────────────────────────────────────
// SETTINGS
// ─────────────────────────────────────────────────────────────

async function getSettings() {
  // chrome.storage.local, never .sync: sync replicates through the user's
  // Google account to every signed-in browser, which is not somewhere an API
  // key should silently travel.
  const s = await chrome.storage.local.get([
    "byok_provider", "byok_key", "byok_model", "api_url", "token", "user_id",
  ]);
  return {
    provider: s.byok_provider || DEFAULT_PROVIDER,
    key: s.byok_key || "",
    model: s.byok_model || DEFAULT_MODEL,
    apiUrl: s.api_url || DEFAULT_API_URL,
    token: s.token || "",
    userId: s.user_id || "",
  };
}

/**
 * Which path an enhancement should take.
 *
 *   backend  — signed in. Full memory features. If the user also has a key it
 *              rides along so their own quota is spent, not the shared one.
 *   direct   — not signed in but has a key. No signup, no server, no memory.
 *   none     — neither. The UI prompts for one or the other.
 */
function resolveRoute(settings) {
  if (settings.token) return "backend";
  if (settings.key) return "direct";
  return "none";
}

// ─────────────────────────────────────────────────────────────
// MESSAGE HANDLING
// ─────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Only our own surfaces may talk to this worker. A message whose sender has
  // no extension id is not from our content script or popup.
  if (sender.id !== chrome.runtime.id) return false;

  (async () => {
    try {
      switch (msg?.type) {
        case "PM_GET_ROUTE": {
          const settings = await getSettings();
          const provider = PROVIDERS[settings.provider];
          sendResponse({
            route: resolveRoute(settings),
            hasKey: Boolean(settings.key),
            signedIn: Boolean(settings.token),
            provider: settings.provider,
            providerLabel: provider?.label || settings.provider,
            model: settings.model,
          });
          break;
        }

        case "PM_VALIDATE_KEY": {
          sendResponse(await validateKey(msg.provider, msg.key));
          break;
        }

        case "PM_ENHANCE_DIRECT": {
          const settings = await getSettings();
          if (!settings.key) {
            sendResponse({ ok: false, error: "No API key set." });
            break;
          }
          const text = await completion({
            providerId: settings.provider,
            apiKey: settings.key,
            modelId: settings.model,
            rawText: msg.prompt,
            mode: msg.mode || "deep",
          });
          if (!text) {
            sendResponse({ ok: false, error: "The model returned an empty response." });
            break;
          }
          sendResponse({
            ok: true, enhanced: text, model: settings.model,
            provider: settings.provider, direct: true,
          });
          break;
        }

        // The credential the content script must never see, handed to the
        // backend so a signed-in user still gets memory features while
        // spending their own quota.
        case "PM_GET_BYOK_FOR_BACKEND": {
          const settings = await getSettings();
          sendResponse(
            settings.key
              ? { provider: settings.provider, key: settings.key, model: settings.model }
              : {}
          );
          break;
        }

        default:
          sendResponse({ ok: false, error: `Unknown message type: ${msg?.type}` });
      }
    } catch (err) {
      sendResponse({ ok: false, error: err?.message || String(err) });
    }
  })();

  return true;   // keeps the port open for the async sendResponse above
});

// ─────────────────────────────────────────────────────────────
// STREAMING
// ─────────────────────────────────────────────────────────────
//
// Streamed tokens go over a long-lived port rather than sendMessage, so the
// content script can paint text as it arrives instead of waiting for the whole
// completion. A one-shot sendMessage cannot deliver progressive chunks.

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "pm-stream") return;
  if (port.sender?.id !== chrome.runtime.id) return;

  const controller = new AbortController();
  port.onDisconnect.addListener(() => controller.abort());

  port.onMessage.addListener(async (msg) => {
    if (msg?.type !== "PM_ENHANCE_STREAM") return;
    try {
      const settings = await getSettings();
      if (!settings.key) {
        port.postMessage({ type: "error", error: "No API key set." });
        return;
      }
      const full = await streamCompletion({
        providerId: settings.provider,
        apiKey: settings.key,
        modelId: settings.model,
        rawText: msg.prompt,
        mode: msg.mode || "deep",
        signal: controller.signal,
        onToken: (token) => {
          try {
            port.postMessage({ type: "token", token });
          } catch {
            // Port closed mid-stream — the user dismissed the panel.
            controller.abort();
          }
        },
      });

      if (!full) {
        port.postMessage({ type: "error", error: "The model returned an empty response." });
        return;
      }
      port.postMessage({
        type: "done", enhanced: full,
        model: settings.model, provider: settings.provider, direct: true,
      });
    } catch (err) {
      if (err?.name === "AbortError") return;
      port.postMessage({ type: "error", error: err?.message || String(err) });
    }
  });
});

// ─────────────────────────────────────────────────────────────
// FIRST RUN
// ─────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  if (reason !== "install") return;
  // Open settings on install so the first thing a new user sees is the one
  // action that makes the extension work, rather than discovering on their
  // first Ctrl+Shift+E that they need an account.
  chrome.tabs.create({ url: chrome.runtime.getURL("popup.html?onboarding=1") });
});
