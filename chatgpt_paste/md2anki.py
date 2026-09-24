"""
Markdown (as copied from ChatGPT) → Anki-ready HTML.

Handles: headings, bold/italic/strikethrough, inline & fenced code, inline math
($...$, \\(...\\)) and block math ($$...$$, \\[...\\]) → Anki MathJax delimiters,
pipe tables (with alignment), ordered/unordered nested lists, blockquotes,
horizontal rules, links, and text arrows (->, =>, <->, ...).

Math and code are stashed as opaque tokens before inline formatting runs, so
their contents are never mangled, then restored verbatim at the end.
"""

from __future__ import annotations

import html as _html
import re

_TOKEN_RE = re.compile(r"\x00T\d+\x00")


def _is_token_only(s: str | None) -> bool:
    return bool(s) and re.fullmatch(r"\s*\x00T\d+\x00\s*", s) is not None


def _arrows(s: str) -> str:
    for a, b in (
        ("<=>", "⇔"), ("<->", "↔"), ("-->", "→"), ("==>", "⇒"),
        ("<--", "←"), ("->", "→"), ("=>", "⇒"), ("<-", "←"),
    ):
        s = s.replace(a, b)
    return s


def _inline(s: str) -> str:
    """Inline formatting for a run of text (tokens pass through untouched)."""
    s = _arrows(s)
    s = _html.escape(s, quote=False)
    # links [text](url)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
               lambda m: '<a href="%s">%s</a>' % (m.group(2), m.group(1)), s)
    # bold
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"__(.+?)__", r"<strong>\1</strong>", s)
    # italic (avoid touching bold markers / mid-word underscores)
    s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"<em>\1</em>", s)
    # strikethrough
    s = re.sub(r"~~(.+?)~~", r"<del>\1</del>", s)
    return s


def _split_row(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    cells = re.split(r"(?<!\\)\|", row)
    return [c.strip().replace("\\|", "|") for c in cells]


def _alignments(sep: str) -> list[str]:
    aligns = []
    for c in _split_row(sep):
        c = c.strip()
        left, right = c.startswith(":"), c.endswith(":")
        if left and right:
            aligns.append("center")
        elif right:
            aligns.append("right")
        elif left:
            aligns.append("left")
        else:
            aligns.append("")
    return aligns


def _table(header: str, sep: str, body: list[str]) -> str:
    aligns = _alignments(sep)

    def cell(tag: str, text: str, i: int) -> str:
        align = aligns[i] if i < len(aligns) else ""
        style = "border:1px solid #7a7a9a;padding:5px 9px;"
        if align:
            style += "text-align:%s;" % align
        if tag == "th":
            style += "background:#00000022;font-weight:700;"
        return "<%s style=\"%s\">%s</%s>" % (tag, style, _inline(text), tag)

    out = ["<table style=\"border-collapse:collapse;margin:8px 0;\">"]
    out.append("<thead><tr>")
    for i, c in enumerate(_split_row(header)):
        out.append(cell("th", c, i))
    out.append("</tr></thead><tbody>")
    for line in body:
        out.append("<tr>")
        for i, c in enumerate(_split_row(line)):
            out.append(cell("td", c, i))
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _list(block: list[str]) -> str:
    items: list[dict] = []
    for ln in block:
        m = re.match(r"^([ \t]*)([-*+]|\d+[.)])[ \t]+(.*)$", ln)
        if m:
            indent = len(m.group(1).expandtabs(4))
            ordered = bool(re.match(r"\d+[.)]", m.group(2)))
            items.append({"indent": indent, "ordered": ordered, "text": m.group(3)})
        elif items:
            items[-1]["text"] += "<br>" + ln.strip()

    if not items:
        return ""

    pos = [0]

    def build(level: int) -> str:
        tag = "ol" if items[pos[0]]["ordered"] else "ul"
        out = ["<%s style=\"margin:4px 0;padding-left:22px;\">" % tag]
        while pos[0] < len(items) and items[pos[0]]["indent"] >= level:
            it = items[pos[0]]
            if it["indent"] > level:
                out.append(build(it["indent"]))
                continue
            pos[0] += 1
            li = "<li>" + _inline(it["text"])
            if pos[0] < len(items) and items[pos[0]]["indent"] > level:
                li += build(items[pos[0]]["indent"])
            li += "</li>"
            out.append(li)
        out.append("</%s>" % tag)
        return "".join(out)

    return build(items[0]["indent"])


def _is_special(line: str, nxt: str) -> bool:
    if _is_token_only(line):
        return True
    if re.match(r"^\s*#{1,6}\s+", line):
        return True
    if re.match(r"^\s*([-*_])\s*(\1\s*){2,}$", line):
        return True
    if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
        return True
    if re.match(r"^\s*>\s?", line):
        return True
    if "|" in line and re.match(r"^\s*\|?[\s:|-]*-[\s:|-]*$", nxt or ""):
        return True
    return False


def convert(md: str) -> str:
    if not md:
        return ""
    md = md.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")

    store: dict[str, str] = {}
    counter = [0]

    def stash(value: str) -> str:
        tok = "\x00T%d\x00" % counter[0]
        counter[0] += 1
        store[tok] = value
        return tok

    # 1) fenced code
    md = re.sub(
        r"```[ \t]*[\w+#.-]*\n(.*?)\n?```",
        lambda m: stash('<pre style="background:#00000022;padding:8px;border-radius:6px;'
                        'overflow:auto;"><code>%s</code></pre>' % _html.escape(m.group(1))),
        md, flags=re.DOTALL)

    # Math → Anki's native <anki-mathjax> element (renders in editor AND card).
    def block_math(latex: str) -> str:
        return stash('<anki-mathjax block="true">%s</anki-mathjax>'
                     % _html.escape(latex.strip(), quote=False))

    def inline_math(latex: str) -> str:
        return stash("<anki-mathjax>%s</anki-mathjax>"
                     % _html.escape(latex.strip(), quote=False))

    # 2) block math
    md = re.sub(r"\$\$(.+?)\$\$", lambda m: block_math(m.group(1)), md, flags=re.DOTALL)
    md = re.sub(r"\\\[(.+?)\\\]", lambda m: block_math(m.group(1)), md, flags=re.DOTALL)

    # 3) inline code
    md = re.sub(r"`([^`\n]+?)`",
                lambda m: stash('<code style="background:#00000022;padding:1px 4px;'
                                'border-radius:4px;">%s</code>' % _html.escape(m.group(1))), md)

    # 4) inline math
    md = re.sub(r"\\\((.+?)\\\)", lambda m: inline_math(m.group(1)), md, flags=re.DOTALL)
    md = re.sub(r"(?<!\\)\$(?!\s)([^\n$]+?)(?<!\s)\$",
                lambda m: inline_math(m.group(1)), md)

    lines = md.split("\n")
    parts: list[str] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        if line.strip() == "":
            i += 1
            continue

        if _is_token_only(line):
            parts.append('<div style="margin:8px 0;">%s</div>' % line.strip())
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            lvl = len(m.group(1))
            parts.append('<h%d style="margin:12px 0 6px;">%s</h%d>'
                         % (lvl, _inline(m.group(2)), lvl))
            i += 1
            continue

        if re.match(r"^\s*([-*_])\s*(\1\s*){2,}$", line):
            parts.append('<hr style="border:none;border-top:1px solid #7a7a9a;margin:10px 0;">')
            i += 1
            continue

        nxt = lines[i + 1] if i + 1 < n else ""
        if "|" in line and re.match(r"^\s*\|?[\s:|-]*-[\s:|-]*$", nxt):
            header, sep = line, nxt
            j = i + 2
            body = []
            while j < n and "|" in lines[j] and lines[j].strip():
                body.append(lines[j])
                j += 1
            parts.append(_table(header, sep, body))
            i = j
            continue

        if re.match(r"^\s*>\s?", line):
            quote = []
            while i < n and re.match(r"^\s*>\s?", lines[i]):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = "<br>".join(_inline(q) for q in quote)
            parts.append('<blockquote style="border-left:3px solid #7c3aed;margin:6px 0;'
                         'padding:2px 10px;opacity:.9;">%s</blockquote>' % inner)
            continue

        if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
            block = []
            while i < n and (
                re.match(r"^\s*([-*+]|\d+[.)])\s+", lines[i])
                or (lines[i].strip() and lines[i][:1] in (" ", "\t"))
            ):
                block.append(lines[i])
                i += 1
            parts.append(_list(block))
            continue

        para = []
        while i < n and lines[i].strip() and not _is_special(
            lines[i], lines[i + 1] if i + 1 < n else ""
        ):
            para.append(lines[i])
            i += 1
        parts.append('<div style="margin:0 0 8px;">%s</div>'
                     % "<br>".join(_inline(p) for p in para))

    result = "\n".join(parts)
    for tok, val in store.items():
        result = result.replace(tok, val)
    return result
