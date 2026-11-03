"""
Import a ChatGPT *share link* (chatgpt.com/share/…) straight into the current
card — the note text AND every image.

ChatGPT's clipboard copy leaves images out, but the shared *page* contains them.
The page is a React app, so the raw HTML is just a data blob; we therefore render
it in a hidden Chromium page (Anki already ships QtWebEngine), wait for the note
to finish rendering, and pull the finished `.markdown` HTML — clean text with the
images as real `<img src="https://…">`. That HTML is handed back to the normal
renderer in __init__.py, which downloads every image into the collection and
inserts the whole note at the cursor (with the usual progress dialog).
"""

from __future__ import annotations

import re

from aqt import mw
from aqt.qt import QTimer, QUrl

try:
    from aqt.qt import QWebEnginePage
except Exception:  # pragma: no cover - fallback for odd Qt packagings
    from PyQt6.QtWebEngineCore import QWebEnginePage

SHARE_RE = re.compile(r"https?://chatgpt\.com/share/[A-Za-z0-9\-]+")

# Clone the note container and return clean inner HTML. ChatGPT wraps each
# (carousel) image in a <button>, so we UNWRAP buttons that contain an image and
# only remove the image-less UI buttons — otherwise every picture would be lost.
_EXTRACT_JS = r"""
(function () {
  var m = document.querySelector('.markdown');
  if (!m) return "";
  var c = m.cloneNode(true);
  c.querySelectorAll('button').forEach(function (b) {
    var imgs = b.querySelectorAll('img');
    if (imgs.length) { b.replaceWith.apply(b, imgs); } else { b.remove(); }
  });
  c.querySelectorAll('svg, noscript, style, script').forEach(function (e) { e.remove(); });
  return c.innerHTML;
})()
"""

_LEN_JS = r"""
(function () { var m = document.querySelector('.markdown'); return m ? m.innerHTML.length : 0; })()
"""

# Keep renderers alive until they finish (otherwise they'd be GC'd mid-load).
_active = set()


class _Renderer:
    def __init__(self, url, on_done, on_fail):
        self._on_done = on_done
        self._on_fail = on_fail
        self._last = -1
        self._stable = 0
        self._ticks = 0
        self._finished = False
        _active.add(self)
        self.page = QWebEnginePage(mw)
        self.page.loadFinished.connect(self._loaded)
        self.timer = QTimer(mw)
        self.timer.setInterval(600)
        self.timer.timeout.connect(self._poll)
        self.page.setUrl(QUrl(url))

    def _loaded(self, ok):
        if self._finished:
            return
        if not ok:
            self._fail("The page couldn't be loaded. Check the link and your internet connection.")
            return
        self.timer.start()                      # poll until the React content appears

    def _poll(self):
        if self._finished:
            return
        self._ticks += 1
        if self._ticks > 50:                    # ~30s hard cap
            if self._last > 500:
                self._grab()
            else:
                self._fail("The note didn't finish loading in time. Please try again.")
            return
        self.page.runJavaScript(_LEN_JS, self._len)

    def _len(self, n):
        if self._finished:
            return
        try:
            n = int(n or 0)
        except Exception:
            n = 0
        if n > 500:                             # content present; wait until it stops growing
            self._stable = self._stable + 1 if n == self._last else 0
            self._last = n
            if self._stable >= 2:
                self._grab()
        else:
            self._last = n

    def _grab(self):
        if self._finished:
            return
        self.timer.stop()
        self.page.runJavaScript(_EXTRACT_JS, self._done)

    def _done(self, html):
        if self._finished:
            return
        self._finished = True
        self._cleanup()
        if html and len(html) > 200:
            self._on_done(html)
        else:
            self._on_fail("No note content was found at that link.")

    def _fail(self, msg):
        if self._finished:
            return
        self._finished = True
        self._cleanup()
        self._on_fail(msg)

    def _cleanup(self):
        try:
            self.timer.stop()
        except Exception:
            pass
        try:
            self.page.deleteLater()
        except Exception:
            pass
        _active.discard(self)


def render(url: str, on_done, on_fail):
    """Render `url` in a hidden page and call on_done(raw_html) / on_fail(msg)."""
    _Renderer(url, on_done, on_fail)
