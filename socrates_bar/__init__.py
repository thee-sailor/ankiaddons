"""
Socrates Bar — bottom bar in the Anki card editor:
  • "→ Socrates" : sends card text to the embedded Socrates browser (add-on 918010938)
  • A B C D E   : sends that letter to the current ChatGPT chat in that browser
Injects JavaScript directly into the QWebEngineView — no Windows API needed.
"""

import html
import re

from aqt import gui_hooks
from aqt.editor import Editor
from aqt.qt import (
    QApplication, QFrame, QHBoxLayout, QPushButton, QTimer, QWebEngineView
)
from aqt.utils import showWarning

SOCRATES_URL = "https://chatgpt.com/g/g-p-6a22d7629e948191a704fefa9bd92329-socrates/project"


# ── Find the embedded browser webview ────────────────────────

def _find_socrates_webview():
    """Return the QWebEngineView from add-on 918010938 that shows ChatGPT."""
    for widget in QApplication.allWidgets():
        if isinstance(widget, QWebEngineView) and widget.isVisible():
            url = widget.url().toString().lower()
            if 'chatgpt' in url or 'socrates' in url or 'openai' in url:
                return widget
    return None

def _find_any_browser_webview():
    """Fallback: return any visible QWebEngineView that isn't Anki's own UI."""
    candidates = []
    for widget in QApplication.allWidgets():
        if isinstance(widget, QWebEngineView) and widget.isVisible():
            url = widget.url().toString()
            # Skip Anki's internal pages
            if url.startswith('http://127.0.0.1') or url in ('', 'about:blank'):
                continue
            candidates.append(widget)
    return candidates[0] if candidates else None


# ── JavaScript injection into ChatGPT ─────────────────────────

_JS_SEND = """
(function(text) {
    // ChatGPT uses a contenteditable div with id="prompt-textarea"
    var el = document.getElementById('prompt-textarea')
           || document.querySelector('[contenteditable="true"][data-virtualkeyboardpolicy]')
           || document.querySelector('div[contenteditable="true"]');

    if (!el) { return 'NO_INPUT'; }

    el.focus();

    // Clear existing content then insert new text
    el.innerHTML = '';
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, text);

    // Trigger React's synthetic input event so the Send button activates
    el.dispatchEvent(new InputEvent('input', { bubbles: true, data: text }));

    // Click Send after a short delay
    setTimeout(function() {
        var send = document.querySelector('[data-testid="send-button"]')
                || document.querySelector('button[aria-label="Send prompt"]')
                || document.querySelector('button[aria-label*="Send"]');
        if (send && !send.disabled) { send.click(); }
    }, 300);

    return 'OK';
})(%s);
"""


def _send_to_browser(text: str):
    webview = _find_socrates_webview() or _find_any_browser_webview()
    if not webview:
        showWarning(
            "Could not find the embedded browser.\n"
            "Make sure the Web Browser add-on (918010938) is open and "
            "showing the Socrates ChatGPT page."
        )
        return

    # Escape text as a JS string literal
    js_text = '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '') + '"'
    webview.page().runJavaScript(_JS_SEND % js_text)


# ── Card text extractor ───────────────────────────────────────

def _card_text(editor: Editor) -> str:
    note = editor.note
    if not note:
        return ""
    parts = []
    for name, val in note.items():
        clean = re.sub(r'<[^>]+>', ' ', val)
        clean = html.unescape(clean).strip()
        if clean:
            parts.append(f"{name}:\n{clean}")
    return "\n\n".join(parts)


# ── Build the bar ─────────────────────────────────────────────

def _add_bar(editor: Editor):
    bar = QFrame()
    bar.setStyleSheet("""
        QFrame { background:#12121f; border-top:1px solid #2a2a4a; }
        QPushButton {
            border-radius:5px; font-weight:700; font-size:12px;
            padding:4px 0; min-height:28px; border:none; color:#fff;
        }
    """)
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(8, 4, 8, 4)
    layout.setSpacing(6)

    # → Socrates
    send_btn = QPushButton("→ Socrates")
    send_btn.setMinimumWidth(110)
    send_btn.setStyleSheet("""
        QPushButton { background:#7c3aed; }
        QPushButton:hover { background:#9f6ff5; }
        QPushButton:pressed { background:#5b21b6; }
    """)
    send_btn.clicked.connect(
        lambda: QTimer.singleShot(0, lambda: _send_to_browser(_card_text(editor)))
    )
    layout.addWidget(send_btn)
    layout.addStretch()

    # A – E
    palette = {
        'A': ('#1e40af', '#3b82f6'),
        'B': ('#065f46', '#10b981'),
        'C': ('#854d0e', '#f59e0b'),
        'D': ('#991b1b', '#ef4444'),
        'E': ('#4c1d95', '#a78bfa'),
    }
    for letter in 'ABCDE':
        bg, hover = palette[letter]
        btn = QPushButton(letter)
        btn.setFixedWidth(38)
        btn.setToolTip(f"Answer {letter}")
        btn.setStyleSheet(f"""
            QPushButton {{ background:{bg}; }}
            QPushButton:hover {{ background:{hover}; }}
        """)
        btn.clicked.connect(
            lambda checked=False, l=letter:
                QTimer.singleShot(0, lambda lt=l: _send_to_browser(lt))
        )
        layout.addWidget(btn)

    # Try to place bar inside the right browser panel after it's built
    def _place():
        placed = False
        parent_win = editor.parentWindow
        if parent_win:
            for wv in parent_win.findChildren(QWebEngineView):
                url = wv.url().toString()
                # Skip Anki's own internal pages
                if url.startswith('http://127.0.0.1') or url in ('', 'about:blank'):
                    continue
                # Found the embedded browser — add bar below it
                container = wv.parent()
                if container is not None:
                    from aqt.qt import QVBoxLayout, QWidget
                    lay = container.layout()
                    if lay is None:
                        lay = QVBoxLayout(container)
                        lay.setContentsMargins(0, 0, 0, 0)
                        lay.setSpacing(0)
                        lay.addWidget(wv)
                    lay.addWidget(bar)
                    placed = True
                    break
        if not placed:
            # Fallback: left panel
            editor.outerLayout.addWidget(bar)

    QTimer.singleShot(300, _place)


# ── Hook ──────────────────────────────────────────────────────
gui_hooks.editor_did_init.append(_add_bar)
