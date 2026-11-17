# How to export your data from each platform

ChatWrapped reads the **official data exports** each platform lets you
download. No scraping, no logins, no API keys — you export a file, we parse
it locally.

> Screenshots of these click-paths are on the roadmap (recorded with
> [vhs](https://github.com/charmbracelet/vhs)); the steps below are exact.

## ChatGPT (OpenAI)

1. Go to <https://chatgpt.com> and sign in.
2. Click your **profile picture** (bottom-left) → **Settings**.
3. Open the **Data controls** tab.
4. Next to **Export data**, click **Export** → confirm **Export**.
5. You'll get an email with a download link (usually within minutes). The
   file is a `.zip`.
   - Newer exports nest the chats inside
     `User Online Activity/Conversations__*-chatgpt-0001.zip` — ChatWrapped
     handles both that and the legacy single `conversations.json`.

**Point ChatWrapped at:** the downloaded `.zip`, the extracted folder, or the
`conversations.json` inside it — all work.

## Claude (Anthropic)

1. Go to <https://claude.ai> and sign in.
2. Click your **profile picture** → **Settings** → **Privacy** (or
   **Account** → **Export data**, depending on region).
3. Click **Export my data** and confirm. You'll receive a `.zip` by email /
   download link containing `conversations-000.zip` (plus `projects`,
   `memories`).

**Point ChatWrapped at:** the `.zip` or the extracted folder.

## Google Gemini

1. Go to <https://takeout.google.com>, sign in.
2. Click **Deselect all**, then tick only **Gemini** (and optionally
   **My Activity**).
3. Click **Next step** → **Create export**. When it's ready, download the
   `.zip` / `.tgz`.

**Point ChatWrapped at:** the downloaded archive or the extracted `Takeout/`
folder. Gemini parsing is **experimental / best-effort** — if your Takeout
layout isn't recognized, `chatwrapped scan` will tell you, and you can open
an issue with the folder structure (never with your data).

## Merging multiple exports

Just pass them all at once — overlapping exports are deduplicated
automatically (same conversation id → the most recent version wins):

```bash
chatwrapped build ~/Downloads/chatgpt-export.zip ~/Downloads/claude-export.zip ~/Downloads/Takeout -o wrapped/
```
