# How to install these add-ons (easy, step-by-step)

No coding needed. If you can copy and paste a folder, you can do this. 🙂

---

## Part 1 — Download the add-ons (do this once)

1. Go to the repository page:
   **https://github.com/thee-sailor/ankiaddons**
2. Click the green **`< > Code`** button (top right of the file list).
3. Click **Download ZIP**.
4. Find the downloaded file (usually in your **Downloads** folder). It's called
   `ankiaddons-main.zip`.
5. **Unzip it:**
   - **Windows:** right-click the file → **Extract All…** → **Extract**.
   - **Mac:** double-click the file.
   You now have a folder called `ankiaddons-main` containing one folder per
   add-on (like `chatgpt_paste`, `editor_field_search`, and so on).

---

## Part 2 — Open Anki's add-ons folder

1. Open **Anki** on your computer.
2. In the top menu click **Tools → Add-ons**.
3. In the window that opens, click **View Files**.
   - A folder called **`addons21`** opens. This is where add-ons live.
   - *(If "View Files" is greyed out, just click any add-on in the list first,
     then click View Files — then go one level up to the `addons21` folder.)*

---

## Part 3 — Copy the add-ons in

1. Go back to the unzipped **`ankiaddons-main`** folder from Part 1.
2. Select the add-on folders you want (or all of them). Each add-on is one
   folder, e.g. `chatgpt_paste`.
3. **Copy** them (Ctrl+C on Windows, Cmd+C on Mac).
4. Go to the **`addons21`** folder you opened in Part 2 and **Paste**
   (Ctrl+V / Cmd+V).
5. **Fully close Anki and open it again.** (Not just the window — quit and
   reopen.)

That's it — the add-ons are installed. ✅

> **Tip:** To remove an add-on later, just delete its folder from `addons21`
> and restart Anki.

---

## Part 4 — Set up each add-on

Most work immediately. A few need one small step — follow the ones you
installed.

### 📋 chatgpt_paste — paste ChatGPT notes with equations & images
- **Setup:** none.
- **How to use:** In ChatGPT, click **Copy** under a reply. In an Anki card
  field, press **Ctrl+V**. Equations, tables, arrows and images appear
  formatted automatically.

### 🔍 editor_field_search — find text while editing a card
- **Setup:** none.
- **How to use:** While editing/adding a card, press **Ctrl+F** (or click the
  magnifying-glass icon in the editor toolbar). Type a word; use ▲ / ▼ to jump
  between matches.

### 🍅 focus_music_pomodoro — study timer + focus music
- **Setup (optional):** On the **Decks** screen, look at the bottom bar. Click
  the **⚙️** (gear) to set your phases (e.g. Study 20 min → break 3 min →
  break 5 min) and to pick a **music folder** from your computer.
- **How to use:** Click the tomato icon to start. It counts down and notifies
  you at each phase. Click the **phase name** to jump to any phase.

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
- **Needs another add-on first:** the **"Add Dialog Web Browser"** add-on
  (from AnkiWeb) so ChatGPT can show inside Anki.
- **How to use:** When editing a card, use the bottom bar's **→ Socrates**
  button and the **A–E** buttons.

### 🌐 deck_sidebar — open web links inside Anki
- **Needs another add-on first:** the **"Add Dialog Web Browser"** add-on
  (from AnkiWeb).
- **How to use:** Press **Ctrl+Shift+B** to open the side browser, or click a
  web link in a card and it opens in the sidebar.

### 📉 daily_cap — cap how many cards you get per day
- **Setup:** **Tools → Cap Daily Cards…**, choose your maximum, click **Apply**.
- It then keeps each day under that limit automatically (extra cards move to
  future days).

### ✅ due_decks_filter — hide decks with nothing due
- **Setup:** none.
- **How to use:** On the Decks screen, click the **"Due Only"** button
  (top-right) to hide decks that have 0 cards due.

### 🎨 comet_theme — a custom look for Anki
- **Setup:** **Tools → Comet Theme Settings** to adjust colours, then it
  applies automatically.

### 🖼️ anki_theme_switcher — themes + daily backgrounds
- **Works best with** the **"Custom Background"** add-on by AnKing (from
  AnkiWeb), which it uses to rotate a background image each day.

### 🪟 custom_icon — use your own Anki icon (Windows) — needs a quick edit
1. Put your icon file (a `.ico` file) somewhere on your computer.
2. In Anki: **Tools → Add-ons → Custom Icon → View Files**, open `__init__.py`
   in Notepad.
3. Change the line `ICON_PATH = r"C:\path\to\your\icon.ico"` to your icon's
   real location, then save and restart Anki.

### 🚀 ronnbrowser_launcher — launch a desktop app from Anki (advanced)
- This one launches a specific program on your computer, so it only works if
  you have that program. Edit the two paths at the top of its `__init__.py`
  (same way as Custom Icon above) to point at your app. Most users can skip it.

---

## Trouble?

- **Nothing changed?** Make sure you **fully quit and reopened** Anki.
- **An add-on shows an error on startup?** Open **Tools → Add-ons**, select it,
  and toggle it off/on, or delete its folder and reinstall.
- **Which Anki do I need?** A recent version (2.1.50 or newer). Update from
  **https://apps.ankiweb.net** if unsure.
