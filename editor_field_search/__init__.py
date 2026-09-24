"""
Editor Field Search
────────────────────
A "find in fields" tool for the note editor (Add / Edit Current).

• A search icon in the editor toolbar (also Ctrl+F) opens a compact floating
  search box in the top-right of the editor — it takes no layout space and
  floats over the content, so nothing is pushed down.
• Type a keyword → live match count "current / total".
• ▲ / ▼  (or Shift+Enter / Enter) navigate between matches; the editor
  scrolls to each match and paints its background.
• Highlight colour follows the time of day: yellow (morning),
  peach (afternoon), maroon (evening / night). Configurable.

Highlighting uses the CSS Custom Highlight API, which paints text ranges
WITHOUT modifying the DOM — so nothing is ever written into your notes.
Works across the editor's per-field shadow roots.
"""

from __future__ import annotations

import datetime
import json
import os

from aqt import gui_hooks, mw
from aqt.editor import Editor
from aqt.qt import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPoint,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import tooltip

_ADDON_DIR = os.path.dirname(os.path.abspath(__file__))

# ── The in-page search engine (injected into the editor webview) ───────────────
#
# Guarded IIFE: defining `window.__ankiSearch` is idempotent, so we can safely
# prepend this on every call. It re-scans the fields (incl. shadow roots) each
# search, so it always reflects the current note.

_ENGINE_JS = r"""
(function () {
  if (window.__ankiSearch) return;

  var ALL = "ankisearch-all";
  var ACTIVE = "ankisearch-active";
  var STYLE_ID = "ankisearch-style";

  var state = { term: "", ranges: [], idx: -1, bg: "#ffd60a", fg: "#1a1a1a" };

  function styleText() {
    // Other matches: dim neutral. Active match: the time-of-day colour, so the
    // one you navigate to with the arrows clearly stands out.
    return "::highlight(" + ALL + "){background-color:rgba(130,130,170,0.35);}" +
           "::highlight(" + ACTIVE + "){background-color:" + state.bg +
             ";color:" + state.fg + ";}";
  }

  function ensureStyle(root) {
    var isDoc = root.nodeType === 9;
    var host = isDoc ? root.head : root;
    if (!host) return;
    var s = root.querySelector("#" + STYLE_ID);
    if (s) { s.textContent = styleText(); return; }
    s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = styleText();
    host.appendChild(s);
  }

  // Collect the editable field elements, descending into shadow roots, and
  // make sure each tree scope carries our ::highlight styles.
  function collectEditables() {
    var out = [];
    var seen = new Set();
    function scan(root) {
      ensureStyle(root);
      var eds = root.querySelectorAll("anki-editable");
      if (!eds.length) eds = root.querySelectorAll('[contenteditable="true"],[contenteditable=""]');
      eds.forEach(function (el) { if (out.indexOf(el) < 0) out.push(el); });
      root.querySelectorAll("*").forEach(function (el) {
        if (el.shadowRoot && !seen.has(el.shadowRoot)) {
          seen.add(el.shadowRoot);
          scan(el.shadowRoot);
        }
      });
    }
    scan(document);
    return out;
  }

  function findInElement(el, term) {
    var res = [];
    var needle = term.toLowerCase();
    var nlen = term.length;
    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
    var node;
    while ((node = walker.nextNode())) {
      var text = node.nodeValue;
      if (!text) continue;
      var hay = text.toLowerCase();
      var start = 0, pos;
      while ((pos = hay.indexOf(needle, start)) !== -1) {
        try {
          var r = document.createRange();
          r.setStart(node, pos);
          r.setEnd(node, pos + nlen);
          res.push(r);
        } catch (e) {}
        start = pos + nlen;
      }
    }
    return res;
  }

  var HL_OK = !!(window.CSS && CSS.highlights && typeof Highlight !== "undefined");

  function applyHighlights() {
    if (!HL_OK) return;
    CSS.highlights.delete(ALL);
    CSS.highlights.delete(ACTIVE);
    if (!state.ranges.length) return;
    var all = new Highlight();
    state.ranges.forEach(function (r, i) { if (i !== state.idx) all.add(r); });
    CSS.highlights.set(ALL, all);
    if (state.idx >= 0) CSS.highlights.set(ACTIVE, new Highlight(state.ranges[state.idx]));
  }

  function clearHighlights() {
    if (window.CSS && CSS.highlights) {
      CSS.highlights.delete(ALL);
      CSS.highlights.delete(ACTIVE);
    }
    state.ranges = [];
    state.idx = -1;
  }

  // Nearest actually-scrollable ancestor, crossing shadow-DOM host boundaries.
  function findScroller(el) {
    while (el) {
      try {
        var st = getComputedStyle(el);
        var oy = st.overflowY;
        if ((oy === "auto" || oy === "scroll" || oy === "overlay") &&
            el.scrollHeight > el.clientHeight + 1) {
          return el;
        }
      } catch (e) {}
      if (el.parentElement) {
        el = el.parentElement;
      } else {
        var root = el.getRootNode ? el.getRootNode() : null;
        el = root && root.host ? root.host : null;
      }
    }
    return document.scrollingElement || document.documentElement;
  }

  function scrollToActive() {
    var r = state.ranges[state.idx];
    if (!r) return;
    var rect = null;
    try { rect = r.getBoundingClientRect(); } catch (e) {}
    var startEl = r.startContainer.nodeType === 1
      ? r.startContainer : r.startContainer.parentElement;
    if (!rect || (!rect.width && !rect.height)) {
      if (startEl && startEl.scrollIntoView) startEl.scrollIntoView({ block: "center" });
      return;
    }
    var scroller = findScroller(startEl);
    var root = document.scrollingElement || document.documentElement;
    if (!scroller || scroller === root || scroller === document.body) {
      var y = root.scrollTop + rect.top - (window.innerHeight / 2);
      root.scrollTo
        ? root.scrollTo({ top: Math.max(0, y), behavior: "smooth" })
        : (root.scrollTop = Math.max(0, y));
    } else {
      var srect = scroller.getBoundingClientRect();
      var target = scroller.scrollTop + (rect.top - srect.top) - (scroller.clientHeight / 2);
      scroller.scrollTo
        ? scroller.scrollTo({ top: Math.max(0, target), behavior: "smooth" })
        : (scroller.scrollTop = Math.max(0, target));
    }
  }

  function search(term) {
    clearHighlights();
    state.term = term || "";
    if (!state.term) return { count: 0, index: 0, supported: HL_OK };
    var eds = collectEditables();
    var ranges = [];
    eds.forEach(function (el) { ranges = ranges.concat(findInElement(el, state.term)); });
    state.ranges = ranges;
    state.idx = ranges.length ? 0 : -1;
    applyHighlights();
    if (state.idx >= 0) scrollToActive();
    return { count: ranges.length, index: state.idx >= 0 ? state.idx + 1 : 0, supported: HL_OK };
  }

  function go(delta) {
    if (!state.ranges.length) return { count: 0, index: 0, supported: HL_OK };
    state.idx = (state.idx + delta + state.ranges.length) % state.ranges.length;
    applyHighlights();
    scrollToActive();
    return { count: state.ranges.length, index: state.idx + 1, supported: HL_OK };
  }

  window.__ankiSearch = {
    search: function (term, bg, fg) {
      if (bg) state.bg = bg;
      if (fg) state.fg = fg;
      return search(term);
    },
    next: function () { return go(1); },
    prev: function () { return go(-1); },
    clear: function () { clearHighlights(); },
  };
})();
"""


# ── Time-of-day colour ─────────────────────────────────────────────────────────

_DEFAULT_COLORS = {
    "morning":   {"bg": "#ffd60a", "fg": "#1a1a1a"},
    "afternoon": {"bg": "#ffc09f", "fg": "#1a1a1a"},
    "evening":   {"bg": "#800020", "fg": "#ffffff"},
}


def _config() -> dict:
    return mw.addonManager.getConfig(__name__) or {}


def _colors() -> tuple[str, str]:
    cfg = _config()
    colors = {**_DEFAULT_COLORS, **cfg.get("colors", {})}
    mode = cfg.get("mode", "auto")
    if mode in colors:
        slot = mode
    else:
        h = datetime.datetime.now().hour
        slot = "morning" if 5 <= h < 12 else "afternoon" if 12 <= h < 18 else "evening"
    c = colors.get(slot, _DEFAULT_COLORS["morning"])
    return c.get("bg", "#ffd60a"), c.get("fg", "#1a1a1a")


# ── Search line edit (captures Esc / Enter / Shift+Enter) ──────────────────────

class _SearchEdit(QLineEdit):
    def __init__(self, popup: "SearchPopup"):
        super().__init__()
        self._popup = popup

    def keyPressEvent(self, e):
        key = e.key()
        if key == Qt.Key.Key_Escape:
            self._popup.close_popup()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._popup.go_prev()
            else:
                self._popup.go_next()
            return
        super().keyPressEvent(e)


# ── The floating search box ─────────────────────────────────────────────────────

_POPUP_STYLE = """
#efsPanel {
    background:#12121f; border:1px solid #3a2a6e; border-radius:10px;
}
#efsPanel QLineEdit {
    background:#0f0f17; color:#e2e8f0; border:1px solid #3a2a6e;
    border-radius:6px; padding:5px 9px; font-size:13px;
    selection-background-color:#7c3aed;
}
#efsPanel QLineEdit:focus { border-color:#7c3aed; }
#efsPanel QLabel#count { color:#a0a0c0; font-size:12px; min-width:62px; }
#efsPanel QPushButton {
    background:#2d2d4e; color:#e2e8f0; border:none; border-radius:6px;
    font-size:14px; font-weight:700; min-width:30px; min-height:28px;
}
#efsPanel QPushButton:hover { background:#3d3d6e; }
#efsPanel QPushButton:disabled { color:#5a5a80; background:#20203a; }
#efsPanel QPushButton#close { background:transparent; color:#8a8ab0; }
#efsPanel QPushButton#close:hover { background:#3d3d6e; color:#fff; }
"""

_POPUP_WIDTH = 610


class SearchPopup(QWidget):
    def __init__(self, editor: Editor):
        # Top-level Tool window so it always paints above the QWebEngineView.
        super().__init__(
            editor.widget,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint,
        )
        self.editor = editor
        self._warned = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(_POPUP_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QFrame()
        panel.setObjectName("efsPanel")
        panel.setStyleSheet(_POPUP_STYLE)
        outer.addWidget(panel)

        row = QHBoxLayout(panel)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(6)

        self.edit = _SearchEdit(self)
        self.edit.setMinimumWidth(400)
        self.edit.setPlaceholderText("Find in fields…")
        self.edit.textChanged.connect(self.do_search)
        row.addWidget(self.edit, 1)

        self.count = QLabel("")
        self.count.setObjectName("count")
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.count)

        self.prev_btn = QPushButton("▲")
        self.prev_btn.setToolTip("Previous match (Shift+Enter)")
        self.prev_btn.clicked.connect(self.go_prev)
        row.addWidget(self.prev_btn)

        self.next_btn = QPushButton("▼")
        self.next_btn.setToolTip("Next match (Enter)")
        self.next_btn.clicked.connect(self.go_next)
        row.addWidget(self.next_btn)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("close")
        close_btn.setToolTip("Close (Esc)")
        close_btn.clicked.connect(self.close_popup)
        row.addWidget(close_btn)

        self._set_nav_enabled(False)
        editor.widget.installEventFilter(self)
        self.hide()

    # ── keep it anchored top-right of the editor ────────────────────────────────

    def _reposition(self):
        w = self.editor.widget
        if w is None:
            return
        top_right = w.mapToGlobal(QPoint(w.width(), 0))
        x = top_right.x() - self.width() - 16
        y = top_right.y() + 46  # just below the toolbar row
        self.move(max(0, x), y)

    def eventFilter(self, obj, event):
        from aqt.qt import QEvent
        if obj is self.editor.widget and event.type() in (
            QEvent.Type.Move, QEvent.Type.Resize
        ):
            if self.isVisible():
                self._reposition()
        return False

    # ── webview bridge ──────────────────────────────────────────────────────────

    def _call(self, expr: str, cb=None):
        js = _ENGINE_JS + "\n" + expr
        web = getattr(self.editor, "web", None)
        if web is None:
            return
        if cb is not None:
            web.evalWithCallback(js, cb)
        else:
            web.eval(js)

    def do_search(self):
        term = self.edit.text()
        if not term:
            self._call("window.__ankiSearch.clear();")
            self.count.setText("")
            self._set_nav_enabled(False)
            return
        bg, fg = _colors()
        expr = "window.__ankiSearch.search(%s, %s, %s);" % (
            json.dumps(term), json.dumps(bg), json.dumps(fg),
        )
        self._call(expr, self._on_result)

    def go_next(self):
        self._call("window.__ankiSearch.next();", self._on_result)

    def go_prev(self):
        self._call("window.__ankiSearch.prev();", self._on_result)

    def _on_result(self, res):
        if not isinstance(res, dict):
            return
        count = int(res.get("count", 0))
        index = int(res.get("index", 0))
        if not res.get("supported", True) and not self._warned:
            self._warned = True
            tooltip("Field Search: colour highlighting isn't supported in this "
                    "Anki build — navigation still works.", period=4000)
        if count:
            self.count.setText(f"{index} / {count}")
        elif self.edit.text():
            self.count.setText("No matches")
        else:
            self.count.setText("")
        self._set_nav_enabled(count > 0)

    def _set_nav_enabled(self, on: bool):
        self.prev_btn.setEnabled(on)
        self.next_btn.setEnabled(on)

    # ── show / hide ───────────────────────────────────────────────────────────

    def open_popup(self):
        self._reposition()
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()
        self.edit.selectAll()
        if self.edit.text():
            self.do_search()

    def close_popup(self):
        self._call("window.__ankiSearch.clear();")
        self.count.setText("")
        self.hide()
        web = getattr(self.editor, "web", None)
        if web is not None:
            web.setFocus()

    def toggle(self):
        if self.isVisible():
            self.close_popup()
        else:
            self.open_popup()

    def refresh_if_open(self):
        # New note loaded → its highlights are gone; re-run the search.
        if self.isVisible() and self.edit.text():
            self.do_search()


# ── Wiring into every editor ─────────────────────────────────────────────────

def _ensure_popup(editor: Editor) -> "SearchPopup | None":
    popup = getattr(editor, "_field_search_popup", None)
    if popup is None:
        popup = SearchPopup(editor)
        editor._field_search_popup = popup
    return popup


def _on_editor_buttons(buttons: list, editor: Editor):
    icon = os.path.join(_ADDON_DIR, "search.svg")
    shortcut = _config().get("shortcut", "Ctrl+F")
    try:
        btn = editor.addButton(
            icon=icon,
            cmd="efs_toggle",
            func=lambda *a, e=editor: _ensure_popup(e).toggle(),
            tip=f"Find in fields ({shortcut})",
            keys=shortcut,
        )
        buttons.append(btn)
    except Exception as exc:
        print(f"[Editor Field Search] could not add button: {exc}")


def _on_load_note(editor: Editor):
    popup = getattr(editor, "_field_search_popup", None)
    if popup is not None:
        popup.refresh_if_open()


gui_hooks.editor_did_init_buttons.append(_on_editor_buttons)
gui_hooks.editor_did_load_note.append(_on_load_note)
