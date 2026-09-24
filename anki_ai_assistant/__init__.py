"""
Anki AI Assistant — Groq sidebar
Functional features:
  1. Text-selection popup       6. Text-to-speech
  2. Add reply as card          7. Explain
  3. Deck-aware context         8. Quiz mode (interactive penta-choice quiz)
  4. Difficulty tagging         9. Persistent chat history (History drawer)
  5. Web search (DuckDuckGo)   10. Automatic model switching by workload
     text + image results

Visual features implemented in sidebar.html:
  1. Status orb (spinning conic-gradient during inference)
  2. Glassmorphism chat bubbles
  3. Token streaming (Groq stream=True, char-by-char render)
  4. Card info chip in header
  5. Semantic colour lanes per AI-response section
  6. Live waveform canvas during TTS
  7. Holographic shimmer on buttons
  8. Reactive particle background (accelerates during inference)
  9. Slide-in History drawer for past chat sessions
"""

from __future__ import annotations
import base64
import collections
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import uuid

from aqt import mw, gui_hooks
from aqt.qt import (
    QDockWidget, Qt, QAction, QKeySequence, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSizePolicy,
    QShortcut, QTextEdit, QDialogButtonBox, QFrame, QUrl,
)
from aqt.utils import tooltip, showWarning

# QWebEngineView / QWebEnginePage — available in any Anki build that ships QtWebEngine
try:
    from aqt.qt import QWebEngineView, QWebEnginePage  # type: ignore[attr-defined]
except ImportError:
    from PyQt6.QtWebEngineWidgets import QWebEngineView    # type: ignore[no-redef]
    from PyQt6.QtWebEngineCore import QWebEnginePage       # type: ignore[no-redef]

# ── Groq SDK auto-install ──────────────────────────────────────────────────────

_HAS_GROQ = False


def _try_pip_install(package: str) -> bool:
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", package],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def _load_groq():
    global _HAS_GROQ
    try:
        import groq  # noqa: F401
        _HAS_GROQ = True
        return
    except ImportError:
        pass
    if _try_pip_install("groq"):
        try:
            import groq  # noqa: F401
            _HAS_GROQ = True
        except ImportError:
            pass


_load_groq()

# ── Session state ──────────────────────────────────────────────────────────────

_session: dict = {
    "struggles": collections.deque(maxlen=10), # {"front": str, "back": str}
    "got_it":   0,
    "confused": 0,
}

# ── Prompts ────────────────────────────────────────────────────────────────────

SYSTEM_BASE = (
    "You are a concise medical-study AI assistant embedded in Anki. "
    "The user is a medical student. When given a flashcard, help them understand it "
    "deeply with clinical context. Be brief and structured — use bullet points, "
    "bold key terms, numbered steps where helpful. "
    "Never exceed ~200 words unless explicitly asked for more."
)

DEFAULT_MODEL = "llama-3.1-8b-instant"

# ── Model selection (feature: automatic switch by workload / token limits) ─────

MODEL_FAST    = "llama-3.1-8b-instant"       # short, everyday questions
MODEL_STRONG  = "llama-3.3-70b-versatile"    # quiz grading / longer reasoning
MODEL_LONGCTX = "mixtral-8x7b-32768"         # long card context / long history

# Rough chars-per-token estimate; good enough for a routing heuristic.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(messages: list[dict]) -> int:
    return sum(len(m.get("content", "")) for m in messages) // _CHARS_PER_TOKEN


def _select_model(cfg: dict, messages: list[dict], quiz_mode: bool) -> str:
    approx = _estimate_tokens(messages)
    if approx > 6000:
        return MODEL_LONGCTX
    if quiz_mode or approx > 1200:
        return MODEL_STRONG
    return cfg.get("model", DEFAULT_MODEL)


def _fallback_chain(primary: str) -> list[str]:
    """Ordered candidates to retry on rate-limit / model errors, primary first."""
    order = [primary, MODEL_STRONG, MODEL_LONGCTX, MODEL_FAST]
    chain: list[str] = []
    for m in order:
        if m not in chain:
            chain.append(m)
    return chain


# ── Web search (DuckDuckGo, no API key) ───────────────────────────────────────

def _ddg_abs_url(u: str) -> str:
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return "https://duckduckgo.com" + u
    return u


def _web_search_text(query: str) -> str:
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query + " medical")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            body = r.read().decode("utf-8", errors="ignore")
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', body, re.DOTALL)
        clean = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets[:3] if s.strip()]
        return "\n".join(f"• {s}" for s in clean)
    except Exception:
        return ""


def _web_search_images(query: str) -> list[str]:
    try:
        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
            "q": query, "format": "json", "no_html": "1", "skip_disambig": "1",
        })
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception:
        return []

    images: list[str] = []
    img = data.get("Image") or ""
    if img:
        images.append(_ddg_abs_url(img))
    for topic in data.get("RelatedTopics", [])[:5]:
        icon = (topic.get("Icon") or {}).get("URL")
        if icon:
            abs_icon = _ddg_abs_url(icon)
            if abs_icon not in images:
                images.append(abs_icon)
        if len(images) >= 2:
            break
    return images[:2]


def _web_search(query: str) -> tuple[str, list[str]]:
    """Returns (text snippets, image URLs) — both best-effort, no API key required."""
    return _web_search_text(query), _web_search_images(query)

# ── TTS (Windows Speech API via PowerShell) ───────────────────────────────────

_speech_proc: subprocess.Popen | None = None


def _speak(text: str) -> None:
    global _speech_proc
    clean = re.sub(r'[\"\'<>&]', " ", _strip_html(text))[:600]
    _stop_speaking()  # only one utterance plays at a time
    _speech_proc = subprocess.Popen(
        ["powershell", "-WindowStyle", "Hidden", "-Command",
         "Add-Type -AssemblyName System.Speech; "
         "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
         f'$s.Speak("{clean}")'],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _stop_speaking() -> None:
    global _speech_proc
    if _speech_proc is not None:
        try:
            if _speech_proc.poll() is None:
                _speech_proc.kill()
        except Exception:
            pass
        _speech_proc = None

# ── Image extraction ───────────────────────────────────────────────────────────

def _extract_images(card_html: str) -> list[tuple[str, str]]:
    if not mw or not mw.col:
        return []
    media_dir = mw.col.media.dir()
    results = []
    for src in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', card_html, re.IGNORECASE):
        path = os.path.join(media_dir, src)
        if os.path.isfile(path):
            try:
                with open(path, "rb") as f:
                    data = f.read()
                ext  = os.path.splitext(src)[1].lower().lstrip(".")
                mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
                        "gif": "gif", "webp": "webp"}.get(ext, "jpeg")
                results.append((f"data:image/{mime};base64,{base64.b64encode(data).decode()}", src))
            except Exception:
                pass
        if len(results) >= 2:
            break
    return results

# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_html(s: str) -> str:
    s = re.sub(r"<script[^>]*>.*?</script>", " ", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<style[^>]*>.*?</style>",   " ", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _relative_time(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        then = datetime.datetime.fromisoformat(iso_str)
        secs = (datetime.datetime.now() - then).total_seconds()
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{int(secs // 60)}m ago"
        if secs < 86400:
            return f"{int(secs // 3600)}h ago"
        if secs < 86400 * 7:
            return f"{int(secs // 86400)}d ago"
        return then.strftime("%b %d")
    except Exception:
        return ""


def _make_title(history: list[dict]) -> str:
    for turn in history:
        if turn.get("role") == "user":
            title = _strip_html(turn.get("content", ""))[:60].strip()
            if title:
                return title
    return "Untitled"


def _user_files_dir() -> str:
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_files")
    os.makedirs(d, exist_ok=True)
    return d


def _sessions_path() -> str:
    return os.path.join(_user_files_dir(), "sessions.json")


def _load_sessions() -> list[dict]:
    path = _sessions_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_sessions(sessions: list[dict]) -> None:
    path = _sessions_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass


def _friendly_error(raw: str) -> str:
    if "401" in raw or "invalid_api_key" in raw.lower() or "authentication" in raw.lower():
        return "Invalid API key (401).\nCheck console.groq.com → API Keys and update Config."
    if "429" in raw or "rate_limit" in raw.lower():
        return "Rate limit hit (429).\nFree tier: 14,400 req/day, 30/min.\nWait a moment and retry."
    if "404" in raw or "model_not_found" in raw.lower():
        return ("Model not found (404).\nValid models:\n"
                "  llama-3.1-8b-instant\n  llama-3.3-70b-versatile\n"
                "  gemma2-9b-it\n  mixtral-8x7b-32768")
    return raw[:400]

# ── JS injected into reviewer for text-selection popup ─────────────────────────

_SELECTION_JS = r"""
(function(){
  if(window._ankiAIPopupReady) return;
  window._ankiAIPopupReady = true;

  var pop = document.createElement('div');
  pop.style.cssText = [
    'position:fixed;display:none;flex-direction:row;gap:4px;padding:5px 7px;',
    'background:#1a1a2e;border:1px solid #f97316;border-radius:8px;',
    'box-shadow:0 4px 20px rgba(0,0,0,.65);z-index:99999;'
  ].join('');
  document.body.appendChild(pop);

  var bs = 'background:#ea580c;color:#fff;border:none;border-radius:5px;' +
           'padding:3px 9px;font-size:11px;font-weight:700;cursor:pointer;';

  [['Explain','explain'],['Define','define'],['Translate','translate'],['Simplify','simplify']
  ].forEach(function(pair){
    var b = document.createElement('button');
    b.textContent = pair[0]; b.style.cssText = bs;
    b.onmousedown = function(e){ e.preventDefault(); };
    b.onclick = function(e){
      e.stopPropagation();
      var sel = window.__aiSelText || '';
      if(sel) pycmd('ai_sel:' + pair[1] + ':' + encodeURIComponent(sel));
      pop.style.display = 'none';
    };
    pop.appendChild(b);
  });

  document.addEventListener('mouseup', function(e){
    if(pop.contains(e.target)) return;
    setTimeout(function(){
      var sel = (window.getSelection()||{toString:function(){return '';}}).toString().trim();
      if(sel.length > 2){
        window.__aiSelText = sel;
        var x = Math.min(e.clientX, window.innerWidth - 240);
        var y = e.clientY + 14;
        pop.style.left = x + 'px';
        pop.style.top  = y + 'px';
        pop.style.display = 'flex';
      } else { pop.style.display = 'none'; }
    }, 10);
  });

  document.addEventListener('mousedown', function(e){
    if(!pop.contains(e.target)) pop.style.display = 'none';
  });
})();
"""

# ── Add-as-Card dialog ─────────────────────────────────────────────────────────

class _AddCardDialog(QDialog):
    def __init__(self, front: str, back: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add AI Response as Card")
        self.setMinimumWidth(420)
        self.setStyleSheet("background:#0f0f17; color:#e2e8f0;")
        lay = QVBoxLayout(self)

        for label_text, attr, txt, h in [
            ("Front:", "_front", front[:300], 70),
            ("Back (AI response):", "_back", back[:2000], 180),
        ]:
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color:#9ca3af; font-size:11px;")
            lay.addWidget(lbl)
            te = QTextEdit()
            te.setPlainText(txt)
            te.setFixedHeight(h)
            te.setStyleSheet(
                "background:#1a1a2e; color:#e2e8f0; border:1px solid rgba(255,255,255,0.1);"
                "border-radius:6px; padding:4px; font-size:12px;"
            )
            lay.addWidget(te)
            setattr(self, attr, te)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _save(self):
        front = self._front.toPlainText().strip()
        back  = self._back.toPlainText().strip()
        if not front or not back:
            return
        try:
            models   = mw.col.models
            notetype = models.by_name("Basic") or models.all()[0]
            note     = mw.col.new_note(notetype)
            fields   = list(note.keys())
            note[fields[0]] = front
            if len(fields) >= 2:
                note[fields[1]] = back
            mw.col.add_note(note, mw.col.decks.selected())
            mw.col.save()
            tooltip("Card added!", period=2000)
            self.accept()
        except Exception as e:
            showWarning(f"Could not add card:\n{e}")

# ── Session summary dialog ─────────────────────────────────────────────────────

class _SessionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Stats")
        self.setMinimumWidth(360)
        self.setStyleSheet("background:#0f0f17; color:#e2e8f0;")
        lay = QVBoxLayout(self)

        total  = _session["got_it"] + _session["confused"]
        header = QLabel(f"Cards this session: {total}")
        header.setStyleSheet("font-size:14px; font-weight:bold; color:#f97316;")
        lay.addWidget(header)

        stats = QLabel(f"✓ Got it: {_session['got_it']}     😕 Confused: {_session['confused']}")
        stats.setStyleSheet("font-size:12px; color:#9ca3af; margin-top:4px;")
        lay.addWidget(stats)

        if _session["struggles"]:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: rgba(255,255,255,0.1);")
            lay.addWidget(sep)
            lbl = QLabel("Topics to review again:")
            lbl.setStyleSheet("font-size:11px; color:#6b7280; margin-top:6px;")
            lay.addWidget(lbl)
            for s in _session["struggles"]:
                item = QLabel(f"  • {s['front'][:80]}")
                item.setStyleSheet("color:#fca5a5; font-size:11px;")
                item.setWordWrap(True)
                lay.addWidget(item)

        close = QPushButton("Close")
        close.setStyleSheet(
            "background:#ea580c; color:white; border:none; border-radius:6px;"
            "padding:6px 20px; font-weight:700; margin-top:10px;"
        )
        close.clicked.connect(self.accept)
        lay.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)

# ── WebEngine page — intercepts JS bridge calls via console.log ────────────────

class _SidebarPage(QWebEnginePage):
    def __init__(self, view: "_AIView", parent=None):
        super().__init__(parent)
        self._view = view

    def javaScriptConsoleMessage(self, level, msg, line, source):
        if msg.startswith("__ANKIAI__:"):
            try:
                _, action, data_json = msg.split(":", 2)
                data = json.loads(data_json)
                self._view._on_bridge(action, data)
            except Exception as exc:
                print(f"[AI Sidebar] bridge parse error: {exc}")

# ── Main view (QWebEngineView hosting sidebar.html) ───────────────────────────

class _AIView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = _SidebarPage(self, self)
        self.setPage(self._page)

        self._history:      list[dict]            = []
        self._card_context  = ""
        self._card_images:  list[tuple[str, str]] = []
        self._deck_name     = ""
        self._note_type     = ""
        self._last_reply    = ""
        self._init_session_fields()

        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sidebar.html")
        self.load(QUrl.fromLocalFile(html_path))

    # ── JS bridge ─────────────────────────────────────────────────────────────

    def js(self, code: str):
        """Run JavaScript on the main thread."""
        self.page().runJavaScript(code)

    def _on_bridge(self, action: str, data: dict):
        """Handle all JS → Python calls."""
        if action == "chat":
            if data.get("quiz"):
                self._quiz_mode = True
            self._do_chat(data.get("text", ""), data.get("webOn", False))
        elif action == "speak":
            text = data.get("text", "")
            if text:
                threading.Thread(target=_speak, args=(text,), daemon=True).start()
        elif action == "stopSpeak":
            _stop_speaking()
        elif action == "gotit":
            _session["got_it"] += 1
        elif action == "confused":
            _session["confused"] += 1
            front = _strip_html(
                self._card_context.split("\n")[0]
                .replace("[Front]: ", "").replace("[Front (question)]: ", "")
            )[:80]
            _session["struggles"].append({"front": front, "back": self._card_context})
        elif action == "addCard":
            reply = data.get("reply", "")
            ctx   = data.get("ctx",   "")
            mw.taskman.run_on_main(lambda: self._show_add_card(ctx, reply))
        elif action == "showSession":
            mw.taskman.run_on_main(lambda: _SessionDialog(parent=mw).exec())
        elif action == "newSession":
            self._reset_session()
            self.js("resetChatUI()")
        elif action == "listSessions":
            self.js(f"renderSessions({json.dumps(self._session_summaries())})")
        elif action == "loadSession":
            self._load_session(data.get("id", ""))
        elif action == "deleteSession":
            self._delete_session(data.get("id", ""))

    # ── Chat history / sessions (feature: persistent memory across sessions) ───

    def _init_session_fields(self):
        self._session_id: str            = str(uuid.uuid4())
        self._session_title: str         = ""
        self._session_created: str | None = None
        self._quiz_mode: bool            = False

    def _persist_current_session(self):
        if not self._history:
            return
        now = _now_iso()
        if not self._session_created:
            self._session_created = now
        if not self._session_title:
            self._session_title = _make_title(self._history)
        sessions = [s for s in _load_sessions() if s.get("id") != self._session_id]
        sessions.append({
            "id":         self._session_id,
            "title":      self._session_title,
            "deck":       self._deck_name,
            "created":    self._session_created,
            "updated":    now,
            "quiz_mode":  self._quiz_mode,
            "history":    self._history,
        })
        sessions.sort(key=lambda s: s.get("updated", ""), reverse=True)
        _save_sessions(sessions[:100])

    def _reset_session(self):
        self._persist_current_session()
        self._history = []
        self._last_reply = ""
        self._init_session_fields()

    def _session_summaries(self) -> list[dict]:
        return [
            {
                "id":    s.get("id"),
                "title": s.get("title", "Untitled"),
                "deck":  s.get("deck", ""),
                "when":  _relative_time(s.get("updated", "")),
            }
            for s in _load_sessions()
        ]

    def _load_session(self, session_id: str):
        if not session_id:
            return
        for s in _load_sessions():
            if s.get("id") != session_id:
                continue
            self._history         = list(s.get("history", []))
            self._session_id      = s.get("id")
            self._session_title   = s.get("title", "")
            self._session_created = s.get("created")
            self._quiz_mode       = bool(s.get("quiz_mode", False))
            self._last_reply      = ""
            for turn in reversed(self._history):
                if turn.get("role") == "assistant":
                    self._last_reply = turn.get("content", "")
                    break
            payload = {"id": self._session_id, "deck": s.get("deck", ""), "turns": self._history}
            self.js(f"renderHistory({json.dumps(payload)})")
            return

    def _delete_session(self, session_id: str):
        if not session_id:
            return
        sessions = [s for s in _load_sessions() if s.get("id") != session_id]
        _save_sessions(sessions)
        if session_id == self._session_id:
            self._history = []
            self._last_reply = ""
            self._init_session_fields()
            self.js("resetChatUI()")
        self.js(f"renderSessions({json.dumps(self._session_summaries())})")

    # ── Card loading ───────────────────────────────────────────────────────────

    def load_card(self, front_html: str, back_html: str = "", card=None):
        _stop_speaking()
        self._reset_session()
        front_plain = _strip_html(front_html)[:400]
        back_plain  = _strip_html(back_html)[:400] if back_html else ""

        self._card_context = (
            f"[Front]: {front_plain}\n[Back]: {back_plain}"
            if back_plain else f"[Front (question)]: {front_plain}"
        )
        self._card_images = _extract_images(front_html + back_html)

        if card:
            try: self._deck_name = mw.col.decks.name(card.did)
            except: self._deck_name = ""
            try: self._note_type = card.note_type()["name"]
            except: self._note_type = ""
        else:
            self._deck_name = self._note_type = ""

        meta = []
        if self._note_type:   meta.append(self._note_type)
        if self._card_images: meta.append(f"{len(self._card_images)} image(s)")

        card_data = {
            "front":    front_plain[:100],
            "back":     back_plain[:60],
            "deck":     self._deck_name,
            "hasImage": bool(self._card_images),
            "meta":     " · ".join(meta),
        }
        self.js(f"loadCard({json.dumps(card_data)})")

    # ── Streaming chat (Feature 3) ─────────────────────────────────────────────

    def _do_chat(self, user_text: str, web_on: bool):
        cfg     = mw.addonManager.getConfig(__name__) or {}
        api_key = cfg.get("api_key", "").strip()

        if not api_key:
            self.js("onError('No API key — Tools → Add-ons → Anki AI Assistant → Config')")
            return
        if not _HAS_GROQ:
            self.js("onError('Groq SDK missing. Restart Anki after: pip install groq')")
            return

        # Build message list with card context as first exchange
        messages = list(self._history)
        if not messages:
            messages = [
                {"role": "user",      "content": self._card_context},
                {"role": "assistant", "content": "Ready."},
            ]
        messages.append({"role": "user", "content": user_text})
        self._history.append({"role": "user", "content": user_text})

        system    = self._build_system()
        quiz_mode = self._quiz_mode

        def _worker():
            try:
                augmented = user_text
                if web_on:
                    snippet_text, image_urls = _web_search(user_text)
                    if snippet_text:
                        augmented = f"[Web results:\n{snippet_text}]\n\nQuestion: {user_text}"
                    if image_urls:
                        img_lines = "\n".join(f"- {u}" for u in image_urls)
                        augmented += (
                            "\n\nRelevant images found (cite at most one, inline, using "
                            f"markdown ![short label](url) if it helps your answer):\n{img_lines}"
                        )

                send_msgs = messages[:-1] + [{"role": "user", "content": augmented}]
                formatted = [{"role": "system", "content": system}]
                for m in send_msgs:
                    role = "assistant" if m["role"] in ("model", "assistant") else "user"
                    formatted.append({"role": role, "content": m["content"]})

                from groq import Groq
                client = Groq(api_key=api_key)

                chosen   = _select_model(cfg, formatted, quiz_mode)
                chain    = _fallback_chain(chosen)
                max_toks = 900 if quiz_mode else 600

                full_text  = ""
                used_model = chosen
                last_err: Exception | None = None

                for m in chain:
                    full_text = ""
                    used_model = m
                    try:
                        stream = client.chat.completions.create(
                            model=m, messages=formatted, max_tokens=max_toks, stream=True
                        )
                        for chunk in stream:
                            delta = chunk.choices[0].delta.content or ""
                            if delta:
                                full_text += delta
                                tj = json.dumps(delta)
                                mw.taskman.run_on_main(lambda t=tj: self.js(f"appendToken({t})"))
                        last_err = None
                        break
                    except Exception as e:
                        last_err = e
                        if full_text:
                            # Already streamed partial content — don't silently
                            # switch models mid-answer, surface the error instead.
                            break
                        continue  # nothing streamed yet: safe to retry with next model

                if last_err is not None:
                    err = _friendly_error(str(last_err))
                    mw.taskman.run_on_main(lambda ej=json.dumps(err): self.js(f"onError({ej})"))
                    return

                mw.taskman.run_on_main(
                    lambda ft=full_text, um=used_model: self._on_stream_done(ft, um)
                )

            except Exception as e:
                err = _friendly_error(str(e))
                mw.taskman.run_on_main(lambda ej=json.dumps(err): self.js(f"onError({ej})"))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stream_done(self, text: str, model: str):
        self._history.append({"role": "assistant", "content": text})
        self._last_reply = text
        self._persist_current_session()
        self.js(f"finalizeStream({json.dumps({'text': text, 'model': model})})")

    def _build_system(self) -> str:
        parts = [SYSTEM_BASE]
        if self._deck_name:
            parts.append(f"Current deck: '{self._deck_name}'. Note type: '{self._note_type}'.")
        struggles = list(_session["struggles"])
        if struggles:
            topics = "; ".join(s["front"][:40] for s in struggles[-3:])
            parts.append(f"Earlier this session the student was confused about: {topics}.")
        return " ".join(parts)

    # ── Add-as-card ────────────────────────────────────────────────────────────

    def _show_add_card(self, ctx: str, reply: str):
        front = _strip_html(
            ctx.split("\n")[0]
            .replace("[Front]: ", "").replace("[Front (question)]: ", "")
        )[:200]
        _AddCardDialog(front=front, back=reply, parent=self).exec()

# ── pycmd handler: text-selection popup ───────────────────────────────────────

_SEL_PROMPTS = {
    "explain":   'Explain this term/phrase clearly with clinical context: "{text}"',
    "define":    'Define "{text}" concisely in a medical context.',
    "translate": 'Translate "{text}" into simple language a patient or first-year student could understand.',
    "simplify":  'Simplify "{text}" — explain it as if seeing it for the first time.',
}


def _on_js_message(handled: tuple, message: str, context) -> tuple:
    if not message.startswith("ai_sel:"):
        return handled
    try:
        _, action, encoded = message.split(":", 2)
        text     = urllib.parse.unquote(encoded).strip()[:300]
        template = _SEL_PROMPTS.get(action, 'Help me understand: "{text}"')
        prompt   = template.format(text=text)
        if _view:
            _view.js(f"doSend({json.dumps(prompt)})")
            _show()
    except Exception:
        pass
    return (True, None)


gui_hooks.webview_did_receive_js_message.append(_on_js_message)

# ── Inject selection JS into reviewer ─────────────────────────────────────────

def _inject_js():
    try:
        if mw.reviewer and mw.reviewer.web:
            mw.reviewer.web.eval(_SELECTION_JS)
    except Exception:
        pass

# ── Dock ───────────────────────────────────────────────────────────────────────

_dock:   "QDockWidget | None" = None
_view:   "_AIView | None"     = None
_hiding_programmatically      = False
_user_wants_open              = False

DOCK_STYLE = """
QDockWidget { background:#060a12; }
QDockWidget::title {
    background:#0d1420; border-bottom:1px solid rgba(0,212,255,0.12);
    padding:0px; font-size:0px;
}
QDockWidget::close-button,QDockWidget::float-button {
    background:transparent; border:none; padding:2px;
}
QDockWidget::close-button:hover,QDockWidget::float-button:hover {
    background:rgba(255,255,255,0.08); border-radius:4px;
}
"""


def _create_dock():
    global _dock, _view
    if _dock is not None:
        return
    _view = _AIView(parent=mw)
    _dock = QDockWidget("AI", mw)
    _dock.setObjectName("AnkiAIAssistant")
    _dock.setStyleSheet(DOCK_STYLE)
    _dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable   |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable
    )
    _dock.setAllowedAreas(
        Qt.DockWidgetArea.LeftDockWidgetArea  |
        Qt.DockWidgetArea.RightDockWidgetArea
    )
    _dock.setWidget(_view)
    _dock.setMinimumWidth(310)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, _dock)
    _dock.visibilityChanged.connect(_on_visibility_changed)
    _dock.hide()


def _on_visibility_changed(visible: bool):
    global _user_wants_open
    if not visible and not _hiding_programmatically:
        _user_wants_open = False


def _show():
    global _user_wants_open
    if _dock is None:
        return
    _user_wants_open = True
    _dock.show(); _dock.raise_()


def _hide_programmatic():
    global _hiding_programmatically
    if _dock is None:
        return
    _hiding_programmatically = True
    _dock.hide()
    _hiding_programmatically = False


def _toggle():
    if _dock is None:
        tooltip("AI Assistant dock not ready.", period=2000)
        return
    if _dock.isVisible():
        global _user_wants_open
        _user_wants_open = False
        _hide_programmatic()
    else:
        _show()

# ── Hooks ──────────────────────────────────────────────────────────────────────

def _on_state_changed(new_state: str, _old: str):
    if _dock is None:
        return
    if new_state == "review":
        if _user_wants_open:
            _dock.show(); _dock.raise_()
    else:
        _hide_programmatic()


def _on_card_shown(card):
    if _view is None:
        return
    try:
        _view.load_card(card.question(), card=card)
        _inject_js()
    except Exception:
        pass


def _on_answer_shown(card):
    if _view is None:
        return
    try:
        _view.load_card(card.question(), card.answer(), card=card)
        _inject_js()
    except Exception:
        pass


def _on_toolbar_init(links: list, toolbar):
    links.append(toolbar.create_link(
        cmd="ai-assistant-toggle",
        label="AI",
        func=lambda: _toggle(),
        tip="Toggle AI Assistant (Ctrl+Shift+A)",
        id="ai-assistant-btn",
    ))


def _setup():
    _create_dock()
    action = QAction("AI Assistant", mw)
    action.setShortcut(QKeySequence("Ctrl+Shift+A"))
    action.setCheckable(True)
    action.triggered.connect(_toggle)
    mw.form.menuTools.addAction(action)
    if _dock:
        _dock.visibilityChanged.connect(action.setChecked)
    sc = QShortcut(QKeySequence("Ctrl+Shift+A"), mw)
    sc.activated.connect(_toggle)
    gui_hooks.state_did_change.append(_on_state_changed)
    gui_hooks.reviewer_did_show_question.append(_on_card_shown)
    gui_hooks.reviewer_did_show_answer.append(_on_answer_shown)


gui_hooks.main_window_did_init.append(_setup)
gui_hooks.top_toolbar_did_init_links.append(_on_toolbar_init)
