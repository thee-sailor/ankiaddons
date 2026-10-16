"""
File Launcher — attach PDFs/PPTX to cards and open them in the embedded browser
(the tabbed "Socrates" browser, add-on 918010938), the local browser, or the
desktop app.

• 📎 toolbar button: attach a PDF/PPTX into the collection media and insert a
  clickable link into the field.
• Links are clickable in the editor AND the reviewer; clicking opens the file.
• PDFs open as a NEW TAB in the embedded browser — Chromium's PDF viewer there
  provides pen/highlight/text annotation (draw on the PDF, then download).
• PPTX is converted to PDF (via LibreOffice, if available) so it opens in a tab
  and can be drawn on the same way; otherwise it opens in the desktop app.
• Tools → File Launcher Settings chooses the target per file type.
"""

from __future__ import annotations

import html
import importlib
import json
import os
import subprocess
import urllib.parse

from aqt import gui_hooks, mw
from aqt.editor import Editor
from aqt.qt import (
    QAction, QComboBox, QDesktopServices, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QLabel, QLineEdit, QUrl,
)
from aqt.utils import showWarning, tooltip

_ADDON = __name__
_DEFAULTS = {"pdf_target": "embedded_browser", "pptx_target": "embedded_browser",
             "libreoffice_path": ""}
_DOC_EXTS = (".pdf", ".pptx", ".ppt")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _cfg() -> dict:
    return {**_DEFAULTS, **(mw.addonManager.getConfig(_ADDON) or {})}


def _target_for(ext: str) -> str:
    c = _cfg()
    return c["pptx_target"] if ext in ("pptx", "ppt") else c["pdf_target"]


def _media_path(fname: str) -> str:
    return os.path.join(mw.col.media.dir(), fname)


# ── embedded browser (add-on 918010938) ───────────────────────────────────────

def _embedded_browser_ref():
    try:
        mod = importlib.import_module("918010938.browser")
        return getattr(mod, "_BROWSER_REF", None)
    except Exception:
        return None


def _open_in_embedded_browser(url: str) -> bool:
    ref = _embedded_browser_ref()
    if ref is None:
        return False
    try:
        ref._add_new_tab(url)      # opens a new tab next to the existing ones
        return True
    except Exception:
        return False


# ── PPTX → PDF via LibreOffice (so it renders in a browser tab) ────────────────

def _find_soffice() -> str | None:
    cfg_path = _cfg().get("libreoffice_path", "").strip()
    candidates = [cfg_path] if cfg_path else []
    candidates += [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for p in candidates:
        if p and (p == "soffice" or os.path.isfile(p)):
            return p
    return None


def _pptx_to_pdf(pptx_path: str) -> str | None:
    pdf = os.path.splitext(pptx_path)[0] + ".pdf"
    if os.path.isfile(pdf) and os.path.getmtime(pdf) >= os.path.getmtime(pptx_path):
        return pdf                                   # cached conversion is current
    soffice = _find_soffice()
    if not soffice:
        return None
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir",
             os.path.dirname(pptx_path), pptx_path],
            timeout=180, creationflags=_NO_WINDOW,
        )
    except Exception:
        return None
    return pdf if os.path.isfile(pdf) else None


# ── open a file per config ─────────────────────────────────────────────────────

def _os_open(path: str):
    try:
        os.startfile(path)                           # Windows default app
    except Exception:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def _open_file(fname: str):
    path = _media_path(fname)
    if not os.path.isfile(path):
        showWarning("File not found in media:\n%s" % fname)
        return
    ext = os.path.splitext(fname)[1].lower().lstrip(".")
    target = _target_for(ext)
    open_path = path

    if ext in ("pptx", "ppt") and target in ("embedded_browser", "local_browser"):
        pdf = _pptx_to_pdf(path)
        if pdf:
            open_path = pdf
        else:
            _os_open(path)
            tooltip("Opened in the desktop app.\n(Install LibreOffice to view/draw "
                    "PPTX in a browser tab.)", period=5000)
            return

    if target == "embedded_browser":
        if _open_in_embedded_browser(QUrl.fromLocalFile(open_path).toString()):
            tooltip("Opened in a browser tab.", period=2000)
            return
        # browser not open → fall back to the local browser
        QDesktopServices.openUrl(QUrl.fromLocalFile(open_path))
        tooltip("Embedded browser not open — opened externally.", period=3000)
        return
    if target == "local_browser":
        QDesktopServices.openUrl(QUrl.fromLocalFile(open_path))
        return
    _os_open(open_path)


# ── clickable link (works in editor + reviewer via pycmd) ─────────────────────

def _make_link(fname: str) -> str:
    # No inline onclick — Anki strips event handlers from field HTML. We mark the
    # link with class + data-fl and attach the click handler via injected JS.
    safe = html.escape(fname)
    label = html.escape(os.path.basename(fname))
    icon = "📊" if fname.lower().endswith((".pptx", ".ppt")) else "📄"
    return (
        '<a href="#" contenteditable="false" class="fl-link" data-fl="%s" '
        'style="color:#7c3aed;font-weight:600;text-decoration:none;cursor:pointer;">'
        '%s&nbsp;%s</a>&nbsp;'
        % (safe, icon, label)
    )


# JS that opens our links on click, in the editor (shadow-DOM fields) and the
# reviewer. Installed once per page; uses composedPath so it works across shadow
# roots, and pycmd to reach _on_js_message.
_CLICK_JS = r"""
(function () {
  if (window.__flClickReady) return;
  window.__flClickReady = true;
  document.addEventListener("click", function (e) {
    var path = e.composedPath ? e.composedPath() : [e.target];
    for (var i = 0; i < path.length; i++) {
      var el = path[i];
      if (el && el.getAttribute) {
        var f = el.getAttribute("data-fl");   // matches old + new links
        if (f) {
          e.preventDefault();
          e.stopPropagation();
          pycmd("fileopen:" + encodeURIComponent(f));
          return;
        }
      }
    }
  }, true);
})();
"""


def _inject_click_handler(web):
    try:
        web.eval(_CLICK_JS)
    except Exception:
        pass


def _on_editor_load(editor: Editor):
    _inject_click_handler(editor.web)


def _on_reviewer_show(card=None):
    try:
        _inject_click_handler(mw.reviewer.web)
    except Exception:
        pass


def _attach(editor: Editor):
    path, _ = QFileDialog.getOpenFileName(
        editor.parentWindow, "Attach PDF or PPTX", "",
        "Documents (*.pdf *.pptx *.ppt);;All files (*)")
    if not path:
        return
    if not path.lower().endswith(_DOC_EXTS):
        showWarning("Please choose a .pdf, .pptx or .ppt file.")
        return
    try:
        with open(path, "rb") as f:
            data = f.read()
        fn = mw.col.media.write_data(os.path.basename(path), data)
    except Exception as exc:
        showWarning("Could not attach the file:\n%s" % exc)
        return
    link = _make_link(fn)
    try:
        editor.doPaste(link, True, False)
    except Exception:
        editor.web.eval("pasteHTML(%s, true, false);" % json.dumps(link))
    tooltip("Attached %s" % fn, period=2000)


def _on_editor_buttons(buttons: list, editor: Editor):
    try:
        buttons.append(editor.addButton(
            icon=None,
            cmd="file_launcher_attach",
            func=lambda e: _attach(e),
            tip="Attach a PDF / PPTX and insert a clickable link",
            label="📎",
        ))
    except Exception as exc:
        print("[File Launcher] could not add button:", exc)


def _on_js_message(handled, message: str, context):
    if message.startswith("fileopen:"):
        fname = urllib.parse.unquote(message[len("fileopen:"):])
        _open_file(fname)
        return (True, None)
    return handled


# ── settings dialog ─────────────────────────────────────────────────────────────

_TARGET_LABELS = [
    ("Embedded browser (Socrates tabs)", "embedded_browser"),
    ("Local browser / default viewer", "local_browser"),
    ("Desktop app", "local_app"),
]


class SettingsDialog(QDialog):
    def __init__(self):
        super().__init__(mw)
        self.setWindowTitle("File Launcher Settings")
        self.setMinimumWidth(420)
        c = _cfg()
        form = QFormLayout(self)

        self.pdf_combo = QComboBox()
        self.pptx_combo = QComboBox()
        for label, val in _TARGET_LABELS:
            self.pdf_combo.addItem(label, val)
            self.pptx_combo.addItem(label, val)
        self._select(self.pdf_combo, c["pdf_target"])
        self._select(self.pptx_combo, c["pptx_target"])
        form.addRow("Open PDFs in:", self.pdf_combo)
        form.addRow("Open PPTX in:", self.pptx_combo)

        self.lo_edit = QLineEdit(c.get("libreoffice_path", ""))
        self.lo_edit.setPlaceholderText("auto-detect — set only if PPTX won't open")
        form.addRow("LibreOffice soffice path:", self.lo_edit)

        note = QLabel("PPTX is converted to PDF (LibreOffice) so it can open in a "
                      "browser tab and be drawn on. PDFs open in the browser's PDF "
                      "viewer, which has pen/highlight/text tools.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#888; font-size:11px;")
        form.addRow(note)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    @staticmethod
    def _select(combo: QComboBox, value: str):
        i = combo.findData(value)
        if i >= 0:
            combo.setCurrentIndex(i)

    def _save(self):
        cfg = mw.addonManager.getConfig(_ADDON) or {}
        cfg["pdf_target"] = self.pdf_combo.currentData()
        cfg["pptx_target"] = self.pptx_combo.currentData()
        cfg["libreoffice_path"] = self.lo_edit.text().strip()
        mw.addonManager.writeConfig(_ADDON, cfg)
        tooltip("Saved.")
        self.accept()


def _add_menu():
    act = QAction("File Launcher Settings…", mw)
    act.triggered.connect(lambda: SettingsDialog().exec())
    mw.form.menuTools.addAction(act)


gui_hooks.editor_did_init_buttons.append(_on_editor_buttons)
gui_hooks.webview_did_receive_js_message.append(_on_js_message)
gui_hooks.main_window_did_init.append(_add_menu)
gui_hooks.editor_did_load_note.append(_on_editor_load)
gui_hooks.reviewer_did_show_question.append(_on_reviewer_show)
gui_hooks.reviewer_did_show_answer.append(_on_reviewer_show)
