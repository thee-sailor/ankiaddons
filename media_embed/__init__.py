"""
Media Embed — play YouTube links and local audio/video INSIDE the card
(the review screen), never in a popup window.

• Paste a YouTube link in the editor  → it is captured automatically and shows
  as an embedded player on the card, with an "Open on YouTube" fallback for the
  rare video whose owner blocks embedding.
• 🎞 / 🎵 toolbar buttons attach a local video / audio file and embed it the
  same way, with native play / pause / volume controls.

Nothing ever auto-plays: a card opens paused and you press play. Everything
renders inline on the card — never a new tab or window.

Why a conversion step: Anki's card webview (Chromium) can't decode H.264/MP4
video or AAC/M4A audio — they show a black frame / play silently. So on attach,
those formats are converted ONCE, with Anki's own bundled mpv, to AV1 WebM /
Ogg Vorbis, which the webview plays inline. WebM, VP9/AV1 MP4, MP3, Ogg, WAV and
FLAC already play, so they are embedded untouched.

Robustness: a tiny, sanitiser-safe placeholder link is stored in the field (so
the editor stays tidy and Anki never strips it); when the card is shown, the
placeholder is swapped for a real <iframe> / <video> / <audio> with controls and
NO autoplay.
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.parse

from aqt import gui_hooks, mw
from aqt.editor import Editor
from aqt.qt import (
    QAction, QCheckBox, QDesktopServices, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QLabel, QMimeData, QProgressDialog, QSpinBox, Qt, QTimer, QUrl,
)
from aqt.utils import askUser, showWarning, tooltip

ADDON = __name__
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _cfg() -> dict:
    base = {"video_crf": 34, "youtube_privacy_mode": False}
    base.update(mw.addonManager.getConfig(ADDON) or {})
    return base


# ── YouTube link parsing ──────────────────────────────────────────────────────

_YT_ID = r"[A-Za-z0-9_-]{11}"
_YT_PATTERNS = [
    re.compile(r"(?:youtube\.com|youtube-nocookie\.com)/watch\?(?:[^ ]*&)?v=(" + _YT_ID + r")"),
    re.compile(r"youtu\.be/(" + _YT_ID + r")"),
    re.compile(r"(?:youtube\.com|youtube-nocookie\.com)/(?:embed|shorts|v|live)/(" + _YT_ID + r")"),
]


def _youtube_id(text: str):
    if not text:
        return None
    for p in _YT_PATTERNS:
        m = p.search(text)
        if m:
            return m.group(1)
    return None


def _parse_start(url: str) -> int:
    """Seconds to start at, from a ?t= / &start= / #t= value like 90 or 1m30s."""
    m = re.search(r"[?&#](?:t|start)=([0-9hms]+)", url or "")
    if not m:
        return 0
    v = m.group(1)
    if v.isdigit():
        return int(v)
    sec = 0
    for num, unit in re.findall(r"(\d+)([hms])", v):
        sec += int(num) * {"h": 3600, "m": 60, "s": 1}[unit]
    return sec


def _looks_like_lone_url(text: str) -> bool:
    """True only when the clipboard is essentially a single YouTube URL, so we
    never hijack a larger paste that merely mentions a link."""
    t = (text or "").strip()
    return bool(t) and len(t.split()) == 1 and (
        "youtu.be" in t or "youtube.com" in t or "youtube-nocookie" in t
    )


# ── placeholders stored in the field (safe, tidy, never auto-played) ──────────

def _yt_placeholder(vid: str, start: int) -> str:
    data_start = ' data-start="%d"' % start if start else ""
    return (
        '<a class="media-embed yt-embed" data-ytid="%s"%s '
        'href="https://youtu.be/%s" contenteditable="false" '
        'style="display:inline-block;padding:4px 10px;border-radius:6px;'
        'background:#ffecec;color:#c00;font-weight:600;text-decoration:none;'
        'border:1px solid #f5bcbc;">&#9654;&nbsp;YouTube&nbsp;%s</a>&nbsp;'
        % (vid, data_start, vid, vid)
    )


def _media_placeholder(fname: str, kind: str) -> str:
    icon = "&#127902;" if kind == "video" else "&#127925;"   # 🎞 / 🎵
    bg, fg, bd = ("#eef", "#33a", "#bcbcf5") if kind == "video" else ("#eafaef", "#1a7f37", "#b7e2c3")
    return (
        '<a class="media-embed local-embed" data-media="%s" data-mkind="%s" '
        'href="#" contenteditable="false" '
        'style="display:inline-block;padding:4px 10px;border-radius:6px;'
        'background:%s;color:%s;font-weight:600;text-decoration:none;'
        'border:1px solid %s;">%s&nbsp;%s</a>&nbsp;'
        % (html.escape(fname), kind, bg, fg, bd, icon, html.escape(os.path.basename(fname)))
    )


# Capture the focused field + caret BEFORE focus moves (a file dialog or the
# transcode steals it), so we can insert exactly there afterwards — otherwise the
# content lands at the very start of the card. Shadow-DOM aware (Anki fields).
_SAVE_CARET_JS = r"""
(function () {
  var el = document.activeElement, root = document;
  while (el && el.shadowRoot && el.shadowRoot.activeElement) {
    root = el.shadowRoot; el = el.shadowRoot.activeElement;
  }
  var s = (root.getSelection && root.getSelection()) || window.getSelection();
  window.__meField = el;
  window.__meSel = s;
  try { window.__meRange = (s && s.rangeCount) ? s.getRangeAt(0).cloneRange() : null; }
  catch (e) { window.__meRange = null; }
})();
"""

# Restore that caret, then insert the HTML there (not at the top of the note).
_RESTORE_INSERT_JS = r"""
(function (html) {
  try {
    var f = window.__meField;
    if (f && f.focus) f.focus();
    var s = window.__meSel, r = window.__meRange;
    if (s && r) { s.removeAllRanges(); s.addRange(r); }
  } catch (e) {}
  try { document.execCommand("insertHTML", false, html); } catch (e) {}
})(%s);
"""


def _save_caret(editor: Editor):
    try:
        editor.web.eval(_SAVE_CARET_JS)
    except Exception:
        pass


def _insert(editor: Editor, frag: str):
    """Insert at the caret saved by _save_caret (keeping the cursor position)."""
    try:
        editor.web.eval(_RESTORE_INSERT_JS % json.dumps(frag))
    except Exception:
        try:
            editor.doPaste(frag, True, False)
        except Exception:
            pass


# ── capture a pasted YouTube link in the editor ───────────────────────────────

def _on_will_process_mime(mime: QMimeData, editor_web_view, internal: bool,
                          extended: bool, drop_event: bool) -> QMimeData:
    if internal or drop_event:
        return mime
    try:
        text = mime.text() if mime.hasText() else ""
    except Exception:
        return mime
    if not _looks_like_lone_url(text):
        return mime
    vid = _youtube_id(text)
    if not vid:
        return mime
    editor = getattr(editor_web_view, "editor", None)
    if editor is None:
        return mime
    _save_caret(editor)                             # remember the cursor spot
    chip = _yt_placeholder(vid, _parse_start(text))
    QTimer.singleShot(0, lambda: _insert(editor, chip))
    tooltip("Embedded YouTube video — it will play on the card.", period=2500)
    return QMimeData()                              # suppress the raw-URL paste


# ── codec detection: can Anki's webview play this file as-is? ──────────────────

_WEB_VIDEO_MARKERS = (b"av01", b"vp09", b"vp08", b"V_AV1", b"V_VP9", b"V_VP8")
_BAD_VIDEO_MARKERS = (b"avc1", b"avc3", b"hev1", b"hvc1", b"hvcC", b"mp4v",
                      b"V_MPEG4/ISO/AVC", b"V_MPEGH/ISO/HEVC")
_WEB_AUDIO_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".oga", ".opus", ".weba")
_BAD_AUDIO_EXTS = (".m4a", ".aac", ".wma", ".alac")


def _is_web_video(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".webm", ".ogv"):
        return True
    try:
        head = open(path, "rb").read(262144)
    except Exception:
        return False
    if any(m in head for m in _BAD_VIDEO_MARKERS):
        return False
    return any(m in head for m in _WEB_VIDEO_MARKERS)


def _is_web_audio(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in _WEB_AUDIO_EXTS:
        return True
    if ext in _BAD_AUDIO_EXTS or ext == ".mp4":
        return False
    try:
        head = open(path, "rb").read(65536)
    except Exception:
        return True
    return b"mp4a" not in head                      # mp4a fourcc ⇒ AAC ⇒ convert


# ── mpv (bundled with Anki) — transcode to a webview-playable format ──────────

def _mpv_path():
    try:
        import anki_audio
        base = os.path.dirname(anki_audio.__file__)
        for name in ("mpv.exe", "mpv"):
            p = os.path.join(base, name)
            if os.path.isfile(p):
                return p
    except Exception:
        pass
    import shutil
    return shutil.which("mpv")


def _cleanup(d):
    try:
        for f in os.listdir(d):
            try:
                os.remove(os.path.join(d, f))
            except Exception:
                pass
        os.rmdir(d)
    except Exception:
        pass


def _transcode_async(src_path: str, kind: str, stem: str, on_success,
                     on_error=None, on_cancel=None, prefix: str = ""):
    """Convert src → AV1 WebM (video) or Ogg Vorbis (audio) with Anki's mpv, on a
    background thread, behind a busy dialog. `on_success(stored_name, kind)` runs
    on the main thread once the converted file is written into collection media.
    `on_error()` runs if mpv fails (bulk mode continues); `on_cancel()` if the
    user cancels; `prefix` is shown in the dialog (e.g. "(2/5) ")."""
    mpv = _mpv_path()
    if not mpv:
        showWarning("Anki's bundled mpv wasn't found, so “%s” can't be converted "
                    "for inline playback." % stem)
        if on_error:
            on_error()
        return
    tmpdir = tempfile.mkdtemp(prefix="media_embed_")
    ext = ".webm" if kind == "video" else ".ogg"
    out = os.path.join(tmpdir, "out" + ext)
    crf = int(_cfg().get("video_crf", 34))
    state = {"proc": None, "cancel": False}

    dlg = QProgressDialog(
        "%sConverting “%s” for inline playback…\nThis happens once; long videos "
        "take a few minutes." % (prefix, stem), "Cancel", 0, 0, mw)
    dlg.setWindowTitle("Media Embed")
    dlg.setMinimumWidth(440)
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    dlg.show()
    t0 = time.time()

    timer = QTimer(mw)
    timer.setInterval(500)

    def on_tick():
        if dlg.wasCanceled() and not state["cancel"]:
            state["cancel"] = True
            p = state["proc"]
            if p:
                try:
                    p.terminate()
                except Exception:
                    pass
        dlg.setLabelText("%sConverting “%s”…   %ds elapsed" % (prefix, stem, int(time.time() - t0)))

    timer.timeout.connect(on_tick)
    timer.start()

    def work():
        args = [mpv, "--no-config", "--really-quiet", "--no-terminal", src_path]
        if kind == "video":
            args += ["--ovc=libaom-av1",
                     "--ovcopts=usage=realtime,cpu-used=8,crf=%d,b=0,row-mt=1" % crf,
                     "--oac=vorbis", "--oacopts=aq=4"]
        else:
            args += ["--no-video", "--oac=vorbis", "--oacopts=aq=5"]
        args += ["--o=" + out]
        try:
            p = subprocess.Popen(args, creationflags=_NO_WINDOW,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            state["proc"] = p
            p.wait()
            return p.returncode
        except Exception:
            return -999

    def done(fut):
        timer.stop()
        try:
            dlg.close()
        except Exception:
            pass
        try:
            rc = fut.result()
        except Exception:
            rc = -1
        if state["cancel"]:
            _cleanup(tmpdir)
            if on_cancel:
                on_cancel()
            else:
                tooltip("Conversion cancelled — nothing attached.", period=2500)
            return
        if rc == 0 and os.path.isfile(out) and os.path.getsize(out) > 0:
            try:
                data = open(out, "rb").read()
                fn = mw.col.media.write_data(stem + ext, data)
            except Exception as exc:
                _cleanup(tmpdir)
                showWarning("Couldn't save the converted file:\n%s" % exc)
                if on_error:
                    on_error()
                return
            _cleanup(tmpdir)
            on_success(fn, kind)
        else:
            _cleanup(tmpdir)
            if on_error:
                tooltip("Skipped “%s” (couldn't convert, mpv code %s)." % (stem, rc), period=3000)
                on_error()
            else:
                showWarning("Couldn't convert “%s” for inline playback (mpv code %s).\n"
                            "It was not attached." % (stem, rc))

    mw.taskman.run_in_background(work, done)


# ── attach a local video / audio file ─────────────────────────────────────────

def _attach(editor: Editor, kind: str):
    # Save the caret NOW, while the field still has focus — the file dialog and
    # the transcode steal it, which is why media used to land at the card start.
    # Yield one tick so the save-caret JS runs before the dialog opens.
    _save_caret(editor)
    QTimer.singleShot(0, lambda: _attach_pick(editor, kind))


def _attach_pick(editor: Editor, kind: str):
    if kind == "video":
        filt = "Video (*.mp4 *.webm *.mkv *.mov *.m4v *.avi *.ogv);;All files (*)"
    else:
        filt = "Audio (*.mp3 *.m4a *.aac *.ogg *.oga *.opus *.wav *.flac *.wma);;All files (*)"
    path, _ = QFileDialog.getOpenFileName(
        editor.parentWindow, "Attach a local %s" % kind, "", filt)
    if not path:
        return

    web_ok = _is_web_video(path) if kind == "video" else _is_web_audio(path)
    base = os.path.basename(path)

    if web_ok:
        try:
            with open(path, "rb") as f:
                data = f.read()
            fn = mw.col.media.write_data(base, data)
        except Exception as exc:
            showWarning("Could not attach the file:\n%s" % exc)
            return
        _insert(editor, _media_placeholder(fn, kind))
        tooltip("Attached %s — it will play on the card." % fn, period=2500)
        return

    # Needs conversion to play inside the card webview.
    stem = os.path.splitext(base)[0]

    def after(fn, k):
        try:
            _insert(editor, _media_placeholder(fn, k))
            tooltip("Converted & attached %s — it will play on the card." % fn, period=3500)
        except Exception:
            tooltip("Converted to %s (added to media). Re-open the note to insert it."
                    % fn, period=5000)

    _transcode_async(path, kind, stem, after)


def _on_editor_buttons(buttons: list, editor: Editor):
    try:
        buttons.append(editor.addButton(
            icon=None, cmd="media_embed_video", func=lambda e: _attach(e, "video"),
            tip="Attach a local video — plays inline on the card", label="🎞"))
        buttons.append(editor.addButton(
            icon=None, cmd="media_embed_audio", func=lambda e: _attach(e, "audio"),
            tip="Attach local audio — plays inline on the card", label="🎵"))
    except Exception as exc:
        print("[Media Embed] could not add buttons:", exc)


# ── render the real players on the card (reviewer only, no autoplay) ──────────

def _render_js(domain: str) -> str:
    return r"""
(function () {
  var DOMAIN = '%s';
  function go() {
    document.querySelectorAll('a.yt-embed[data-ytid]:not([data-me-done])').forEach(function (a) {
      a.setAttribute('data-me-done', '1');
      var id = a.getAttribute('data-ytid');
      var start = parseInt(a.getAttribute('data-start') || '0', 10);
      var src = 'https://' + DOMAIN + '/embed/' + id + '?rel=0&playsinline=1' + (start > 0 ? ('&start=' + start) : '');
      var wrap = document.createElement('div');
      wrap.className = 'me-ytwrap';
      wrap.style.cssText = 'max-width:640px;margin:10px auto;';
      var box = document.createElement('div');
      box.style.cssText = 'position:relative;width:100%%;padding-top:56.25%%;';
      var f = document.createElement('iframe');
      f.src = src;                               // no autoplay param → stays paused
      f.setAttribute('frameborder', '0');
      f.setAttribute('allow', 'accelerometer;clipboard-write;encrypted-media;gyroscope;picture-in-picture');
      f.setAttribute('allowfullscreen', '');
      f.style.cssText = 'position:absolute;inset:0;width:100%%;height:100%%;border:0;border-radius:8px;';
      box.appendChild(f);
      var cap = document.createElement('div');
      cap.style.cssText = 'text-align:center;margin-top:4px;font-size:12px;';
      var link = document.createElement('a');
      link.href = 'https://youtu.be/' + id;
      link.textContent = 'Open on YouTube ↗';
      link.style.cssText = 'color:#36c;text-decoration:none;';
      link.addEventListener('click', function (e) {
        e.preventDefault();
        pycmd('meopen:' + encodeURIComponent('https://youtu.be/' + id));
      });
      cap.appendChild(link);
      wrap.appendChild(box); wrap.appendChild(cap);
      a.replaceWith(wrap);
    });
    document.querySelectorAll('a.local-embed[data-media]:not([data-me-done])').forEach(function (a) {
      a.setAttribute('data-me-done', '1');
      var file = a.getAttribute('data-media');
      var kind = a.getAttribute('data-mkind');
      var el = document.createElement(kind === 'video' ? 'video' : 'audio');
      el.setAttribute('controls', '');           // play / pause / volume
      el.setAttribute('preload', 'metadata');    // NOT autoplay
      el.src = encodeURIComponent(file);         // served from collection.media
      if (kind === 'video') {
        el.style.cssText = 'max-width:640px;width:100%%;display:block;margin:10px auto;border-radius:8px;';
      } else {
        el.style.cssText = 'width:100%%;max-width:480px;display:block;margin:10px auto;';
      }
      a.replaceWith(el);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', go);
  } else {
    go();
  }
  setTimeout(go, 60);                            // safety pass once the card settles
})();
""" % domain


def _render_on_card(card=None):
    domain = "www.youtube-nocookie.com" if _cfg().get("youtube_privacy_mode") else "www.youtube.com"
    try:
        mw.reviewer.web.eval(_render_js(domain))
    except Exception:
        pass


def _on_js_message(handled, message: str, context):
    if message.startswith("meopen:"):
        url = urllib.parse.unquote(message[len("meopen:"):])
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception:
            pass
        return (True, None)
    return handled


# ── convert already-attached files (Tools menu) ───────────────────────────────

# Matches one stored local-media placeholder anchor in a field.
_ANCHOR_RE = re.compile(r'<a\b(?=[^>]*\blocal-embed\b)[^>]*>.*?</a>', re.S)


def _anchor_media(tag: str):
    """(real_filename, kind) from a placeholder anchor, or (None, None)."""
    mm = re.search(r'data-media="([^"]*)"', tag)
    if not mm:
        return None, None
    mk = re.search(r'data-mkind="([^"]*)"', tag)
    return html.unescape(mm.group(1)), (mk.group(1) if mk else "video")


def _remap(m, mapping: dict) -> str:
    """Replace a placeholder anchor with a fresh one pointing at the new file."""
    tag = m.group(0)
    real, kind = _anchor_media(tag)
    if real is None or real not in mapping:
        return tag
    return _media_placeholder(mapping[real], kind)


def _convert_existing():
    col = mw.col
    if not col:
        return
    media_dir = col.media.dir()
    need = {}                                      # real_filename -> kind (distinct)
    try:
        nids = col.find_notes('"local-embed"')
    except Exception:
        nids = []
    if not nids:                                   # safety net against search quirks
        try:
            nids = col.find_notes("")
        except Exception:
            nids = []
    for nid in nids:
        note = col.get_note(nid)
        for field in note.fields:
            for m in _ANCHOR_RE.finditer(field):
                real, kind = _anchor_media(m.group(0))
                if not real or real in need:
                    continue
                path = os.path.join(media_dir, real)
                if not os.path.isfile(path):
                    continue
                ok = _is_web_video(path) if kind == "video" else _is_web_audio(path)
                if not ok:
                    need[real] = kind

    if not need:
        tooltip("No attachments need converting — they all already play inline.", period=4000)
        return

    items = list(need.items())
    n = len(items)
    if not askUser(
            "%d attached file(s) use a format the card webview can't play "
            "(H.264 video / AAC audio).\n\nConvert them now for inline playback? "
            "This runs once and can take a few minutes for long videos.\n\n"
            "(The original files are left in place; run Tools → Check Media later "
            "to clear them.)" % n, title="Media Embed"):
        return

    mapping = {}
    state = {"i": 0}

    def finalize(partial=False):
        if mapping:
            to_update = []
            for nid in nids:                       # same note set found in the scan
                note = col.get_note(nid)
                changed = False
                for idx, field in enumerate(note.fields):
                    newf = _ANCHOR_RE.sub(lambda mm: _remap(mm, mapping), field)
                    if newf != field:
                        note.fields[idx] = newf
                        changed = True
                if changed:
                    to_update.append(note)
            if to_update:
                try:
                    col.update_notes(to_update)
                except Exception as exc:
                    showWarning("Converted files, but couldn't update notes:\n%s" % exc)
        msg = "Converted %d file(s); updated the cards." % len(mapping)
        if partial:
            msg = "Stopped. Converted %d of %d file(s)." % (len(mapping), n)
        tooltip(msg, period=5000)

    def process_next():
        if state["i"] >= n:
            finalize()
            return
        real, kind = items[state["i"]]
        state["i"] += 1
        src = os.path.join(media_dir, real)
        stem = os.path.splitext(real)[0]
        prefix = "(%d/%d) " % (state["i"], n)

        def ok(fn, k, old=real):
            mapping[old] = fn
            process_next()

        def err():
            process_next()                         # skip this one, keep going

        def cancel():
            finalize(partial=True)                 # apply what we have, then stop

        _transcode_async(src, kind, stem, ok, on_error=err, on_cancel=cancel, prefix=prefix)

    process_next()


# ── settings dialog (tuning) ───────────────────────────────────────────────────

class SettingsDialog(QDialog):
    def __init__(self):
        super().__init__(mw)
        self.setWindowTitle("Media Embed Settings")
        self.setMinimumWidth(440)
        c = _cfg()
        form = QFormLayout(self)

        self.crf = QSpinBox()
        self.crf.setRange(18, 45)
        self.crf.setValue(int(c.get("video_crf", 34)))
        form.addRow("Converted-video quality (CRF):", self.crf)
        hint = QLabel("Lower = sharper but larger & slower; higher = smaller & "
                      "faster. 30–38 is a good range (default 34). Applies to "
                      "videos converted from now on.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#888;font-size:11px;")
        form.addRow(hint)

        self.privacy = QCheckBox("Use youtube-nocookie.com (more privacy)")
        self.privacy.setChecked(bool(c.get("youtube_privacy_mode", False)))
        form.addRow(self.privacy)
        note = QLabel("Off (default) uses youtube.com, which lets more videos "
                      "embed — nocookie refuses some.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#888;font-size:11px;")
        form.addRow(note)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _save(self):
        cfg = mw.addonManager.getConfig(ADDON) or {}
        cfg["video_crf"] = self.crf.value()
        cfg["youtube_privacy_mode"] = self.privacy.isChecked()
        mw.addonManager.writeConfig(ADDON, cfg)
        tooltip("Saved.")
        self.accept()


def _add_menu():
    menu = mw.form.menuTools
    a1 = QAction("Media Embed: Convert existing attachments…", mw)
    a1.triggered.connect(_convert_existing)
    menu.addAction(a1)
    a2 = QAction("Media Embed Settings…", mw)
    a2.triggered.connect(lambda: SettingsDialog().exec())
    menu.addAction(a2)


gui_hooks.editor_will_process_mime.append(_on_will_process_mime)
gui_hooks.editor_did_init_buttons.append(_on_editor_buttons)
gui_hooks.reviewer_did_show_question.append(_render_on_card)
gui_hooks.reviewer_did_show_answer.append(_render_on_card)
gui_hooks.webview_did_receive_js_message.append(_on_js_message)
gui_hooks.main_window_did_init.append(_add_menu)
