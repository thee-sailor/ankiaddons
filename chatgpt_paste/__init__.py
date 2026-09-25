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

import hashlib
import json
import re
import threading
import urllib.request

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


def _img_ext(ctype: str, url: str) -> str:
    c = (ctype or "").lower()
    if "png" in c:
        return ".png"
    if "jpeg" in c or "jpg" in c:
        return ".jpg"
    if "gif" in c:
        return ".gif"
    if "webp" in c:
        return ".webp"
    if "svg" in c:
        return ".svg"
    m = re.search(r"\.(png|jpe?g|gif|webp|svg)", url.lower())
    return "." + m.group(1) if m else ".png"


def _localize_and_paste(editor: Editor, html: str):
    """Download any remote <img> into the collection's media folder, rewrite the
    src to the local filename, then insert via an internal paste (which keeps the
    <anki-mathjax> equations and images intact). Downloading runs off the UI
    thread; media writes and the paste happen back on the main thread."""
    urls = list(dict.fromkeys(re.findall(r'<img[^>]+\bsrc="([^"]+)"', html)))
    remote = [u for u in urls if u.replace("&amp;", "&").startswith(("http://", "https://"))]

    if not remote:
        _do_internal_paste(editor, html)
        return

    tooltip("Fetching %d image(s)…" % len(remote), period=2500)

    def _work():
        fetched = {}
        for u in remote:
            real = u.replace("&amp;", "&")
            try:
                req = urllib.request.Request(real, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    fetched[u] = (r.read(), r.headers.get("Content-Type", ""))
            except Exception:
                pass

        def _finish():
            out = html
            for u, (data, ctype) in fetched.items():
                try:
                    name = "chatgpt-%s%s" % (hashlib.md5(data).hexdigest()[:16], _img_ext(ctype, u))
                    fn = mw.col.media.write_data(name, data)
                    out = out.replace('src="%s"' % u, 'src="%s"' % fn)
                except Exception:
                    pass
            _do_internal_paste(editor, out)

        mw.taskman.run_on_main(_finish)

    threading.Thread(target=_work, daemon=True).start()


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
    except Exception:
        return mime

    editor = getattr(editor_web_view, "editor", None)
    if editor is None:
        return mime

    # ChatGPT (KaTeX) content: fully take over the paste. Clean the math from the
    # KaTeX annotations (no duplication, correct sub/superscripts), download the
    # images locally, and insert internally so <anki-mathjax> survives.
    if has_html and katex.has_katex(html):
        cleaned = katex.clean_katex_html(html)
        QTimer.singleShot(0, lambda: _localize_and_paste(editor, cleaned))
        return QMimeData()  # suppress Anki's own paste; we handle it entirely

    # Other rich HTML (web pages, etc.) — let Anki paste it normally.
    if has_html:
        return mime

    # Plain-text Markdown (no HTML) — render it ourselves.
    if _looks_like_markdown(text):
        QTimer.singleShot(0, lambda: _do_internal_paste(editor, md2anki.convert(text)))
        return QMimeData()

    return mime


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
