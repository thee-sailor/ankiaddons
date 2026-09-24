"""
Anki Theme Switcher — 20 themes.
- Red-X regions: fully transparent so background image shows through.
- Blue stats widgets: 6 distinct attractive colors per theme.
- Deck container: frosted glass with theme accent.
"""

import json, os, shutil
from datetime import date
from aqt import mw, gui_hooks
from aqt.deckbrowser import DeckBrowser

# ── Daily background rotation ─────────────────────────────────
_BG_CONFIG = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', '1210908941', 'config.json'
))
_BG_FOLDER = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', '1210908941', 'user_files', 'background'
))
_BG_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

def _rotate_background():
    try:
        # Read folder fresh each time — picks up any added/removed images
        images = sorted(
            f for f in os.listdir(_BG_FOLDER)
            if os.path.splitext(f)[1].lower() in _BG_EXTS
        )
        if not images:
            return
        today_image = images[date.today().toordinal() % len(images)]
        with open(_BG_CONFIG, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        cfg['Image name for background'] = today_image
        with open(_BG_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

# ── Daily deck icon rotation ──────────────────────────────────
_ICONS_SRC = os.path.join(
    os.path.dirname(__file__), '..', '1116770498',
    'user_files', 'assets', 'deck_icons'
)
_ICON_NAMES = [
    'Bam', 'Bullseye', 'Cowboy', 'Diamond', 'Dragon',
    'Fire', 'Flower', 'Nerd', 'Rose', 'Shield',
    'Star', 'Sun', 'YinYang',
]

def _rotate_deck_icon():
    try:
        icons_dir = os.path.normpath(_ICONS_SRC)
        day_index = date.today().toordinal() % len(_ICON_NAMES)
        icon_name = _ICON_NAMES[day_index]
        src = os.path.join(icons_dir, f'{icon_name}.png')
        dst = os.path.join(icons_dir, 'default.png')
        if os.path.exists(src):
            shutil.copy2(src, dst)
    except Exception:
        pass

_CFG = os.path.join(os.path.dirname(__file__), 'theme.json')

# ── Theme definitions ─────────────────────────────────────────
# surface   – deck table frosted-glass bg (semi-transparent)
# border    – deck row separator
# text      – deck link color
# text_zero – zero-count dimmed color
# text_filt – filtered deck color
# gear      – gear SVG fill
# rev_bg/fg – review badge
# new_bg/fg – new badge
# w_text    – widget text
# w[0..5]   – 6 widget bg colors: Studied, Avg, Remain, New, Due, Total
# btn_bg/fg – bottom bar button

THEMES = {
"Midnight Purple": dict(
    swatch="#7c3aed",
    surface="rgba(20,10,50,0.72)",  border="rgba(167,139,250,0.25)",
    text="#c4b5fd", text_zero="rgba(167,139,250,0.35)", text_filt="#f0abfc",
    gear="#a78bfa",
    rev_bg="rgba(139,92,246,0.85)",  rev_fg="#fff",
    new_bg="rgba(99,102,241,0.85)",  new_fg="#fff",
    w_text="#fff",
    w=["rgba(109,40,217,0.88)","rgba(236,72,153,0.82)","rgba(239,68,68,0.82)",
       "rgba(59,130,246,0.82)","rgba(16,185,129,0.82)","rgba(245,158,11,0.82)"],
    btn_bg="rgba(109,40,217,0.9)", btn_fg="#fff",
),
"Ocean Blue": dict(
    swatch="#0ea5e9",
    surface="rgba(2,20,45,0.72)",   border="rgba(56,189,248,0.25)",
    text="#7dd3fc", text_zero="rgba(56,189,248,0.35)", text_filt="#fbbf24",
    gear="#38bdf8",
    rev_bg="rgba(14,165,233,0.85)", rev_fg="#fff",
    new_bg="rgba(6,182,212,0.85)",  new_fg="#fff",
    w_text="#fff",
    w=["rgba(2,132,199,0.88)","rgba(8,145,178,0.85)","rgba(236,72,153,0.82)",
       "rgba(34,197,94,0.82)","rgba(245,158,11,0.82)","rgba(139,92,246,0.82)"],
    btn_bg="rgba(14,165,233,0.9)", btn_fg="#fff",
),
"Forest Green": dict(
    swatch="#16a34a",
    surface="rgba(3,22,10,0.72)",   border="rgba(74,222,128,0.25)",
    text="#86efac", text_zero="rgba(74,222,128,0.35)", text_filt="#fde68a",
    gear="#4ade80",
    rev_bg="rgba(22,163,74,0.85)",  rev_fg="#fff",
    new_bg="rgba(5,150,105,0.85)",  new_fg="#fff",
    w_text="#fff",
    w=["rgba(21,128,61,0.88)","rgba(6,148,162,0.85)","rgba(245,158,11,0.82)",
       "rgba(99,102,241,0.82)","rgba(236,72,153,0.82)","rgba(139,92,246,0.82)"],
    btn_bg="rgba(22,163,74,0.9)", btn_fg="#fff",
),
"Crimson Dark": dict(
    swatch="#dc2626",
    surface="rgba(35,5,8,0.72)",    border="rgba(252,165,165,0.25)",
    text="#fca5a5", text_zero="rgba(252,165,165,0.35)", text_filt="#fcd34d",
    gear="#f87171",
    rev_bg="rgba(220,38,38,0.85)",  rev_fg="#fff",
    new_bg="rgba(190,18,60,0.85)",  new_fg="#fff",
    w_text="#fff",
    w=["rgba(185,28,28,0.88)","rgba(194,65,12,0.85)","rgba(245,158,11,0.82)",
       "rgba(124,58,237,0.82)","rgba(14,165,233,0.82)","rgba(22,163,74,0.82)"],
    btn_bg="rgba(220,38,38,0.9)", btn_fg="#fff",
),
"Golden Hour": dict(
    swatch="#d97706",
    surface="rgba(30,15,0,0.72)",   border="rgba(251,191,36,0.25)",
    text="#fcd34d", text_zero="rgba(251,191,36,0.35)", text_filt="#f0abfc",
    gear="#fbbf24",
    rev_bg="rgba(217,119,6,0.85)",  rev_fg="#fff",
    new_bg="rgba(180,83,9,0.85)",   new_fg="#fff",
    w_text="#fff",
    w=["rgba(180,83,9,0.88)","rgba(220,38,38,0.85)","rgba(139,92,246,0.82)",
       "rgba(14,165,233,0.82)","rgba(22,163,74,0.82)","rgba(190,18,60,0.82)"],
    btn_bg="rgba(217,119,6,0.9)", btn_fg="#fff",
),
"Arctic Ice": dict(
    swatch="#22d3ee",
    surface="rgba(3,20,35,0.72)",   border="rgba(103,232,249,0.25)",
    text="#a5f3fc", text_zero="rgba(103,232,249,0.35)", text_filt="#fde68a",
    gear="#67e8f9",
    rev_bg="rgba(6,182,212,0.85)",  rev_fg="#fff",
    new_bg="rgba(8,145,178,0.85)",  new_fg="#fff",
    w_text="#fff",
    w=["rgba(6,182,212,0.88)","rgba(99,102,241,0.85)","rgba(236,72,153,0.82)",
       "rgba(22,163,74,0.82)","rgba(245,158,11,0.82)","rgba(139,92,246,0.82)"],
    btn_bg="rgba(6,182,212,0.9)", btn_fg="#fff",
),
"Rose Gold": dict(
    swatch="#f43f8e",
    surface="rgba(30,5,18,0.72)",   border="rgba(249,168,212,0.25)",
    text="#fbcfe8", text_zero="rgba(249,168,212,0.35)", text_filt="#fde68a",
    gear="#f9a8d4",
    rev_bg="rgba(244,63,142,0.85)", rev_fg="#fff",
    new_bg="rgba(168,85,247,0.85)", new_fg="#fff",
    w_text="#fff",
    w=["rgba(219,39,119,0.88)","rgba(245,158,11,0.85)","rgba(139,92,246,0.82)",
       "rgba(14,165,233,0.82)","rgba(22,163,74,0.82)","rgba(239,68,68,0.82)"],
    btn_bg="rgba(244,63,142,0.9)", btn_fg="#fff",
),
"Cyberpunk": dict(
    swatch="#facc15",
    surface="rgba(8,0,28,0.78)",    border="rgba(250,204,21,0.30)",
    text="#facc15", text_zero="rgba(250,204,21,0.30)", text_filt="#f0abfc",
    gear="#facc15",
    rev_bg="rgba(250,204,21,0.90)", rev_fg="#000",
    new_bg="rgba(168,85,247,0.85)", new_fg="#fff",
    w_text="#fff",
    w=["rgba(109,40,217,0.88)","rgba(250,204,21,0.75)","rgba(236,72,153,0.82)",
       "rgba(6,182,212,0.82)","rgba(239,68,68,0.82)","rgba(34,197,94,0.72)"],
    btn_bg="rgba(250,204,21,0.95)", btn_fg="#000",
),
"Dracula": dict(
    swatch="#bd93f9",
    surface="rgba(40,42,54,0.80)",  border="rgba(98,114,164,0.50)",
    text="#f8f8f2", text_zero="rgba(98,114,164,0.60)", text_filt="#ffb86c",
    gear="#6272a4",
    rev_bg="rgba(189,147,249,0.85)", rev_fg="#282a36",
    new_bg="rgba(80,250,123,0.75)",  new_fg="#282a36",
    w_text="#f8f8f2",
    w=["rgba(189,147,249,0.80)","rgba(255,184,108,0.80)","rgba(255,85,85,0.80)",
       "rgba(80,250,123,0.70)","rgba(139,233,253,0.70)","rgba(255,121,198,0.80)"],
    btn_bg="rgba(189,147,249,0.9)", btn_fg="#282a36",
),
"Nord": dict(
    swatch="#88c0d0",
    surface="rgba(46,52,64,0.78)",  border="rgba(76,86,106,0.55)",
    text="#eceff4", text_zero="rgba(76,86,106,0.70)", text_filt="#ebcb8b",
    gear="#7b8fa6",
    rev_bg="rgba(136,192,208,0.80)", rev_fg="#2e3440",
    new_bg="rgba(94,129,172,0.80)",  new_fg="#eceff4",
    w_text="#eceff4",
    w=["rgba(94,129,172,0.85)","rgba(235,203,139,0.80)","rgba(191,97,106,0.80)",
       "rgba(163,190,140,0.80)","rgba(136,192,208,0.75)","rgba(180,142,173,0.80)"],
    btn_bg="rgba(136,192,208,0.9)", btn_fg="#2e3440",
),
"Solarized Dark": dict(
    swatch="#268bd2",
    surface="rgba(0,43,54,0.80)",   border="rgba(38,139,210,0.25)",
    text="#93a1a1", text_zero="rgba(88,110,117,0.70)", text_filt="#b58900",
    gear="#586e75",
    rev_bg="rgba(38,139,210,0.85)", rev_fg="#fdf6e3",
    new_bg="rgba(42,161,152,0.85)", new_fg="#fdf6e3",
    w_text="#fdf6e3",
    w=["rgba(38,139,210,0.85)","rgba(203,75,22,0.85)","rgba(220,50,47,0.82)",
       "rgba(38,139,210,0.75)","rgba(133,153,0,0.82)","rgba(108,113,196,0.82)"],
    btn_bg="rgba(38,139,210,0.9)", btn_fg="#fdf6e3",
),
"Tokyo Night": dict(
    swatch="#7aa2f7",
    surface="rgba(26,27,46,0.78)",  border="rgba(65,72,104,0.60)",
    text="#c0caf5", text_zero="rgba(59,66,97,0.80)", text_filt="#e0af68",
    gear="#565f89",
    rev_bg="rgba(122,162,247,0.85)", rev_fg="#1a1b2e",
    new_bg="rgba(158,206,106,0.75)", new_fg="#1a1b2e",
    w_text="#c0caf5",
    w=["rgba(122,162,247,0.82)","rgba(224,175,104,0.82)","rgba(247,118,142,0.82)",
       "rgba(158,206,106,0.75)","rgba(125,207,255,0.75)","rgba(187,154,247,0.82)"],
    btn_bg="rgba(122,162,247,0.9)", btn_fg="#1a1b2e",
),
"Monokai": dict(
    swatch="#a6e22e",
    surface="rgba(39,40,34,0.80)",  border="rgba(117,113,94,0.45)",
    text="#f8f8f2", text_zero="rgba(117,113,94,0.65)", text_filt="#e6db74",
    gear="#75715e",
    rev_bg="rgba(166,226,46,0.80)",  rev_fg="#272822",
    new_bg="rgba(102,217,239,0.70)", new_fg="#272822",
    w_text="#f8f8f2",
    w=["rgba(166,226,46,0.72)","rgba(230,219,116,0.75)","rgba(249,38,114,0.78)",
       "rgba(102,217,239,0.68)","rgba(166,226,46,0.68)","rgba(174,129,255,0.75)"],
    btn_bg="rgba(166,226,46,0.9)", btn_fg="#272822",
),
"Gruvbox": dict(
    swatch="#fe8019",
    surface="rgba(40,40,40,0.80)",  border="rgba(168,153,132,0.35)",
    text="#ebdbb2", text_zero="rgba(80,73,69,0.80)", text_filt="#fabd2f",
    gear="#928374",
    rev_bg="rgba(254,128,25,0.85)", rev_fg="#282828",
    new_bg="rgba(131,165,152,0.80)",new_fg="#282828",
    w_text="#ebdbb2",
    w=["rgba(215,153,33,0.82)","rgba(214,93,14,0.82)","rgba(204,36,29,0.82)",
       "rgba(69,133,136,0.80)","rgba(152,151,26,0.80)","rgba(177,98,134,0.82)"],
    btn_bg="rgba(254,128,25,0.9)", btn_fg="#282828",
),
"Catppuccin": dict(
    swatch="#cba6f7",
    surface="rgba(30,30,46,0.78)",  border="rgba(88,91,112,0.45)",
    text="#cdd6f4", text_zero="rgba(88,91,112,0.70)", text_filt="#f9e2af",
    gear="#6c7086",
    rev_bg="rgba(203,166,247,0.85)", rev_fg="#1e1e2e",
    new_bg="rgba(166,227,161,0.75)", new_fg="#1e1e2e",
    w_text="#cdd6f4",
    w=["rgba(203,166,247,0.82)","rgba(250,179,135,0.82)","rgba(243,139,168,0.82)",
       "rgba(166,227,161,0.75)","rgba(137,220,235,0.75)","rgba(180,190,254,0.82)"],
    btn_bg="rgba(203,166,247,0.9)", btn_fg="#1e1e2e",
),
"One Dark": dict(
    swatch="#61afef",
    surface="rgba(40,44,52,0.78)",  border="rgba(92,99,112,0.45)",
    text="#abb2bf", text_zero="rgba(62,68,81,0.80)", text_filt="#e5c07b",
    gear="#5c6370",
    rev_bg="rgba(97,175,239,0.85)",  rev_fg="#282c34",
    new_bg="rgba(152,195,121,0.75)", new_fg="#282c34",
    w_text="#abb2bf",
    w=["rgba(97,175,239,0.82)","rgba(229,192,123,0.82)","rgba(224,108,117,0.82)",
       "rgba(152,195,121,0.75)","rgba(86,182,194,0.75)","rgba(198,120,221,0.82)"],
    btn_bg="rgba(97,175,239,0.9)", btn_fg="#282c34",
),
"Material Dark": dict(
    swatch="#82aaff",
    surface="rgba(15,20,38,0.78)",  border="rgba(55,65,110,0.55)",
    text="#eeffff", text_zero="rgba(45,50,80,0.80)", text_filt="#ffcb6b",
    gear="#546e7a",
    rev_bg="rgba(130,170,255,0.85)", rev_fg="#0a0e1a",
    new_bg="rgba(195,232,141,0.75)", new_fg="#0a0e1a",
    w_text="#eeffff",
    w=["rgba(130,170,255,0.82)","rgba(255,203,107,0.82)","rgba(255,85,114,0.82)",
       "rgba(195,232,141,0.75)","rgba(137,221,255,0.75)","rgba(199,146,234,0.82)"],
    btn_bg="rgba(130,170,255,0.9)", btn_fg="#0a0e1a",
),
"Synthwave": dict(
    swatch="#ff7edb",
    surface="rgba(15,0,30,0.82)",   border="rgba(255,126,219,0.28)",
    text="#ff7edb", text_zero="rgba(255,126,219,0.28)", text_filt="#36f9f6",
    gear="#ff7edb",
    rev_bg="rgba(255,126,219,0.82)", rev_fg="#0d0013",
    new_bg="rgba(54,249,246,0.45)",  new_fg="#fff",
    w_text="#fff",
    w=["rgba(120,0,180,0.88)","rgba(255,126,219,0.55)","rgba(255,50,100,0.75)",
       "rgba(54,249,246,0.45)","rgba(255,200,0,0.65)","rgba(80,0,160,0.88)"],
    btn_bg="rgba(255,126,219,0.9)", btn_fg="#0d0013",
),
"Emerald": dict(
    swatch="#10b981",
    surface="rgba(3,18,10,0.75)",   border="rgba(52,211,153,0.25)",
    text="#6ee7b7", text_zero="rgba(52,211,153,0.30)", text_filt="#fde68a",
    gear="#34d399",
    rev_bg="rgba(16,185,129,0.85)", rev_fg="#fff",
    new_bg="rgba(5,150,105,0.85)",  new_fg="#fff",
    w_text="#fff",
    w=["rgba(6,148,162,0.85)","rgba(245,158,11,0.82)","rgba(239,68,68,0.82)",
       "rgba(99,102,241,0.82)","rgba(16,185,129,0.82)","rgba(168,85,247,0.80)"],
    btn_bg="rgba(16,185,129,0.9)", btn_fg="#fff",
),
"Ayu Dark": dict(
    swatch="#e6b450",
    surface="rgba(13,16,23,0.80)",  border="rgba(61,74,90,0.60)",
    text="#bfbdb6", text_zero="rgba(45,50,68,0.80)", text_filt="#e6b450",
    gear="#3d4a5c",
    rev_bg="rgba(230,180,80,0.85)", rev_fg="#0d1017",
    new_bg="rgba(57,186,230,0.80)", new_fg="#0d1017",
    w_text="#bfbdb6",
    w=["rgba(57,186,230,0.82)","rgba(230,180,80,0.82)","rgba(255,117,0,0.82)",
       "rgba(147,199,153,0.75)","rgba(57,186,230,0.72)","rgba(210,100,230,0.75)"],
    btn_bg="rgba(230,180,80,0.9)", btn_fg="#0d1017",
),
}

# ── Persistence ───────────────────────────────────────────────

def _load_theme() -> str:
    try:
        with open(_CFG, 'r', encoding='utf-8') as f:
            name = json.load(f)['theme']
        return name if name in THEMES else 'Midnight Purple'
    except Exception:
        return 'Midnight Purple'

def _save_theme(name: str):
    with open(_CFG, 'w', encoding='utf-8') as f:
        json.dump({'theme': name}, f)

_current = _load_theme()

# ── CSS + JS builder ──────────────────────────────────────────

def _build_js(t: dict) -> str:
    w = t['w']
    widget_colors = json.dumps(w)

    css = f"""
/* ── Transparent regions: let background image breathe ── */
body {{ background-color: transparent !important; }}
.overlay {{ background: transparent !important; }}

/* ── Deck table: frosted glass ── */
.decks-container {{
    background-color: {t['surface']} !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.45) !important;
}}

/* ── Deck rows ── */
.deck-row {{ border-bottom: 1px solid {t['border']} !important; }}
.deck-row:hover {{ background: rgba(255,255,255,0.04) !important; }}

/* ── Text ── */
a.deck, .collapseable {{ color: {t['text']} !important; }}
.collapseable         {{ color: {t['text']} !important; }}
.zero-count           {{ color: {t['text_zero']} !important; }}
.count                {{ color: {t['text']} !important; }}
.filtered             {{ color: {t['text_filt']} !important; }}

/* ── Gear icon ── */
.bi-gear-fill path, svg .bi-gear-fill {{ fill: {t['gear']} !important; }}

/* ── Count badges ── */
.review-count {{
    background-color: {t['rev_bg']} !important;
    color: {t['rev_fg']} !important;
}}
.new-count {{
    background-color: {t['new_bg']} !important;
    color: {t['new_fg']} !important;
}}

/* ── Stats widget text ── */
.stats {{ color: {t['w_text']} !important; }}
.stats svg path {{ fill: {t['w_text']} !important; }}

/* ── Bottom bar buttons ── */
.btn {{
    background: {t['btn_bg']} !important;
    color: {t['btn_fg']} !important;
    border: none !important;
}}
"""

    js_css = json.dumps(css)

    return f"""
(function() {{
    /* Inject stylesheet */
    var el = document.getElementById('anki-theme-style');
    if (!el) {{
        el = document.createElement('style');
        el.id = 'anki-theme-style';
        document.head.appendChild(el);
    }}
    el.textContent = {js_css};

    /* Patch inline-styled stats widgets (Beautify sets these inline) */
    var colors = {widget_colors};
    var widgets = document.querySelectorAll('.stats');
    widgets.forEach(function(w, i) {{
        if (i < colors.length) {{
            w.style.setProperty('background-color', colors[i], 'important');
        }}
    }});

    /* Patch bottom bar buttons */
    document.querySelectorAll('.btn').forEach(function(b) {{
        b.style.setProperty('background', '{t['btn_bg']}', 'important');
        b.style.setProperty('color', '{t['btn_fg']}', 'important');
    }});
}})();
"""

# ── Apply theme ───────────────────────────────────────────────

def _apply_theme(name: str = None):
    global _current
    if name:
        _current = name
        _save_theme(name)
    t = THEMES.get(_current, THEMES['Midnight Purple'])
    mw.deckBrowser.web.eval(_build_js(t))

# ── Theme picker modal ────────────────────────────────────────

def _build_picker_js() -> str:
    swatches = ''
    for name, t in THEMES.items():
        ring = '3px solid #fff' if name == _current else '2px solid transparent'
        swatches += f"""
        <div class="tswatch" onclick="pycmd('set_theme:{name}')" title="{name}"
             style="background:{t['swatch']};width:30px;height:30px;border-radius:50%;
                    cursor:pointer;display:inline-flex;margin:5px;
                    border:{ring};box-sizing:border-box;transition:transform .15s,border .15s;"
             onmouseenter="this.style.transform='scale(1.25)';this.style.border='3px solid #fff';
                           document.getElementById('t-label').textContent=this.title;"
             onmouseleave="this.style.transform='';this.style.border='{ring}';">
        </div>"""

    return f"""
    (function() {{
        var old = document.getElementById('theme-modal');
        if (old) {{ old.remove(); return; }}
        var m = document.createElement('div');
        m.id = 'theme-modal';
        m.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);' +
            'background:rgba(20,15,40,0.95);backdrop-filter:blur(20px);' +
            'border:1px solid rgba(255,255,255,0.15);border-radius:16px;' +
            'padding:22px 26px;z-index:99999;' +
            'box-shadow:0 20px 60px rgba(0,0,0,0.8);min-width:360px;';
        m.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <span style="color:#fff;font-weight:800;font-size:15px;letter-spacing:.5px;">🎨 Choose Theme</span>
                <span onclick="this.parentElement.parentElement.remove()"
                      style="color:#888;cursor:pointer;font-size:20px;padding:2px 6px;"
                      onmouseenter="this.style.color='#fff'" onmouseleave="this.style.color='#888'">✕</span>
            </div>
            <div style="display:flex;flex-wrap:wrap;justify-content:flex-start;">
                {swatches}
            </div>
            <div id="t-label"
                 style="color:#aaa;font-size:12px;margin-top:12px;text-align:center;
                        height:16px;letter-spacing:.3px;">{_current}</div>
        `;
        document.body.appendChild(m);
    }})();
    """

# ── pycmd handler ─────────────────────────────────────────────

def _handle_pycmd(handled, message, context):
    if message == 'open_theme_picker':
        mw.deckBrowser.web.eval(_build_picker_js())
        return (True, None)
    if message.startswith('set_theme:'):
        name = message[len('set_theme:'):]
        if name in THEMES:
            _apply_theme(name)
            mw.deckBrowser.web.eval(
                "var m=document.getElementById('theme-modal');if(m)m.remove();"
            )
            _inject_toolbar_btn()
        return (True, None)
    return handled

# ── Toolbar 🎨 button (injected into toolbar webview) ─────────

def _inject_toolbar_btn():
    js = """
    (function() {
        var old = document.getElementById('theme-tb-btn');
        if (old) old.remove();
        var btn = document.createElement('button');
        btn.id = 'theme-tb-btn';
        btn.innerHTML = '🎨';
        btn.title = 'Switch Theme';
        btn.style.cssText = [
            'position:fixed','top:6px','right:14px','z-index:9999',
            'background:rgba(30,20,60,0.85)',
            'border:1px solid rgba(124,58,237,0.5)',
            'border-radius:50%','width:30px','height:30px',
            'font-size:16px','cursor:pointer',
            'display:flex','align-items:center','justify-content:center',
            'transition:transform .15s,background .15s','line-height:1'
        ].join(';');
        btn.onmouseenter = function(){ this.style.transform='scale(1.15)'; this.style.background='rgba(124,58,237,0.9)'; };
        btn.onmouseleave = function(){ this.style.transform=''; this.style.background='rgba(30,20,60,0.85)'; };
        btn.onclick = function(){ pycmd('open_theme_picker'); };
        document.body.appendChild(btn);
    })();
    """
    mw.toolbar.web.eval(js)

# ── Hooks ─────────────────────────────────────────────────────

_webview_connected = False

def _on_deck_render(deck_browser: DeckBrowser):
    from aqt.qt import QTimer
    QTimer.singleShot(300, _apply_theme)
    QTimer.singleShot(350, _inject_toolbar_btn)

def _on_state_change(new_state, old_state):
    """Re-apply when returning to deck browser (e.g. after reviewing cards)."""
    if new_state == "deckBrowser" and old_state != "deckBrowser":
        from aqt.qt import QTimer
        QTimer.singleShot(400, _apply_theme)

def _on_toolbar_render(links, toolbar):
    from aqt.qt import QTimer
    QTimer.singleShot(250, _inject_toolbar_btn)

def _on_webview_load(ok):
    """Fires when deck browser webview finishes loading — most reliable path."""
    if ok and mw.state == "deckBrowser":
        _apply_theme()

def _setup():
    global _webview_connected
    _rotate_background()
    _rotate_deck_icon()
    gui_hooks.deck_browser_did_render.append(_on_deck_render)
    gui_hooks.state_did_change.append(_on_state_change)
    gui_hooks.top_toolbar_did_init_links.append(_on_toolbar_render)
    gui_hooks.webview_did_receive_js_message.append(_handle_pycmd)
    # Guard against double-connection on profile switch within the same process
    if not _webview_connected:
        mw.deckBrowser.web.loadFinished.connect(_on_webview_load)
        _webview_connected = True

gui_hooks.main_window_did_init.append(_setup)
