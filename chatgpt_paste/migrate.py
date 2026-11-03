"""
Tag-safe migration / repair of note fields for un-rendered or mis-rendered LaTeX.

Passes (all idempotent, all HTML-tag-safe — they never let an equation swallow
following markup):

  1. _unswallow      – undo earlier damage: pull HTML that got trapped (escaped)
                       inside an <anki-mathjax> element back out.
  2. _render_delims  – convert delimiter math \\[…\\] \\(…\\) $$…$$ to <anki-mathjax>.
  3. _wrap_bare      – wrap bare, un-delimited LaTeX (\\text{…}, \\boxed{…}, …) that
                       sits inside a text node, bounded by tags so nothing else is
                       absorbed; a pure \\text{…} run becomes plain words.
  4. _dedup          – remove plain text immediately before an <anki-mathjax> when
                       it is just the duplicated rendering of that equation.
"""

from __future__ import annotations

import html as _html
import re

# ── shared helpers ─────────────────────────────────────────────────────────────

_LATEX_CMD = re.compile(
    r"\\(?:text|boxed|frac|sqrt|rightarrow|leftarrow|Rightarrow|Leftarrow|"
    r"leftrightarrow|to|uparrow|downarrow|times|div|pm|mp|leq|geq|neq|approx|"
    r"equiv|propto|cdot|circ|sim|infty|sum|int|prod|partial|nabla|forall|exists|"
    r"alpha|beta|gamma|delta|Delta|theta|lambda|mu|sigma|Sigma|omega|Omega|"
    r"overline|underline|hat|bar|vec|mathbf|mathrm|mathit|left|right|degree|"
    r"angle|perp|parallel|log|ln|sin|cos|tan|lim)\b"
)

_SUBSUP = str.maketrans("₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹", "01234567890123456789")

_SYMS = {"rightarrow": "→", "to": "→", "leftarrow": "←", "uparrow": "↑",
         "downarrow": "↓", "Rightarrow": "⇒", "times": "×", "div": "÷",
         "pm": "±", "leq": "≤", "geq": "≥", "neq": "≠", "approx": "≈",
         "cdot": "·", "circ": "∘", "degree": "°"}

_MJ_SPLIT = re.compile(r"(<anki-mathjax[^>]*>.*?</anki-mathjax>)", re.DOTALL)
_MJ_MATCH = re.compile(r"<anki-mathjax([^>]*)>(.*?)</anki-mathjax>", re.DOTALL)
_TAG_SPLIT = re.compile(r"(<[^>]+>)")
_ESC_TAG = re.compile(r"&lt;/?[a-zA-Z][^&]*?&gt;")


def _esc(s: str) -> str:
    return _html.escape(s, quote=False)


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", _html.unescape(s).translate(_SUBSUP).lower())


def _latex_to_plain(latex: str) -> str:
    s = re.sub(r"\\text\{([^{}]*)\}", r"\1", latex)
    s = re.sub(r"\\boxed\{(.*)\}", r"\1", s, flags=re.DOTALL)
    for cmd, ch in _SYMS.items():
        s = s.replace("\\" + cmd, ch)
    s = re.sub(r"\\[a-zA-Z]+", " ", s)
    s = s.replace("{", "").replace("}", "").replace("_", "").replace("^", "")
    return re.sub(r"\s+", " ", s).strip()


def _dedup_cut(prefix: str, plain: str) -> str:
    """Trim the tail of `prefix` iff it is the duplicated plain rendering of the
    equation; otherwise return `prefix` unchanged (never over-trims).
    Entity-safe: comparison is on the normalised (unescaped) form, and the cut
    is the largest suffix of the original prefix that normalises to the plain."""
    target = _norm(plain)
    if not target or not _norm(prefix).endswith(target):
        return prefix
    # Largest p (keep as much real prefix as possible, incl. separators) whose
    # suffix still normalises to exactly the duplicated plain text.
    for p in range(len(prefix), -1, -1):
        if _norm(prefix[p:]) == target:
            return prefix[:p]
    return prefix


# ── pass 1: un-swallow trapped HTML ────────────────────────────────────────────

def _unswallow(field: str) -> str:
    def fix(m):
        attrs, content = m.group(1), m.group(2)
        tm = _ESC_TAG.search(content)          # first *escaped HTML tag* inside math
        if not tm:
            return m.group(0)                   # genuine equation (e.g. "&lt; 7") — leave
        math = content[:tm.start()]
        rest = _html.unescape(content[tm.start():])
        if not math.strip():
            return rest
        return "<anki-mathjax%s>%s</anki-mathjax>%s" % (attrs, math, rest)

    prev = None
    while prev != field:
        prev = field
        field = _MJ_MATCH.sub(fix, field)
    return field


# ── pass 2: delimiter math ─────────────────────────────────────────────────────

def _render_delims(field: str) -> str:
    def block(m):
        return '<anki-mathjax block="true">%s</anki-mathjax>' % _esc(m.group(1).strip())

    def inline(m):
        return "<anki-mathjax>%s</anki-mathjax>" % _esc(m.group(1).strip())

    field = re.sub(r"\$\$(.+?)\$\$", block, field, flags=re.DOTALL)
    field = re.sub(r"\\\[(.+?)\\\]", block, field, flags=re.DOTALL)
    field = re.sub(r"\\\((.+?)\\\)", inline, field, flags=re.DOTALL)
    return field


# ── pass 3: bare LaTeX, bounded to text nodes ──────────────────────────────────

# Characters allowed to sit between commands inside one LaTeX expression.
_RUN_CHARS = set(" \t0123456789+-*/=(),.:;^_<>|%!?'\""
                 "→←↑↓⇒⇔≤≥≠≈±×÷·∘°√∞")


def _match_brace(text: str, j: int) -> int:
    depth = 0
    n = len(text)
    while j < n:
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return j


def _consume_latex_run(text: str, start: int) -> int:
    """Return the index just past a maximal LaTeX expression beginning at
    `start`. Stops at a bare (plain-text) word or an HTML entity — so two
    separate boxed equations with prose between them are NOT merged."""
    n = len(text)
    j = start
    while j < n:
        c = text[j]
        if c == "\\":                     # a command: \word (or \, \\ etc.)
            k = j + 1
            while k < n and text[k].isalpha():
                k += 1
            j = k if k > j + 1 else j + 2
            continue
        if c == "{":
            j = _match_brace(text, j)
            continue
        if c in _RUN_CHARS:
            j += 1
            continue
        break                             # bare letter / '&' entity → run ends
    return j


def _iter_segments(text: str):
    """Split a text node into alternating ('plain', str) / ('latex', str)."""
    segs = []
    i, n = 0, len(text)
    while i < n:
        m = _LATEX_CMD.search(text, i)
        if not m:
            segs.append(("plain", text[i:]))
            break
        if m.start() > i:
            segs.append(("plain", text[i:m.start()]))
        j = _consume_latex_run(text, m.start())
        segs.append(("latex", text[m.start():j]))
        i = j
    return segs


def _is_pure_text(latex: str) -> bool:
    return re.sub(r"\s+", "", re.sub(r"\\text\{[^{}]*\}", "", latex)) == ""


def _process_text_node(node: str) -> str:
    if "\\" not in node:
        return node
    segs = _iter_segments(node)
    if not any(k == "latex" for k, _ in segs):
        return node
    out = []
    for idx, (kind, val) in enumerate(segs):
        if kind == "plain":
            # drop a plain run that just duplicates the equation right after it
            if idx + 1 < len(segs) and segs[idx + 1][0] == "latex":
                val = _dedup_cut(val, _latex_to_plain(segs[idx + 1][1]))
            out.append(val)
        else:
            latex = val.strip()
            if _is_pure_text(latex):
                out.append(_latex_to_plain(latex))
            else:
                out.append("<anki-mathjax>%s</anki-mathjax>" % _esc(latex))
    return "".join(out)


def _wrap_bare(field: str) -> str:
    segs = _MJ_SPLIT.split(field)
    for si in range(0, len(segs), 2):           # segments outside <anki-mathjax>
        seg = segs[si]
        if "\\" not in seg:
            continue
        toks = _TAG_SPLIT.split(seg)
        for ti in range(0, len(toks), 2):       # text nodes (no HTML tags inside)
            toks[ti] = _process_text_node(toks[ti])
        segs[si] = "".join(toks)
    return "".join(segs)


# ── pass 3b: inline sub/superscript duplication (CO2CO_2 → CO_2) ───────────────

# A contiguous "formula" run containing at least one subscript/superscript,
# e.g. CO2CO_2, H2OH_2O, Na+Na^+, Ca2+Ca^{2+} — no backslash command, so
# pass 3 misses it. The duplication signature: with _ ^ { } removed the run is
# a *doubled* string (visible + LaTeX-stripped), e.g. CO2CO_2 -> CO2CO2.
_SUBSUP_UNIT = re.compile(r"[A-Za-z0-9+\-_^{}]*[_^][A-Za-z0-9+\-_^{}]*")


def _dedup_inline_subsup(text: str) -> str:
    if "_" not in text and "^" not in text:
        return text

    def fix(m):
        tok = m.group(0)
        stripped = re.sub(r"[_^{}]", "", tok)
        h = len(stripped) // 2
        if len(stripped) >= 4 and len(stripped) % 2 == 0 and stripped[:h] == stripped[h:] \
                and re.search(r"[A-Za-z]", stripped[:h]):
            latex = tok[h:]                       # second half keeps the markup
            if "_" in latex or "^" in latex:
                return "<anki-mathjax>%s</anki-mathjax>" % _esc(latex)
        return tok

    return _SUBSUP_UNIT.sub(fix, text)


def _dedup_subsup(field: str) -> str:
    segs = _MJ_SPLIT.split(field)
    for si in range(0, len(segs), 2):                    # outside <anki-mathjax>
        seg = segs[si]
        if "_" not in seg and "^" not in seg:
            continue
        toks = _TAG_SPLIT.split(seg)
        for ti in range(0, len(toks), 2):                # text nodes only
            toks[ti] = _dedup_inline_subsup(toks[ti])
        segs[si] = "".join(toks)
    return "".join(segs)


# ── pass 4: remove duplicated plain text before an equation ────────────────────

def _dedup(field: str) -> str:
    def fix(m):
        before, br, attrs, latex = m.group(1), m.group(2) or "", m.group(3), m.group(4)
        plain = _latex_to_plain(_html.unescape(latex))
        return _dedup_cut(before, plain) + br + "<anki-mathjax%s>%s</anki-mathjax>" % (attrs, latex)

    # optional <br> between the duplicated plain text and the equation
    return re.sub(r"([^<>]*)(<br\s*/?>)?<anki-mathjax([^>]*)>(.*?)</anki-mathjax>",
                  fix, field, flags=re.DOTALL)


# ── pass 1b: split an <anki-mathjax> that wrongly holds 2+ equations ────────────

def _repair_mathjax(field: str) -> str:
    def fix(m):
        attrs, content = m.group(1), m.group(2)
        raw = _html.unescape(content)
        segs = _iter_segments(raw)
        latex_count = sum(1 for k, _ in segs if k == "latex")
        # Only touch clearly mis-wrapped elements (two+ separate equations).
        # A single equation — however unusual — is left exactly as it is.
        if latex_count < 2:
            return m.group(0)
        return _process_text_node(raw)

    return _MJ_MATCH.sub(fix, field)


# ── public ─────────────────────────────────────────────────────────────────────

def migrate_field(field: str) -> str:
    out = _unswallow(field)
    out = _repair_mathjax(out)
    out = _render_delims(out)
    out = _wrap_bare(out)
    out = _dedup_subsup(out)
    out = _dedup(out)
    return out
