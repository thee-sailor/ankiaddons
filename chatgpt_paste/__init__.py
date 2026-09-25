"""
Paste from ChatGPT
──────────────────
• Automatic on Ctrl+V: when the clipboard looks like Markdown/LaTeX (as copied
  from ChatGPT) it is rendered to Anki HTML + MathJax and inserted; anything
  else pastes normally. The equation renders right away.
• Automatic migration/repair on startup (see migrate.py): older notes with
  un-rendered LaTeX are fixed in place, HTML that a previous version trapped
  inside an equation is pulled back out, and duplicated plain text is removed.
  All tag-safe and idempotent — it never lets an equation swallow other markup.
"""

from __future__ import annotations

import json
import re

from aqt import gui_hooks, mw
from aqt.editor import Editor
from aqt.qt import QMimeData, QTimer
from aqt.utils import tooltip

from . import katex, md2anki, migrate


def _config() -> dict:
    return mw.addonManager.getConfig(__name__) or {}


# ── Clipboard paste (fresh ChatGPT Markdown) ───────────────────────────────────

_MD_MARKERS = (
    r"\$\$?[^$]+\$\$?", r"\\\(|\\\[", r"^\s{0,3}#{1,6}\s+",
    r"^\s*([-*+]|\d+[.)])\s+", r"\n\s*\|?[\s:|-]*-[\s:|-]*\n",
    r"\*\*[^*]+\*\*", r"`[^`]+`", r"->|=>|<->|<=>",
    r"\\(text|frac|rightarrow|boxed|sqrt|sum|int|alpha|beta|uparrow|downarrow)\b",
)


def _looks_like_markdown(text: str) -> bool:
    return bool(text) and any(re.search(p, text, re.MULTILINE) for p in _MD_MARKERS)


def _do_internal_paste(editor: Editor, html: str):
    """Insert as internal paste (keeps styles), then fully reload the note so the
    <anki-mathjax> equations mount and render (nothing left in edit-mode)."""
    try:
        editor.doPaste(html, True, False)
    except Exception:
        editor.web.eval("pasteHTML(%s, true, false);" % json.dumps(html))

    def _finish():
        def _reload():
            try:
                editor.loadNote()
            except Exception:
                pass
        try:
            editor.saveNow(_reload)
        except Exception:
            _reload()

    QTimer.singleShot(150, _finish)


def _render_after_paste(editor: Editor):
    """Let Anki's native paste land first (it downloads/embeds images and keeps
    tables, bold, headings), then clean up the math in the pasted field(s) with
    the same tag-safe migration used on startup. Images survive because
    migrate_field never touches HTML tags like <img>."""
    def _cb():
        note = getattr(editor, "note", None)
        if note is None:
            return
        changed = False
        for i, val in enumerate(note.fields):
            new = migrate.migrate_field(val)
            if new != val:
                note.fields[i] = new
                changed = True
        if not changed:
            return
        try:
            if getattr(note, "id", 0):
                mw.col.update_note(note)
        except Exception:
            pass
        try:
            editor.loadNote()
        except Exception:
            pass

    try:
        editor.saveNow(_cb)
    except Exception:
        _cb()


def _on_will_process_mime(mime: QMimeData, editor_web_view, internal: bool,
                          extended: bool, drop_event: bool) -> QMimeData:
    if internal or drop_event:
        return mime
    if not _config().get("auto", True):
        return mime
    try:
        has_html = mime.hasHtml()
        html = mime.html() if has_html else ""
        text = mime.text() if mime.hasText() else ""
        has_img = (mime.hasImage() or mime.hasUrls()
                   or (has_html and "<img" in html.lower()))
    except Exception:
        return mime

    editor = getattr(editor_web_view, "editor", None)
    if editor is None:
        return mime

    # Best fix: clean ChatGPT's KaTeX HTML at the source. This removes the
    # duplicated visible text, keeps the exact LaTeX (so sub/superscripts render
    # correctly), and leaves images/tables intact for Anki's native paste.
    if has_html and katex.has_katex(html):
        try:
            mime.setHtml(katex.clean_katex_html(html))
        except Exception:
            pass
        QTimer.singleShot(300, lambda: _render_after_paste(editor))
        return mime

    if not _looks_like_markdown(text):
        return mime  # nothing to render

    if has_html or has_img:
        # Native paste keeps images & rich formatting; fix the math afterwards.
        QTimer.singleShot(300, lambda: _render_after_paste(editor))
        return mime

    # Plain-text-only Markdown (no images/HTML to lose): render it ourselves.
    conv = md2anki.convert(text)
    QTimer.singleShot(0, lambda: _do_internal_paste(editor, conv))
    return QMimeData()  # suppress Anki's own paste; we insert ourselves


# ── Automatic migration / repair on startup ────────────────────────────────────

def _auto_migrate():
    if not mw or not mw.col:
        return
    try:
        nids = mw.col.db.list(
            "SELECT id FROM notes WHERE "
            "flds LIKE '%\\%' OR flds LIKE '%$$%' "
            "OR (flds LIKE '%anki-mathjax%' AND flds LIKE '%&lt;%')"
        )
    except Exception:
        return
    if not nids:
        return

    to_update, fixed = [], 0
    for nid in nids:
        try:
            note = mw.col.get_note(nid)
        except Exception:
            continue
        dirty = False
        for i, val in enumerate(note.fields):
            new = migrate.migrate_field(val)
            if new != val:
                note.fields[i] = new
                dirty = True
        if dirty:
            to_update.append(note)
            fixed += 1
        if len(to_update) >= 500:
            mw.col.update_notes(to_update)
            to_update = []

    if to_update:
        mw.col.update_notes(to_update)
    if fixed:
        tooltip(f"Fixed LaTeX in {fixed} note(s).", period=3000)


def _on_collection_load(_col=None):
    QTimer.singleShot(400, _auto_migrate)


gui_hooks.editor_will_process_mime.append(_on_will_process_mime)
gui_hooks.collection_did_load.append(_on_collection_load)
