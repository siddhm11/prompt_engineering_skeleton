# Test instructions tab

Google's reviewers read this box (**Items → Prompt Memory → Test
instructions**). Give them a working path that doesn't depend on your server
being awake. The HF Space can cold-start, and a reviewer who hits a timeout
may reject the item for "does not work".

Fill in the two placeholders before pasting. Use a **disposable** Google
account, and a Groq key made just for review that you revoke after approval.

```
No payment or special hardware is needed. Two ways to test:

A) Fastest, no account (bring-your-own-key):
1. Click the Prompt Memory toolbar icon, choose "Agree & continue" on the one-time data notice, then open "Use your own API key".
2. Choose Groq and paste this review-only key: <GROQ_REVIEW_KEY>
3. Open https://chatgpt.com (works logged out), https://gemini.google.com or https://www.perplexity.ai.
4. Type a rough request in the chat box, e.g. "plan a 5 day japan trip in april, budget like 2k, not too touristy".
5. Click the round ⊕ button at the bottom right (or press Ctrl+Shift+E / ⌘+Shift+E). A card shows the rewrite.
6. On the card, try "Shorter" (a second version is added; use ‹ › or [ ] to step between versions), "Show original", then "Replace draft" to put the rewrite in the chat box. Nothing is sent to the chat site; the user still presses its own Send.

B) Signed in (library, history, // menu):
1. In the popup choose "Continue with Google" and sign in with: <REVIEW_GOOGLE_ACCOUNT> / <PASSWORD>
2. On a chat site, type a draft and press ⊕. Then press Ctrl+Shift+L (⌘+Shift+L) to open the library; use "Save" at the top to save the chat box text.
3. In the chat box type //, then part of the saved prompt's title; press Enter to insert it at the cursor.
4. Library → ⋯ → Privacy settings shows the Prompt tracking, Conversation context and // switches.
5. Popup → "Delete account & data", type DELETE, confirm: the account and its data are erased and the extension signs out.

The first signed-in request can take up to ~30 seconds if our server was idle (it is hosted on Hugging Face Spaces). Route A has no such delay.
```

A Google account with 2-step verification will block the reviewer. Use one
without it, or give them route A only.
