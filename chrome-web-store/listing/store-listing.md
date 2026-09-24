# Store listing tab

Copy each block into the matching field of the Chrome Web Store Developer
Dashboard (**Items → Prompt Memory → Store listing**). Character counts are
the store's limits.

## Name (from the manifest, 75 max)

    Prompt Memory

The name comes from `extension/manifest.json`. Leave it as it is. Names that
stack keywords ("Prompt Memory – ChatGPT, Claude, Gemini Prompt Enhancer") get
flagged as keyword spam, and the description already names every site.

## Summary (from the manifest `description`, 132 max)

Current (119 characters):

    One-click prompt engineering — turns your raw thoughts into precision-crafted LLM queries. Free, with your own API key.

Recommended (125 characters). This version tells a store visitor where it works and that nothing is replaced without review:

    Rewrite rough drafts into clear prompts in ChatGPT, Claude, Gemini, Perplexity and Grok. Review each rewrite before it's used.

The summary is read from the manifest, so changing it means editing
`description` in `extension/manifest.json` and rebuilding the ZIP
(`python3 scripts/package_extension.py`).

## Category and language

- **Category:** Productivity → Tools. Workflow & Planning also fits. Use the closest option the dashboard offers.
- **Language:** English (United States)

## Description (16,000 max)

```
A vague prompt gets a vague answer. Prompt Memory turns the rough draft you'd normally send into a clear, specific prompt, right inside the AI chat you already use.

HOW IT WORKS
1. Type your draft the way you think: "plan a 5 day japan trip in april, budget like 2k, not too touristy".
2. Click the ⊕ button beside the chat box (or press Ctrl+Shift+E, ⌘+Shift+E on Mac).
3. A card shows the rewrite: "Plan a 5-day trip to Japan for me in early April. My budget is about $2,000 excluding flights, and I'd rather avoid the most touristy spots. Suggest a day-by-day itinerary…"
4. Replace your draft with it, compare it with your original, or dismiss it. Nothing changes in your chat box until you choose.

THREE STYLES, EVERY VERSION KEPT
• Deep (default) adds the context and structure your request implies, without inventing new requirements.
• Quick keeps it to one to three sentences.
• Creative opens the question up and invites other angles.
Not quite right? Click "Shorter", "More detail" or "Open-ended" on the card. Every version stays on the card, so you can step back to the one you liked.

YOUR PROMPT LIBRARY, ONE // AWAY
Save prompts that work. Later, type // in any supported chat box to search them and press Enter to insert one where you were typing. Open the full library with Ctrl+Shift+L (⌘+Shift+L on Mac) to search, rename, delete, or attach saved prompts as context for a rewrite.

WORKS WHERE YOU ALREADY CHAT
ChatGPT (chatgpt.com), Claude (claude.ai), Gemini (gemini.google.com), Perplexity (perplexity.ai) and Grok (grok.com and x.com/i/grok).

TWO WAYS TO USE IT
• Your own API key, no account: paste a Groq, Gemini or OpenRouter key. Your draft goes straight from your browser to that provider, and Prompt Memory's server never sees it. The provider's own limits and terms apply.
• Sign in with Google: get a free daily allowance of rewrites with no key, plus a synced prompt library, rewrite history, conversation-aware rewrites and Voice-to-Prompt.

YOU'RE IN CONTROL
• Rewrites are shown for review first, and your draft is only replaced when you choose "Replace draft".
• Conversation context (sending recent messages from the current chat with a signed-in rewrite) has its own on/off switch.
• Prompt tracking, // shortcuts and every other data setting has its own switch under Library → ⋯ → Privacy settings.
• "Delete account & data" in the toolbar popup erases your account, history, saved prompts and feedback.

KEYBOARD SHORTCUTS
• Ctrl/⌘+Shift+E: rewrite the current draft
• Ctrl/⌘+Shift+L: open your library
• Ctrl/⌘+Shift+V: Voice to Prompt (signed in)
• [ and ]: step between versions on the card
• Esc: minimize the card to the pill

Privacy policy: https://prompt-engineering-skeleton-seven.vercel.app/privacy

Prompt Memory is an independent project and is not affiliated with or endorsed by OpenAI, Anthropic, Google, Perplexity or xAI.
```

Before pasting, check these three lines against the build you upload:

- **"free daily allowance"**: the popup currently says 15 enhancements a day. The number is left out here so a quota change can't make the listing wrong.
- **"Prompt tracking … has its own switch"**: this line is deliberately neutral about the default. See the tracking blocker in `../README.md`. Once that is resolved, you may add "Prompt tracking is off unless you turn it on" if that is what the code does.
- **Voice-to-Prompt**: it needs sign-in and microphone permission. Keep it in the description only if it works on the build you upload.

## Graphic assets

| Dashboard field | File | Spec |
|---|---|---|
| Store icon | `images/icon/store-icon-128.png` | 128×128 PNG, 96px art + 16px transparent padding |
| Screenshots (1–5) | `images/screenshots/01…05-*.png`, in order | 1280×800, 24-bit PNG, no alpha |
| Small promo tile | `images/promo-tiles/small-promo-tile-440x280.png` | 440×280 |
| Marquee promo tile | `images/promo-tiles/marquee-promo-tile-1400x560.png` | 1400×560 (only used if Google features the item) |
| Global promo video | YouTube URL of `video/prompt-memory-demo-1080p.mp4` | see `youtube-video.md` |

`images/screenshots-unframed/` holds the same captures without headline
frames: raw 1280×800 browser shots. Use them if you prefer plain screenshots,
or for the website and GitHub README.

## Additional fields

- **Official URL:** leave empty unless you verify a domain in Search Console. A `vercel.app` subdomain can't be verified.
- **Homepage URL:** `https://prompt-engineering-skeleton-seven.vercel.app/`
- **Support URL:** `https://github.com/siddhm11/prompt_engineering_skeleton/issues`, or a `mailto:` for `hello.promptmemory@gmail.com`
- **Mature content:** No
