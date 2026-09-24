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

def _wrap_bare(field: str) -> str:
    segs = _MJ_SPLIT.split(field)
    for si in range(0, len(segs), 2):           # segments outside <anki-mathjax>
        seg = segs[si]
        if "\\" not in seg:
            continue
        toks = _TAG_SPLIT.split(seg)
        for ti in range(0, len(toks), 2):       # text nodes (no HTML tags inside)
            node = toks[ti]
            if "\\" not in node:
                continue
            m = _LATEX_CMD.search(node)
            if not m:
                continue
            s = m.start()
            latex = node[s:].strip()            # bounded by the text node → tag-safe
            prefix = _dedup_cut(node[:s], _latex_to_plain(latex))
            pure = re.sub(r"\s+", "", re.sub(r"\\text\{[^{}]*\}", "", latex)) == ""
            repl = _latex_to_plain(latex) if pure else "<anki-mathjax>%s</anki-mathjax>" % _esc(latex)
            toks[ti] = prefix + repl
        segs[si] = "".join(toks)
    return "".join(segs)


# ── pass 4: remove duplicated plain text before an equation ────────────────────

def _dedup(field: str) -> str:
    def fix(m):
        before, attrs, latex = m.group(1), m.group(2), m.group(3)
        plain = _latex_to_plain(_html.unescape(latex))
        return _dedup_cut(before, plain) + "<anki-mathjax%s>%s</anki-mathjax>" % (attrs, latex)

    return re.sub(r"([^<>]*)<anki-mathjax([^>]*)>(.*?)</anki-mathjax>",
                  fix, field, flags=re.DOTALL)


# ── public ─────────────────────────────────────────────────────────────────────

def migrate_field(field: str) -> str:
    out = _unswallow(field)
    out = _render_delims(out)
    out = _wrap_bare(out)
    out = _dedup(out)
    return out
