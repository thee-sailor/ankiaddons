"""
Comet Theme — Spatial UI for Anki
All visual settings are driven by config.json and editable via
Tools → Comet Theme Settings (GUI dialog, no file editing required).
"""

from __future__ import annotations
import os

from aqt import mw, gui_hooks
from aqt.qt import (
    QAction, QButtonGroup, QCheckBox, QColor, QColorDialog,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QSizePolicy, QSlider,
    QSpacerItem, QVBoxLayout, Qt, QWidget,
)
from aqt.utils import tooltip
from aqt.webview import WebContent

# ── Paths ──────────────────────────────────────────────────────────────────────

_ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
_ADDON_PKG = __name__
_CSS_URL   = f"/_addons/{_ADDON_PKG}/ui.css"

# ── Colour utilities ───────────────────────────────────────────────────────────

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c*2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"

def _lighten(hex_color: str, factor: float = 0.18) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(
        min(255, int(r + (255 - r) * factor)),
        min(255, int(g + (255 - g) * factor)),
        min(255, int(b + (255 - b) * factor)),
    )

def _darken(hex_color: str, factor: float = 0.35) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(int(r * (1 - factor)), int(g * (1 - factor)), int(b * (1 - factor)))

def _mix(a: str, b: str, t: float = 0.5) -> str:
    """Linear interpolate between two hex colors."""
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    return _rgb_to_hex(
        int(ar + (br - ar) * t),
        int(ag + (bg - ag) * t),
        int(ab + (bb - ab) * t),
    )

# ── Config → CSS/QSS builders ─────────────────────────────────────────────────

def _get_cfg() -> dict:
    return mw.addonManager.getConfig(__name__) or {}


def _wallpaper_value(cfg: dict) -> str:
    wtype = cfg.get("wallpaper_type", "solid")
    if wtype == "gradient":
        gf = cfg.get("wallpaper_grad_from", "#091717")
        gt = cfg.get("wallpaper_grad_to",   "#0d2030")
        ga = int(cfg.get("wallpaper_grad_angle", 135))
        return f"linear-gradient({ga}deg, {gf}, {gt})"
    if wtype == "image":
        path = cfg.get("wallpaper_image_path", "").strip()
        if path:
            url = path.replace("\\", "/")
            if not url.startswith("file://"):
                url = "file:///" + url
            return f"url('{url}')"
    return cfg.get("wallpaper_solid", "#091717")


def _build_css_vars(cfg: dict) -> str:
    """Inline <style> block that overrides :root variables from config."""
    accent      = cfg.get("accent",       "#21808d")
    accent_lt   = _lighten(accent, 0.20)
    accent_dim  = f"rgba({','.join(str(v) for v in _hex_to_rgb(accent))},0.22)"
    accent_glow = f"rgba({','.join(str(v) for v in _hex_to_rgb(accent))},0.15)"
    bg_base     = cfg.get("bg_base",      "#091717")
    bg_card     = cfg.get("bg_card",      "#162c2c")
    bg_surface  = _mix(bg_base, "#ffffff", 0.04)
    bg_elevated = _mix(bg_base, "#ffffff", 0.07)
    bg_input    = _mix(bg_base, "#ffffff", 0.05)
    text_prim   = cfg.get("text_primary", "#fbfaf4")
    noise_op    = cfg.get("noise_opacity", 0.035) if cfg.get("noise_enabled", True) else 0
    font_ui     = cfg.get("font_ui",      "Inter")
    font_disp   = cfg.get("font_display", "Newsreader")
    wp          = _wallpaper_value(cfg)

    return (
        f"<style>:root{{"
        f"--bg-wallpaper:{wp};"
        f"--bg-base:{bg_base};"
        f"--bg-surface:{bg_surface};"
        f"--bg-elevated:{bg_elevated};"
        f"--bg-card:{bg_card};"
        f"--bg-input:{bg_input};"
        f"--bg-hover:rgba({','.join(str(v) for v in _hex_to_rgb(accent))},0.08);"
        f"--bg-selected:rgba({','.join(str(v) for v in _hex_to_rgb(accent))},0.14);"
        f"--text-primary:{text_prim};"
        f"--accent:{accent};"
        f"--accent-light:{accent_lt};"
        f"--accent-dim:{accent_dim};"
        f"--accent-glow:{accent_glow};"
        f"--noise-opacity:{noise_op};"
        f"--font-ui:'{font_ui}','Segoe UI',sans-serif;"
        f"--font-display:'{font_disp}','Georgia',serif;"
        f"}}</style>"
    )


def _build_qt_style(cfg: dict) -> str:
    accent    = cfg.get("accent",       "#21808d")
    accent_lt = _lighten(accent, 0.18)
    bg_base   = cfg.get("bg_base",      "#091717")
    bg_surf   = _mix(bg_base, "#ffffff", 0.04)
    bg_elev   = _mix(bg_base, "#ffffff", 0.07)
    bg_card   = cfg.get("bg_card",      "#162c2c")
    bg_input  = _mix(bg_base, "#ffffff", 0.05)
    bg_sel    = f"rgba({','.join(str(v) for v in _hex_to_rgb(accent))},0.22)"
    text      = cfg.get("text_primary", "#fbfaf4")
    text_dim  = f"rgba({','.join(str(v) for v in _hex_to_rgb(text))},0.60)"
    text_mute = f"rgba({','.join(str(v) for v in _hex_to_rgb(text))},0.30)"
    font      = cfg.get("font_ui", "Inter")

    return f"""
QWidget{{background-color:{bg_base};color:{text};font-family:"{font}","Segoe UI",sans-serif;font-size:13px;border:none;outline:none;}}
QMainWindow,QDialog{{background-color:{bg_base};}}
QToolBar{{background-color:{bg_surf};border-bottom:1px solid rgba(255,255,255,0.05);padding:4px 8px;spacing:4px;}}
QMenuBar{{background-color:{bg_surf};color:{text_dim};border-bottom:1px solid rgba(255,255,255,0.05);padding:2px 6px;}}
QMenuBar::item{{background:transparent;padding:4px 10px;border-radius:8px;}}
QMenuBar::item:selected{{background:{bg_card};color:{text};}}
QMenu{{background-color:{bg_elev};color:{text};border:1px solid rgba(255,255,255,0.07);border-radius:16px;padding:6px 4px;}}
QMenu::item{{padding:7px 22px 7px 14px;border-radius:8px;margin:1px 4px;}}
QMenu::item:selected{{background:{bg_sel};color:{text};}}
QMenu::separator{{height:1px;background:rgba(255,255,255,0.06);margin:4px 10px;}}
QPushButton{{background-color:{bg_elev};color:{text_dim};border:1px solid rgba(255,255,255,0.07);border-radius:999px;padding:6px 18px;font-weight:500;min-height:28px;}}
QPushButton:hover{{background-color:{bg_card};color:{text};border-color:{accent};}}
QPushButton:pressed{{background-color:{bg_base};}}
QPushButton:disabled{{color:{text_mute};border-color:rgba(255,255,255,0.03);}}
QPushButton:default{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {accent_lt},stop:1 {accent});color:{text};border:none;font-weight:600;}}
QPushButton:default:hover{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {accent_lt},stop:1 {accent_lt});}}
QToolButton{{background:transparent;color:{text_dim};border:none;border-radius:8px;padding:5px 8px;}}
QToolButton:hover{{background:{bg_card};color:{text};}}
QToolButton:checked{{background:{bg_sel};color:{accent_lt};}}
QLineEdit,QTextEdit,QPlainTextEdit{{background-color:{bg_input};color:{text};border:1px solid rgba(255,255,255,0.07);border-radius:8px;padding:6px 12px;selection-background-color:{accent};selection-color:{text};}}
QLineEdit:focus,QTextEdit:focus,QPlainTextEdit:focus{{border-color:{accent};}}
QLineEdit:disabled,QTextEdit:disabled{{color:{text_mute};background-color:{bg_surf};}}
QComboBox{{background-color:{bg_input};color:{text};border:1px solid rgba(255,255,255,0.07);border-radius:8px;padding:5px 12px;min-height:28px;}}
QComboBox:hover{{border-color:{accent};}}
QComboBox::drop-down{{border:none;width:20px;}}
QComboBox QAbstractItemView{{background-color:{bg_elev};color:{text};border:1px solid rgba(255,255,255,0.07);border-radius:10px;selection-background-color:{bg_sel};selection-color:{text};padding:4px;}}
QSpinBox,QDoubleSpinBox{{background-color:{bg_input};color:{text};border:1px solid rgba(255,255,255,0.07);border-radius:8px;padding:5px 10px;}}
QSpinBox:focus,QDoubleSpinBox:focus{{border-color:{accent};}}
QTableView,QListView,QTreeView{{background-color:{bg_surf};color:{text};border:1px solid rgba(255,255,255,0.05);border-radius:16px;gridline-color:rgba(255,255,255,0.04);selection-background-color:{bg_sel};selection-color:{text};alternate-background-color:{bg_base};outline:none;}}
QTableView::item,QListView::item,QTreeView::item{{padding:6px 10px;border:none;}}
QTableView::item:selected,QListView::item:selected,QTreeView::item:selected{{background-color:{bg_sel};color:{text};}}
QTableView::item:hover,QListView::item:hover,QTreeView::item:hover{{background-color:rgba(255,255,255,0.04);}}
QHeaderView{{background-color:{bg_elev};border:none;}}
QHeaderView::section{{background-color:{bg_elev};color:{text_mute};font-size:10px;font-weight:600;padding:8px 12px;border:none;border-right:1px solid rgba(255,255,255,0.05);border-bottom:1px solid rgba(255,255,255,0.05);}}
QHeaderView::section:hover{{background-color:{bg_card};color:{text};}}
QTabWidget::pane{{background-color:{bg_surf};border:1px solid rgba(255,255,255,0.05);border-radius:16px;top:-1px;}}
QTabBar::tab{{background:transparent;color:{text_mute};padding:8px 18px;border:none;border-bottom:2px solid transparent;font-weight:500;}}
QTabBar::tab:selected{{color:{text};border-bottom:2px solid {accent};}}
QTabBar::tab:hover{{color:{text_dim};background:{bg_card};border-radius:8px 8px 0 0;}}
QScrollBar:vertical{{background:transparent;width:6px;margin:0;}}
QScrollBar::handle:vertical{{background:rgba(255,255,255,0.10);border-radius:3px;min-height:30px;}}
QScrollBar::handle:vertical:hover{{background:rgba(255,255,255,0.18);}}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}
QScrollBar:horizontal{{background:transparent;height:6px;margin:0;}}
QScrollBar::handle:horizontal{{background:rgba(255,255,255,0.10);border-radius:3px;min-width:30px;}}
QScrollBar::handle:horizontal:hover{{background:rgba(255,255,255,0.18);}}
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0;}}
QCheckBox,QRadioButton{{color:{text_dim};spacing:8px;}}
QCheckBox:hover,QRadioButton:hover{{color:{text};}}
QCheckBox::indicator,QRadioButton::indicator{{width:16px;height:16px;border:1px solid rgba(255,255,255,0.15);border-radius:4px;background:{bg_input};}}
QCheckBox::indicator:checked{{background:{accent};border-color:{accent};}}
QRadioButton::indicator{{border-radius:8px;}}
QRadioButton::indicator:checked{{background:{accent};border-color:{accent};}}
QSplitter::handle{{background:rgba(255,255,255,0.05);}}
QSplitter::handle:horizontal{{width:1px;}}
QSplitter::handle:vertical{{height:1px;}}
QDockWidget{{color:{text};}}
QDockWidget::title{{background:{bg_surf};padding:6px 10px;border-bottom:1px solid rgba(255,255,255,0.05);font-weight:600;color:{accent_lt};font-size:12px;}}
QStatusBar{{background:{bg_surf};color:{text_mute};border-top:1px solid rgba(255,255,255,0.04);font-size:11px;}}
QLabel{{color:{text_dim};background:transparent;}}
QGroupBox{{border:1px solid rgba(255,255,255,0.07);border-radius:14px;margin-top:18px;padding-top:14px;color:{text_dim};font-weight:500;}}
QGroupBox::title{{subcontrol-origin:margin;subcontrol-position:top left;left:12px;top:-1px;padding:0 6px;color:{text_mute};font-size:11px;}}
QProgressBar{{background:{bg_elev};border:none;border-radius:999px;height:6px;text-align:center;color:transparent;}}
QProgressBar::chunk{{background:{accent};border-radius:999px;}}
QSlider::groove:horizontal{{background:{bg_elev};height:4px;border-radius:2px;}}
QSlider::handle:horizontal{{background:{accent};border:none;width:14px;height:14px;border-radius:7px;margin:-5px 0;}}
QSlider::sub-page:horizontal{{background:{accent};border-radius:2px;}}
QToolTip{{background-color:{bg_elev};color:{text};border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:5px 10px;font-size:12px;}}
"""

# ── WebView injection ──────────────────────────────────────────────────────────

def _inject_webview(web_content: WebContent, context: object) -> None:
    cfg = _get_cfg()
    web_content.head += _build_css_vars(cfg)
    web_content.css.append(_CSS_URL)

# ── Colour picker button helper ────────────────────────────────────────────────

def _color_btn(color: str) -> QPushButton:
    btn = QPushButton()
    btn.setFixedSize(46, 30)
    btn.setToolTip("Click to pick colour")
    _color_btn_apply(btn, color)
    return btn

def _color_btn_apply(btn: QPushButton, color: str) -> None:
    btn._comet_color = color  # type: ignore[attr-defined]
    btn.setStyleSheet(
        f"QPushButton{{background:{color};border:1px solid rgba(255,255,255,.18);"
        f"border-radius:8px;}} QPushButton:hover{{border-color:rgba(255,255,255,.45);}}"
    )

def _pick(btn: QPushButton, parent: QWidget) -> None:
    c = QColorDialog.getColor(QColor(btn._comet_color), parent, "Choose Colour")  # type: ignore[attr-defined]
    if c.isValid():
        _color_btn_apply(btn, c.name())

# ── Settings dialog ────────────────────────────────────────────────────────────

_LABEL_STYLE  = "color:rgba(251,250,244,.55);font-size:11px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;"
_HEADER_STYLE = "color:#fbfaf4;font-size:15px;font-weight:600;"
_SEP_STYLE    = "background:rgba(255,255,255,0.07);"

def _hsep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1); f.setStyleSheet(_SEP_STYLE)
    return f

class CometSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Comet Theme Settings")
        self.setMinimumWidth(460)
        self.setMaximumWidth(520)
        self.setStyleSheet("""
            QDialog{background:#0d1e1e;color:#fbfaf4;}
            QGroupBox{border:1px solid rgba(255,255,255,.07);border-radius:12px;
                      margin-top:16px;padding:14px 12px 10px;}
            QGroupBox::title{subcontrol-origin:margin;subcontrol-position:top left;
                             left:12px;top:-1px;padding:0 6px;
                             color:rgba(251,250,244,.35);font-size:10px;
                             font-weight:600;letter-spacing:0.12em;}
            QRadioButton{color:rgba(251,250,244,.65);spacing:7px;}
            QRadioButton:hover{color:#fbfaf4;}
            QRadioButton::indicator{width:14px;height:14px;border:1px solid rgba(255,255,255,.18);
                                    border-radius:7px;background:#0e2020;}
            QRadioButton::indicator:checked{background:#21808d;border-color:#21808d;}
            QCheckBox{color:rgba(251,250,244,.65);spacing:7px;}
            QCheckBox:hover{color:#fbfaf4;}
            QCheckBox::indicator{width:14px;height:14px;border:1px solid rgba(255,255,255,.18);
                                  border-radius:4px;background:#0e2020;}
            QCheckBox::indicator:checked{background:#21808d;border-color:#21808d;}
            QLineEdit{background:#0e2020;color:#fbfaf4;border:1px solid rgba(255,255,255,.08);
                      border-radius:7px;padding:5px 10px;font-size:12px;}
            QLineEdit:focus{border-color:#21808d;}
            QSlider::groove:horizontal{background:#122626;height:4px;border-radius:2px;}
            QSlider::handle:horizontal{background:#21808d;border:none;width:14px;height:14px;
                                        border-radius:7px;margin:-5px 0;}
            QSlider::sub-page:horizontal{background:#21808d;border-radius:2px;}
            QLabel{background:transparent;}
            QPushButton{background:#122626;color:rgba(251,250,244,.65);
                        border:1px solid rgba(255,255,255,.07);border-radius:999px;
                        padding:6px 16px;font-size:12px;font-weight:500;}
            QPushButton:hover{background:#162c2c;color:#fbfaf4;border-color:#21808d;}
            QPushButton#save{background:#21808d;color:#fbfaf4;border:none;font-weight:600;}
            QPushButton#save:hover{background:#2d9ead;}
            QPushButton#reset{background:transparent;color:rgba(251,250,244,.35);border:none;}
            QPushButton#reset:hover{color:rgba(251,250,244,.70);}
        """)
        self._cfg = dict(_get_cfg())
        self._build()
        self._load_cfg()

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(4)

        # Header
        hdr = QLabel("Comet Theme")
        hdr.setStyleSheet("color:#fbfaf4;font-size:16px;font-weight:700;")
        root.addWidget(hdr)
        sub = QLabel("Visual settings apply immediately on save — no Anki restart needed.")
        sub.setStyleSheet("color:rgba(251,250,244,.40);font-size:11px;")
        sub.setWordWrap(True)
        root.addWidget(sub)
        root.addSpacing(6)

        # ── Wallpaper ──────────────────────────────────────────────────────
        wp_box = QGroupBox("Wallpaper")
        wp_lay = QVBoxLayout(wp_box)
        wp_lay.setSpacing(8)

        # Type radio row
        type_row = QHBoxLayout()
        self._rb_solid = QRadioButton("Solid colour")
        self._rb_grad  = QRadioButton("Gradient")
        self._rb_img   = QRadioButton("Image file")
        self._wp_group = QButtonGroup(self)
        for i, rb in enumerate([self._rb_solid, self._rb_grad, self._rb_img]):
            self._wp_group.addButton(rb, i)
            type_row.addWidget(rb)
        type_row.addStretch()
        wp_lay.addLayout(type_row)
        wp_lay.addWidget(_hsep())

        # Solid
        self._solid_frame = QWidget()
        sl = QHBoxLayout(self._solid_frame); sl.setContentsMargins(0,0,0,0); sl.setSpacing(10)
        sl.addWidget(QLabel("Colour"))
        self._btn_solid = _color_btn("#091717")
        self._btn_solid.clicked.connect(lambda: _pick(self._btn_solid, self))
        sl.addWidget(self._btn_solid); sl.addStretch()
        wp_lay.addWidget(self._solid_frame)

        # Gradient
        self._grad_frame = QWidget()
        gl = QHBoxLayout(self._grad_frame); gl.setContentsMargins(0,0,0,0); gl.setSpacing(10)
        gl.addWidget(QLabel("From"))
        self._btn_gfrom = _color_btn("#091717")
        self._btn_gfrom.clicked.connect(lambda: _pick(self._btn_gfrom, self))
        gl.addWidget(self._btn_gfrom)
        gl.addWidget(QLabel("To"))
        self._btn_gto = _color_btn("#0d2030")
        self._btn_gto.clicked.connect(lambda: _pick(self._btn_gto, self))
        gl.addWidget(self._btn_gto)
        gl.addWidget(QLabel("°"))
        self._angle_spin = QDoubleSpinBox()
        self._angle_spin.setRange(0, 360); self._angle_spin.setValue(135)
        self._angle_spin.setSuffix("°"); self._angle_spin.setFixedWidth(72)
        self._angle_spin.setDecimals(0)
        gl.addWidget(self._angle_spin); gl.addStretch()
        wp_lay.addWidget(self._grad_frame)

        # Image
        self._img_frame = QWidget()
        il = QHBoxLayout(self._img_frame); il.setContentsMargins(0,0,0,0); il.setSpacing(8)
        self._img_path = QLineEdit(); self._img_path.setPlaceholderText("C:/path/to/wallpaper.jpg")
        il.addWidget(self._img_path, stretch=1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_image)
        il.addWidget(browse)
        wp_lay.addWidget(self._img_frame)

        root.addWidget(wp_box)

        # ── Colours ────────────────────────────────────────────────────────
        col_box = QGroupBox("Colours")
        col_lay = QVBoxLayout(col_box)
        col_lay.setSpacing(8)

        self._color_rows: dict[str, QPushButton] = {}
        for key, label, default in [
            ("accent",       "Accent (buttons & highlights)", "#21808d"),
            ("bg_base",      "Background base",               "#091717"),
            ("bg_card",      "Card surface",                  "#162c2c"),
            ("text_primary", "Text",                          "#fbfaf4"),
        ]:
            row = QHBoxLayout(); row.setSpacing(10)
            lbl = QLabel(label); lbl.setStyleSheet("color:rgba(251,250,244,.65);font-size:12px;")
            row.addWidget(lbl, stretch=1)
            btn = _color_btn(default)
            btn.clicked.connect(lambda _, b=btn: _pick(b, self))
            row.addWidget(btn)
            self._color_rows[key] = btn
            col_lay.addLayout(row)

        root.addWidget(col_box)

        # ── Texture ────────────────────────────────────────────────────────
        tex_box = QGroupBox("Grain texture")
        tex_lay = QHBoxLayout(tex_box); tex_lay.setSpacing(12)
        self._chk_noise = QCheckBox("Enable grain overlay")
        self._chk_noise.setChecked(True)
        tex_lay.addWidget(self._chk_noise)
        tex_lay.addStretch()
        tex_lay.addWidget(QLabel("Intensity"))
        self._noise_slider = QSlider(Qt.Orientation.Horizontal)
        self._noise_slider.setRange(0, 100); self._noise_slider.setValue(35)
        self._noise_slider.setFixedWidth(100)
        tex_lay.addWidget(self._noise_slider)
        self._noise_val = QLabel("3.5%")
        self._noise_val.setStyleSheet("color:rgba(251,250,244,.55);font-size:11px;min-width:36px;")
        self._noise_slider.valueChanged.connect(
            lambda v: self._noise_val.setText(f"{v/10:.1f}%")
        )
        tex_lay.addWidget(self._noise_val)
        root.addWidget(tex_box)

        root.addSpacing(6)

        # ── Button row ─────────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        reset = QPushButton("Reset defaults"); reset.setObjectName("reset")
        reset.clicked.connect(self._reset_defaults)
        btn_row.addWidget(reset)
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        save = QPushButton("Save & apply"); save.setObjectName("save")
        save.setDefault(True)
        save.clicked.connect(self._save)
        btn_row.addWidget(save)
        root.addLayout(btn_row)

        # Connect radio group to show/hide sub-panels
        self._wp_group.idToggled.connect(self._on_wp_type)
        self._rb_solid.setChecked(True)

    # ── Load config into controls ──────────────────────────────────────────────

    def _load_cfg(self):
        c = self._cfg
        wtype = c.get("wallpaper_type", "solid")
        {"solid": self._rb_solid, "gradient": self._rb_grad, "image": self._rb_img}.get(
            wtype, self._rb_solid
        ).setChecked(True)

        _color_btn_apply(self._btn_solid, c.get("wallpaper_solid", "#091717"))
        _color_btn_apply(self._btn_gfrom, c.get("wallpaper_grad_from", "#091717"))
        _color_btn_apply(self._btn_gto,   c.get("wallpaper_grad_to",   "#0d2030"))
        self._angle_spin.setValue(c.get("wallpaper_grad_angle", 135))
        self._img_path.setText(c.get("wallpaper_image_path", ""))

        for key, btn in self._color_rows.items():
            _color_btn_apply(btn, c.get(key, btn._comet_color))  # type: ignore[attr-defined]

        self._chk_noise.setChecked(c.get("noise_enabled", True))
        self._noise_slider.setValue(int(round(c.get("noise_opacity", 0.035) * 1000)))

    # ── Slot handlers ──────────────────────────────────────────────────────────

    def _on_wp_type(self, _id: int, checked: bool):
        if not checked:
            return
        self._solid_frame.setVisible(_id == 0)
        self._grad_frame.setVisible(_id == 1)
        self._img_frame.setVisible(_id == 2)

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Wallpaper Image", "",
            "Images (*.jpg *.jpeg *.png *.webp *.bmp)"
        )
        if path:
            self._img_path.setText(path)

    def _reset_defaults(self):
        defaults = {
            "wallpaper_type":  "solid",
            "wallpaper_solid": "#091717",
            "wallpaper_grad_from":  "#091717",
            "wallpaper_grad_to":    "#0d2030",
            "wallpaper_grad_angle": 135,
            "wallpaper_image_path": "",
            "accent":          "#21808d",
            "bg_base":         "#091717",
            "bg_card":         "#162c2c",
            "text_primary":    "#fbfaf4",
            "noise_opacity":   0.035,
            "noise_enabled":   True,
        }
        self._cfg = defaults
        self._load_cfg()

    # ── Collect + save ─────────────────────────────────────────────────────────

    def _collect(self) -> dict:
        wtype = ("solid" if self._rb_solid.isChecked()
                 else "gradient" if self._rb_grad.isChecked()
                 else "image")
        noise_v = self._noise_slider.value() / 1000.0

        cfg = dict(self._cfg)
        cfg.update({
            "wallpaper_type":       wtype,
            "wallpaper_solid":      self._btn_solid._comet_color,  # type: ignore
            "wallpaper_grad_from":  self._btn_gfrom._comet_color,  # type: ignore
            "wallpaper_grad_to":    self._btn_gto._comet_color,    # type: ignore
            "wallpaper_grad_angle": int(self._angle_spin.value()),
            "wallpaper_image_path": self._img_path.text().strip(),
            "accent":               self._color_rows["accent"]._comet_color,       # type: ignore
            "bg_base":              self._color_rows["bg_base"]._comet_color,      # type: ignore
            "bg_card":              self._color_rows["bg_card"]._comet_color,      # type: ignore
            "text_primary":         self._color_rows["text_primary"]._comet_color, # type: ignore
            "noise_enabled":        self._chk_noise.isChecked(),
            "noise_opacity":        noise_v,
        })
        return cfg

    def _save(self):
        cfg = self._collect()
        mw.addonManager.writeConfig(__name__, cfg)
        _apply_all(cfg)
        tooltip("Comet Theme settings saved.", period=2000)
        self.accept()

# ── Apply settings at runtime ──────────────────────────────────────────────────

def _apply_all(cfg: dict) -> None:
    """Re-apply Qt stylesheet; webview CSS updates automatically on next load."""
    mw.app.setStyleSheet(_build_qt_style(cfg))

# ── Setup ──────────────────────────────────────────────────────────────────────

def _open_settings():
    dlg = CometSettingsDialog(parent=mw)
    dlg.exec()

def _setup():
    cfg = _get_cfg()
    _apply_all(cfg)

    action = QAction("Comet Theme Settings…", mw)
    action.triggered.connect(_open_settings)
    mw.form.menuTools.addAction(action)

mw.addonManager.setWebExports(__name__, r".*\.css$")
mw.addonManager.setConfigAction(__name__, _open_settings)
gui_hooks.webview_will_set_content.append(_inject_webview)
gui_hooks.main_window_did_init.append(_setup)
