# Anki Addons

A collection of custom [Anki](https://apps.ankiweb.net/) add-ons for a
medical-study workflow. Each folder is a standalone add-on.

## Installing

Copy any add-on folder into your Anki add-ons directory and restart Anki:

- **Windows:** `%APPDATA%\Anki2\addons21\`
- **macOS:** `~/Library/Application Support/Anki2/addons21/`
- **Linux:** `~/.local/share/Anki2/addons21/`

(In Anki: **Tools → Add-ons → View Files** opens this folder.)

Most add-ons target Anki 2.1.50+ (Qt6).

## Add-ons

| Folder | What it does |
| --- | --- |
| `chatgpt_paste` | Paste notes copied from ChatGPT and have Markdown/LaTeX render automatically — equations become Anki MathJax, tables/lists/arrows/code become HTML, images are kept. Also repairs older notes with un-rendered LaTeX on startup. |
| `editor_field_search` | A "find in fields" box for the editor (toolbar icon / Ctrl+F): live match count, ▲/▼ navigation, and time-of-day highlight colour. Never modifies note content (uses the CSS Custom Highlight API). |
| `focus_music_pomodoro` | Focus-music player plus a **multi-phase** Pomodoro cycle (e.g. Study → Genuine break → Value-added break → …), configurable phases, notifications between each, and a dropdown to jump to any phase. *Modified from the [Focus Music & Pomodoro Player](https://ankiweb.net/shared/info/1540641384) AnkiWeb add-on — see [`focus_music_pomodoro/CREDITS.md`](focus_music_pomodoro/CREDITS.md).* |
| `anki_ai_assistant` | A Groq-powered AI sidebar (explain/define/quiz/TTS/web-search, add replies as cards). **Set your own API key** in the add-on config. |
| `socrates_bar` | Editor bottom bar that sends card text to an embedded ChatGPT page and answer-choice buttons (A–E). Works with the embedded browser add-on. |
| `deck_sidebar` | Dockable in-app browser sidebar; http links in cards open here instead of an external browser (Ctrl+Shift+B). |
| `daily_cap` | Redistributes excess reviews/learning to future days so each day stays under a chosen total; runs on startup. |
| `due_decks_filter` | Hides deck rows whose due counts are all zero; toggle from the deck browser. |
| `comet_theme` | A configurable "spatial UI" theme with a settings dialog. |
| `anki_theme_switcher` | Multiple themes with daily background/icon rotation. |
| `custom_icon` | Uses a custom window/taskbar icon on Windows. **Edit `ICON_PATH`** to your own `.ico`. |
| `ronnbrowser_launcher` | Adds a Tools-menu item to launch a local Electron app. **Edit the paths** to your app. |

## Notes

- No API keys or personal data are included. Add-ons that need them
  (`anki_ai_assistant`) read from Anki's per-add-on config, and a few
  (`custom_icon`, `ronnbrowser_launcher`) have placeholder paths to edit.
- `meta.json` and `user_files/` are intentionally git-ignored — Anki
  regenerates them per install.
