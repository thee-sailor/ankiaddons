# Anki AI Assistant — Config

| Key | Default | Description |
|-----|---------|-------------|
| `api_key` | `""` | Groq API key from [console.groq.com/keys](https://console.groq.com/keys) |
| `model` | `"llama-3.1-8b-instant"` | Text model for chat |

## Text models

The `model` key is only the *default* for short, simple questions. The add-on
automatically switches models based on workload (see "Automatic model
switching" below), so all of these may be used in a single session.

| Model | Speed | Notes |
|-------|-------|-------|
| `llama-3.1-8b-instant` | Fastest | Default, everyday questions |
| `llama-3.3-70b-versatile` | Slower | Auto-selected for Quiz mode and longer questions |
| `mixtral-8x7b-32768` | Fast | Auto-selected when conversation/card context is long (32K context) |

## Features

1. **Text-selection popup** — select any text on a card → floating Explain/Define/Translate/Simplify buttons appear
2. **Add as card** — ➕ Card button saves the AI reply as a new Anki note
3. **Deck-aware context** — deck name and note type injected into every prompt
4. **Web search** — toggle 🔍 Web ON to include DuckDuckGo text results (and, when available, a relevant image) with the next query
5. **Difficulty tagging** — ✓ Got it / 😕 Confused track performance; 📊 Review stats (menu) shows the summary
6. **Text-to-speech** — 🔊 Speak reads the last AI reply aloud (Windows), with a live waveform
7. **Explain** — one-tap clinical explanation of the current card
8. **Quiz** — 🎯 Quiz starts an interactive 5-option (A–E) multiple-choice quiz on the current card. Questions come one at a time; missed questions are re-asked after 3 more questions; each answer gets an explanation of every option. Keep answering in the chat box to continue the quiz.
9. **Chat history** — 🕘 in the header opens a slide-in drawer of past chat threads. Every conversation is saved automatically (to `user_files/sessions.json`, preserved across add-on updates) — starting a new card, hitting **+ New session**, or switching threads all archive the current one first. Click a thread to reload its transcript and keep chatting; ✕ deletes one. Continuing an old thread uses the *current* card as context for new questions — the already-shown messages don't change.
10. **Automatic model switching** — each reply picks a Groq model based on workload: the fast 8B model for short questions, the 70B model for Quiz mode or longer questions, and the 32K-context Mixtral model when the conversation/card context is long. If a rate limit or model error occurs before any tokens have streamed, it retries once with a different model automatically. The model used is shown as a small badge next to each reply.
