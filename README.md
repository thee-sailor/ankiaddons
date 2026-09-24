# Anki Addons

A collection of custom [Anki](https://apps.ankiweb.net/) add-ons for a
medical-study workflow. Each folder is one standalone add-on.

**Contents**
- [How to install (easy, step-by-step)](#how-to-install-easy-step-by-step)
- [Set up each add-on](#set-up-each-add-on)
- [Add-on reference](#add-on-reference)
- [Trouble?](#trouble)
- [Notes & license](#notes--license)

---

# How to install (easy, step-by-step)

No coding needed. If you can copy and paste a folder, you can do this. 🙂

## Part 1 — Download the add-ons (do this once)

1. Go to the repository page:
   **https://github.com/thee-sailor/ankiaddons**
2. Click the green **`< > Code`** button (near the top-right of the file list).
3. Click **Download ZIP**.

   > 📷 *Screenshot placeholder — the green “Code” button with “Download ZIP”.*

4. Find the downloaded file (usually in your **Downloads** folder). It's called
   `ankiaddons-main.zip`.
5. **Unzip it:**
   - **Windows:** right-click the file → **Extract All…** → **Extract**.
   - **Mac:** double-click the file.

   You now have a folder called `ankiaddons-main` containing one folder per
   add-on (like `chatgpt_paste`, `editor_field_search`, and so on).

## Part 2 — Open Anki's add-ons folder

1. Open **Anki** on your computer.
2. In the top menu click **Tools → Add-ons**.
3. In the window that opens, click **View Files**.

   > 📷 *Screenshot placeholder — the Tools → Add-ons window with “View Files”.*

   - A folder called **`addons21`** opens. This is where add-ons live.
   - *(If “View Files” is greyed out, click any add-on in the list first, then
     click View Files, and go one level up to the `addons21` folder.)*

## Part 3 — Copy the add-ons in

1. Go back to the unzipped **`ankiaddons-main`** folder from Part 1.
2. Select the add-on folders you want (or all of them). Each add-on is one
   folder, e.g. `chatgpt_paste`.
3. **Copy** them (Ctrl+C on Windows, Cmd+C on Mac).
4. Go to the **`addons21`** folder you opened in Part 2 and **Paste**
   (Ctrl+V / Cmd+V).
5. **Fully close Anki and open it again.** (Quit completely, not just the
   window.)

That's it — the add-ons are installed. ✅

> **Tip:** To remove an add-on later, just delete its folder from `addons21`
> and restart Anki.

---

# Set up each add-on

Most work immediately. A few need one small step — follow the ones you
installed.

### 📋 chatgpt_paste — paste ChatGPT notes with equations & images
- **Setup:** none.
- **How to use:** In ChatGPT, click **Copy** under a reply. In an Anki card
  field, press **Ctrl+V**. Equations, tables, arrows and images appear
  formatted automatically.

  > 📷 *Screenshot placeholder — a card field showing a rendered equation.*

### 🔍 editor_field_search — find text while editing a card
- **Setup:** none.
- **How to use:** While editing/adding a card, press **Ctrl+F** (or click the
  magnifying-glass icon in the editor toolbar). Type a word; use ▲ / ▼ to jump
  between matches.

  > 📷 *Screenshot placeholder — the search box in the editor toolbar.*

### 🍅 focus_music_pomodoro — study timer + focus music
- **Setup (optional):** On the **Decks** screen, look at the bottom bar. Click
  the **⚙️** (gear) to set your phases (e.g. Study 20 min → break 3 min →
  break 5 min) and to pick a **music folder** from your computer.
- **How to use:** Click the tomato icon to start. It counts down and notifies
  you at each phase. Click the **phase name** to jump to any phase.

  > 📷 *Screenshot placeholder — the bottom bar with the phase name and timer.*

### 🤖 anki_ai_assistant — AI helper sidebar (needs a free key)
This one needs a free **Groq** API key (takes ~2 minutes):
1. Go to **https://console.groq.com** and sign up / log in (it's free).
2. Open **API Keys** → **Create API Key** → copy the key it shows you
   (it starts with `gsk_...`).
3. In Anki: **Tools → Add-ons**, click **Anki AI Assistant**, then click
   **Config**.
4. Paste your key between the quotes after `"api_key":`, so it looks like
   `"api_key": "gsk_your_key_here"`. Click **OK**.
5. Restart Anki. Press **Ctrl+Shift+A** while reviewing to open the AI sidebar.
- **Keep your key private** — don't share it.

### 💬 socrates_bar — send card text to ChatGPT
- **Needs another add-on first:** the **“Add Dialog Web Browser”** add-on (from
  AnkiWeb) so ChatGPT can show inside Anki.
- **How to use:** When editing a card, use the bottom bar's **→ Socrates**
  button and the **A–E** buttons.

### 🌐 deck_sidebar — open web links inside Anki
- **Needs another add-on first:** the **“Add Dialog Web Browser”** add-on (from
  AnkiWeb).
- **How to use:** Press **Ctrl+Shift+B** to open the side browser, or click a
  web link in a card and it opens in the sidebar.

### 📉 daily_cap — cap how many cards you get per day
- **Setup:** **Tools → Cap Daily Cards…**, choose your maximum, click **Apply**.
- It then keeps each day under that limit automatically (extra cards move to
  future days).

### ✅ due_decks_filter — hide decks with nothing due
- **Setup:** none.
- **How to use:** On the Decks screen, click the **“Due Only”** button
  (top-right) to hide decks that have 0 cards due.

### 🎨 comet_theme — a custom look for Anki
- **Setup:** **Tools → Comet Theme Settings** to adjust colours; it applies
  automatically.

### 🖼️ anki_theme_switcher — themes + daily backgrounds
- **Works best with** the **“Custom Background”** add-on by AnKing (from
  AnkiWeb), which it uses to rotate a background image each day.

### 🪟 custom_icon — use your own Anki icon (Windows) — needs a quick edit
1. Put your icon file (a `.ico` file) somewhere on your computer.
2. In Anki: **Tools → Add-ons → Custom Icon → View Files**, open `__init__.py`
   in Notepad.
3. Change the line `ICON_PATH = r"C:\path\to\your\icon.ico"` to your icon's real
   location, then save and restart Anki.

### 🚀 ronnbrowser_launcher — launch a desktop app from Anki (advanced)
- This launches a specific program on your computer, so it only works if you
  have that program. Edit the two paths at the top of its `__init__.py` (same
  way as Custom Icon above). Most users can skip it.

---

# Add-on reference

| Folder | What it does |
| --- | --- |
| `chatgpt_paste` | Paste ChatGPT notes and have Markdown/LaTeX render automatically — equations become MathJax, tables/lists/arrows/code become HTML, images kept. Also repairs older notes with un-rendered LaTeX on startup. |
| `editor_field_search` | A “find in fields” box for the editor (toolbar icon / Ctrl+F): live match count, ▲/▼ navigation, time-of-day highlight colour. Never edits note content. |
| `focus_music_pomodoro` | Focus-music player + a **multi-phase** Pomodoro cycle with per-phase notifications and a jump-to-phase menu. *Modified from the [Focus Music & Pomodoro Player](https://ankiweb.net/shared/info/1540641384) AnkiWeb add-on — see [`focus_music_pomodoro/CREDITS.md`](focus_music_pomodoro/CREDITS.md).* |
| `anki_ai_assistant` | Groq-powered AI sidebar (explain/define/quiz/TTS/web-search, add replies as cards). **Set your own API key** in Config. |
| `socrates_bar` | Editor bottom bar that sends card text to an embedded ChatGPT page + A–E answer buttons. |
| `deck_sidebar` | Dockable in-app browser sidebar; card links open here (Ctrl+Shift+B). |
| `daily_cap` | Redistributes excess reviews/learning to future days so each day stays under a chosen total. |
| `due_decks_filter` | Hides deck rows whose due counts are all zero. |
| `comet_theme` | A configurable “spatial UI” theme with a settings dialog. |
| `anki_theme_switcher` | Multiple themes with daily background/icon rotation. |
| `custom_icon` | Uses a custom window/taskbar icon on Windows (edit `ICON_PATH`). |
| `ronnbrowser_launcher` | Tools-menu item to launch a local Electron app (edit paths). |

> **Add-ons that need a companion add-on:** `socrates_bar` and `deck_sidebar`
> need the “Add Dialog Web Browser” add-on; `anki_theme_switcher` works best
> with AnKing’s “Custom Background”. Install those from AnkiWeb separately.

---

# Trouble?

- **Nothing changed?** Make sure you **fully quit and reopened** Anki.
- **An add-on shows an error on startup?** Open **Tools → Add-ons**, select it,
  toggle it off/on, or delete its folder and reinstall.
- **Which Anki do I need?** A recent version (2.1.50 or newer). Update from
  **https://apps.ankiweb.net** if unsure.

---

# Notes & license

- No API keys or personal data are included. Add-ons that need them
  (`anki_ai_assistant`) read from Anki's per-add-on config; a couple
  (`custom_icon`, `ronnbrowser_launcher`) have placeholder paths to edit.
- `meta.json` and `user_files/` are git-ignored — Anki regenerates them.
- Licensed under the [MIT License](LICENSE). `focus_music_pomodoro` is derived
  from a third-party add-on; see its [`CREDITS.md`](focus_music_pomodoro/CREDITS.md).
