# Privacy practices tab

Answers for **Items → Prompt Memory → Privacy practices**. Each one was
checked against the 4.6.2 code on 2026-09-24. If the code changes, re-check
the answers: Google compares this form with the extension's behaviour and
with the privacy policy, and a mismatch is a common rejection reason.

## Single purpose (1,000 max)

```
Prompt Memory helps people write better prompts in AI chat sites. It rewrites the draft in the site's chat box into a clearer prompt, shows the rewrite for review, and inserts it only when the user chooses; it also keeps a library of the user's saved prompts to insert into that chat box.
```

## Permission justifications

**storage**
```
Stores the user's settings (default rewrite style, privacy switches, consent), their sign-in session, an in-progress rewrite so it survives a page reload, and, if they choose to bring their own key, their Groq, Gemini or OpenRouter API key. Everything is stored locally in chrome.storage on this device.
```

**scripting**
```
When the extension is installed or updated, chat tabs that are already open do not have the content script yet. scripting injects it into those supported chat tabs only, so the ⊕ button works without the user having to reload each tab.
```

**Host permissions** (one justification covers the list; the dashboard shows one box)
```
chatgpt.com, claude.ai, gemini.google.com, www.perplexity.ai, grok.com and x.com/i/grok: the content script adds the ⊕ button, the rewrite card and the // saved-prompt menu to these sites' chat boxes, reads the draft the user asks to rewrite, and writes the rewrite back when the user chooses Replace. On x.com it runs only on the Grok path (/i/grok*).
siddhm11-prompt-engine.hf.space: Prompt Memory's own server, for Google sign-in and signed-in features (rewrites, saved prompts, history, voice transcription, account deletion).
api.groq.com, generativelanguage.googleapis.com and openrouter.ai: when a user brings their own API key, the rewrite request goes directly from the browser to that provider, with no Prompt Memory server involved.
```

## Remote code

**No, I am not using remote code.**
```
All JavaScript ships in the package (background.js, content.js, popup.js, lib/providers.js). The extension does not use eval, new Function or remotely hosted scripts. Network responses are data only: rewrite text and JSON.
```
(Checked: no `eval(`, `new Function`, `importScripts` or remote `<script src>` in `extension/`.)

## Data usage: what to tick

Google counts data as "collected" when it leaves the device. Tick these:

| Category | Tick? | Why (from the code) |
|---|---|---|
| Personally identifiable information | **Yes** | Google sign-in stores the account **email** (`backend/routers/auth.py`). |
| Health information | No | |
| Financial and payment information | No | |
| Authentication information | **Yes** | A sign-in token (JWT) is sent to our server. A user's own API key goes to *their* provider (Groq, Gemini or OpenRouter) with each rewrite. If they are also signed in, the key is forwarded through our server for that request, as the first-run notice says. |
| Personal communications | **Yes** | With Conversation context on (default: on) and signed in, recent messages from the open chat go with the rewrite. Voice-to-Prompt audio is sent for transcription. |
| Location | No | |
| Web history | No | Only the chat site's hostname goes with a request, never browsing history. |
| User activity | **Yes, while Prompt tracking exists** | Prompt tracking logs prompts the user submits on the supported sites (signed in only). Untick only if tracking is removed. |
| Website content | **Yes** | The draft text read from the chat box, and saved prompts. |

## Certifications (tick all three; the privacy policy supports each)

- I do not sell or transfer user data to third parties, outside of the approved use cases.
- I do not use or transfer user data for purposes that are unrelated to my item's single purpose.
- I do not use or transfer user data to determine creditworthiness or for lending purposes.

"Approved use cases" covers sending the draft to the AI provider that
performs the rewrite, which is the feature the user asked for.

## Privacy policy URL

    https://prompt-engineering-skeleton-seven.vercel.app/privacy

Live, public, no login needed, and identical to `website/privacy.html` as
of 2026-09-24. **It currently says Prompt Tracking is off by default, but the
code turns it on by default.** Fix one of them before submitting (see
`../README.md`, blocker 1).
