"""
Clean ChatGPT's pasted HTML at the source.

ChatGPT renders math with KaTeX. Its copied HTML contains, for every equation,
BOTH the visible rendering (``<span class="katex-html">``) and the exact LaTeX
source (``<annotation encoding="application/x-tex">…</annotation>``). Anki's
plain paste keeps both, which is what produced the duplicated "visible + raw
LaTeX" mess.

`clean_katex_html` walks the HTML and replaces each whole ``<span class="katex">``
(or ``katex-display``) with a single ``<anki-mathjax>`` built from the annotation
LaTeX — dropping the duplicated visible text. Everything else (text, <img>,
tables, headings, …) passes through untouched, so images are preserved.
"""

from __future__ import annotations

import html as _html
from html.parser import HTMLParser

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
         "link", "meta", "param", "source", "track", "wbr"}

# Attributes worth keeping on pass-through tags; ChatGPT's inline styles/classes
# are dropped so pasted notes stay lean and adopt the card's own styling.
_KEEP_ATTRS = {"src", "alt", "href", "colspan", "rowspan", "start", "title"}


def _esc(s: str) -> str:
    return _html.escape(s, quote=False)


class _KatexCleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out = []
        self.depth = 0          # span nesting depth inside the current katex root
        self.in_ann = False     # inside <annotation encoding=application/x-tex>
        self.html_level = 0     # depth at which the katex-html (visible) span sits
        self.tex = []           # captured LaTeX
        self.visible = []       # captured visible text (fallback)
        self.block = False      # display (block) equation?

    # ---- reconstruction of pass-through tags --------------------------------
    def _starttag(self, tag, attrs, selfclose=False):
        parts = ["<" + tag]
        for k, v in attrs:
            if k.lower() not in _KEEP_ATTRS:
                continue
            if v is None:
                parts.append(" " + k)
            else:
                parts.append(' %s="%s"' % (k, v.replace("&", "&amp;").replace('"', "&quot;")))
        parts.append("/>" if selfclose else ">")
        return "".join(parts)

    def handle_starttag(self, tag, attrs):
        if self.depth == 0:
            cls = dict(attrs).get("class", "") or ""
            if tag == "span" and "katex" in cls:
                self.depth = 1
                self.in_ann = False
                self.html_level = 0
                self.tex = []
                self.visible = []
                self.block = "katex-display" in cls
                return
            self.out.append(self._starttag(tag, attrs))
            return
        # inside a katex root
        if tag == "span":
            self.depth += 1
            if self.html_level == 0 and "katex-html" in (dict(attrs).get("class", "") or ""):
                self.html_level = self.depth
        elif tag == "annotation" and dict(attrs).get("encoding") == "application/x-tex":
            self.in_ann = True

    def handle_startendtag(self, tag, attrs):
        if self.depth > 0:
            return
        self.out.append(self._starttag(tag, attrs, selfclose=True))

    def handle_endtag(self, tag):
        if self.depth == 0:
            if tag not in _VOID:
                self.out.append("</%s>" % tag)
            return
        if tag == "annotation":
            self.in_ann = False
        if tag == "span":
            self.depth -= 1
            if self.html_level and self.depth < self.html_level:
                self.html_level = 0
            if self.depth == 0:
                self._emit()

    def _emit(self):
        tex = _html.unescape("".join(self.tex)).strip()
        if tex:
            tag = 'anki-mathjax block="true"' if self.block else "anki-mathjax"
            self.out.append("<%s>%s</anki-mathjax>" % (tag, _esc(tex)))
        else:
            vis = _html.unescape("".join(self.visible)).strip()
            if vis:
                self.out.append(_esc(vis))   # no LaTeX found — keep visible text

    def handle_data(self, data):
        if self.depth > 0:
            if self.in_ann:
                self.tex.append(data)
            elif self.html_level:
                self.visible.append(data)
            return
        self.out.append(data)

    def handle_entityref(self, name):
        s = "&%s;" % name
        if self.depth > 0:
            if self.in_ann:
                self.tex.append(s)
            elif self.html_level:
                self.visible.append(s)
            return
        self.out.append(s)

    def handle_charref(self, name):
        s = "&#%s;" % name
        if self.depth > 0:
            if self.in_ann:
                self.tex.append(s)
            elif self.html_level:
                self.visible.append(s)
            return
        self.out.append(s)

    def handle_comment(self, data):
        if self.depth == 0:
            self.out.append("<!--%s-->" % data)


def has_katex(html: str) -> bool:
    return bool(html) and ("katex" in html or "application/x-tex" in html)


def clean_katex_html(html: str) -> str:
    try:
        p = _KatexCleaner()
        p.feed(html)
        p.close()
        return "".join(p.out)
    except Exception:
        return html
