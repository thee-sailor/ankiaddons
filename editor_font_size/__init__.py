"""
Editor Font Size
────────────────
Adds two buttons to the note editor toolbar that increase / decrease the font
size of the currently selected text. Works inside Anki's per-field shadow DOM
by wrapping the selection in a relatively-sized <span> (em-based, so repeated
clicks keep scaling).

Shortcuts: Ctrl+Shift+.  (bigger)   Ctrl+Shift+,  (smaller)
"""

from __future__ import annotations

import os

from aqt import gui_hooks
from aqt.editor import Editor

_DIR = os.path.dirname(os.path.abspath(__file__))

_JS = r"""
(function () {
  if (window.__efsFont) return;

  function activeSelection() {
    var el = document.activeElement, root = document;
    while (el && el.shadowRoot && el.shadowRoot.activeElement) {
      root = el.shadowRoot;
      el = el.shadowRoot.activeElement;
    }
    return (root.getSelection && root.getSelection()) || window.getSelection();
  }

  function adjust(factor) {
    var sel = activeSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return;
    var range = sel.getRangeAt(0);
    var span = document.createElement("span");
    span.style.fontSize = factor > 0 ? "1.2em" : "0.83em";
    try {
      span.appendChild(range.extractContents());
      range.insertNode(span);
      sel.removeAllRanges();
      var nr = document.createRange();
      nr.selectNodeContents(span);
      sel.addRange(nr);
      span.dispatchEvent(new Event("input", { bubbles: true }));  // let Anki save
    } catch (e) {}
  }

  window.__efsFont = {
    bigger: function () { adjust(1); },
    smaller: function () { adjust(-1); },
  };
})();
"""


def _apply(editor: Editor, bigger: bool):
    fn = "bigger" if bigger else "smaller"
    editor.web.eval(_JS + ("\nwindow.__efsFont && window.__efsFont.%s();" % fn))


def _on_buttons(buttons: list, editor: Editor):
    try:
        buttons.append(editor.addButton(
            icon=os.path.join(_DIR, "font_increase.svg"),
            cmd="efs_font_bigger",
            func=lambda e: _apply(e, True),
            tip="Increase font size of selection (Ctrl+Shift+.)",
            keys="Ctrl+Shift+.",
        ))
        buttons.append(editor.addButton(
            icon=os.path.join(_DIR, "font_decrease.svg"),
            cmd="efs_font_smaller",
            func=lambda e: _apply(e, False),
            tip="Decrease font size of selection (Ctrl+Shift+,)",
            keys="Ctrl+Shift+,",
        ))
    except Exception as exc:
        print("[Editor Font Size] could not add buttons:", exc)


gui_hooks.editor_did_init_buttons.append(_on_buttons)
