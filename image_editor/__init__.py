"""
Image Editor — draw on images in the note editor.

Right-click an image in a field → "✏️ Draw / edit image" → a canvas opens with
drawing tools (pen, marker, arrow, rectangle, ellipse, text, eraser, colour,
size, undo). Save writes the annotated image into the collection's media folder
and points this card's <img> at the new file (other notes are untouched).
"""

from __future__ import annotations

import hashlib
import math
import os
import urllib.parse

from aqt import gui_hooks, mw
from aqt.qt import *  # noqa: F401,F403
from aqt.utils import showWarning, tooltip

try:
    from aqt.qt import QWebEngineContextMenuRequest
except Exception:  # pragma: no cover
    from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest


# ── Drawing canvas ─────────────────────────────────────────────────────────────

class Canvas(QWidget):
    def __init__(self, pixmap: QPixmap):
        super().__init__()
        self.base = pixmap
        self.overlay = QImage(pixmap.size(), QImage.Format.Format_ARGB32)
        self.overlay.fill(Qt.GlobalColor.transparent)
        self.setFixedSize(pixmap.size())
        self.setCursor(Qt.CursorShape.CrossCursor)

        self.tool = "pen"
        self.color = QColor("#ff3b30")
        self.pen_w = 4

        self._drawing = False
        self._start = None
        self._last = None
        self._cur = None
        self._undo: list[QImage] = []

    # -- helpers --------------------------------------------------------------
    def _snapshot(self):
        self._undo.append(self.overlay.copy())
        if len(self._undo) > 40:
            self._undo.pop(0)

    def undo(self):
        if self._undo:
            self.overlay = self._undo.pop()
            self.update()

    def _pen(self, painter: QPainter, marker=False):
        c = QColor(self.color)
        w = self.pen_w
        if marker:
            c.setAlpha(80)
            w = self.pen_w * 3
        pen = QPen(c, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _segment(self, a, b):
        p = QPainter(self.overlay)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.tool == "eraser":
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.setPen(QPen(Qt.GlobalColor.transparent, self.pen_w * 4,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        else:
            self._pen(p, marker=(self.tool == "marker"))
        p.drawLine(a, b)
        p.end()

    def _shape(self, p: QPainter, a, b):
        self._pen(p)
        if self.tool in ("line", "arrow"):
            p.drawLine(a, b)
            if self.tool == "arrow":
                ang = math.atan2(b.y() - a.y(), b.x() - a.x())
                L = max(12, self.pen_w * 3.5)
                for d in (math.pi - 0.45, math.pi + 0.45):
                    x = b.x() + L * math.cos(ang + d)
                    y = b.y() + L * math.sin(ang + d)
                    p.drawLine(b, QPoint(int(x), int(y)))
        elif self.tool == "rect":
            p.drawRect(QRect(a, b).normalized())
        elif self.tool == "ellipse":
            p.drawEllipse(QRect(a, b).normalized())

    # -- events ---------------------------------------------------------------
    def _pos(self, e):
        return e.position().toPoint()

    def mousePressEvent(self, e):
        pos = self._pos(e)
        self._snapshot()
        self._start = pos
        self._last = pos
        self._cur = pos

        if self.tool == "text":
            txt, ok = QInputDialog.getText(self, "Add text", "Text:")
            if ok and txt:
                p = QPainter(self.overlay)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                f = QFont()
                f.setPixelSize(max(14, self.pen_w * 6))
                f.setBold(True)
                p.setFont(f)
                p.setPen(self.color)
                p.drawText(QPoint(pos.x(), pos.y() + f.pixelSize()), txt)
                p.end()
            else:
                if self._undo:
                    self._undo.pop()
            self.update()
            return

        self._drawing = True
        if self.tool in ("pen", "marker", "eraser"):
            self._segment(pos, pos)
            self.update()

    def mouseMoveEvent(self, e):
        if not self._drawing:
            return
        pos = self._pos(e)
        if self.tool in ("pen", "marker", "eraser"):
            self._segment(self._last, pos)
            self._last = pos
        self._cur = pos
        self.update()

    def mouseReleaseEvent(self, e):
        if not self._drawing:
            return
        pos = self._pos(e)
        if self.tool in ("line", "arrow", "rect", "ellipse"):
            p = QPainter(self.overlay)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._shape(p, self._start, pos)
            p.end()
        self._drawing = False
        self._cur = None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawPixmap(0, 0, self.base)
        p.drawImage(0, 0, self.overlay)
        if self._drawing and self._cur and self.tool in ("line", "arrow", "rect", "ellipse"):
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._shape(p, self._start, self._cur)
        p.end()

    def result(self) -> QImage:
        img = QImage(self.base.size(), QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.white)
        p = QPainter(img)
        p.drawPixmap(0, 0, self.base)
        p.drawImage(0, 0, self.overlay)
        p.end()
        return img


# ── Editor dialog ──────────────────────────────────────────────────────────────

_TOOLS = [
    ("pen",     "✏️", "Pen"),
    ("marker",  "🖍️", "Highlighter"),
    ("arrow",   "➴",  "Arrow"),
    ("line",    "／",  "Line"),
    ("rect",    "▭",  "Rectangle"),
    ("ellipse", "◯",  "Ellipse"),
    ("text",    "T",  "Text"),
    ("eraser",  "🧽", "Eraser (your drawing only)"),
]


class ImageEditorDialog(QDialog):
    def __init__(self, parent, pixmap: QPixmap):
        super().__init__(parent)
        self.setWindowTitle("Draw / edit image")
        self.canvas = Canvas(pixmap)

        root = QVBoxLayout(self)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, label, tip in _TOOLS:
            b = QToolButton()
            b.setText(label)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setFixedSize(34, 30)
            b.clicked.connect(lambda _c=False, k=key: self._set_tool(k))
            if key == "pen":
                b.setChecked(True)
            self._group.addButton(b)
            bar.addWidget(b)

        bar.addSpacing(10)

        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(30, 28)
        self._color_btn.setToolTip("Colour")
        self._color_btn.clicked.connect(self._pick_color)
        self._paint_color_btn()
        bar.addWidget(self._color_btn)

        bar.addWidget(QLabel("Size"))
        self._size = QSlider(Qt.Orientation.Horizontal)
        self._size.setRange(1, 40)
        self._size.setValue(self.canvas.pen_w)
        self._size.setFixedWidth(110)
        self._size.valueChanged.connect(lambda v: setattr(self.canvas, "pen_w", v))
        bar.addWidget(self._size)

        undo_btn = QPushButton("↶ Undo")
        undo_btn.clicked.connect(self.canvas.undo)
        bar.addWidget(undo_btn)

        bar.addStretch()
        root.addLayout(bar)

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidgetResizable(False)
        root.addWidget(scroll, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.canvas.undo)

        # Size the dialog to fit the image plus chrome, within the screen.
        w = min(pixmap.width() + 60, 1500)
        h = min(pixmap.height() + 130, 900)
        self.resize(w, h)

    def _set_tool(self, key):
        self.canvas.tool = key

    def _paint_color_btn(self):
        c = self.canvas.color.name()
        self._color_btn.setStyleSheet(
            "background:%s; border:1px solid #888; border-radius:4px;" % c)

    def _pick_color(self):
        c = QColorDialog.getColor(self.canvas.color, self, "Pick colour")
        if c.isValid():
            self.canvas.color = c
            self._paint_color_btn()


# ── Save + field update ─────────────────────────────────────────────────────────

def _png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _open_editor(editor, fname: str):
    path = os.path.join(mw.col.media.dir(), fname)
    if not os.path.isfile(path):
        showWarning("Image file not found in media:\n%s" % fname)
        return
    pm = QPixmap(path)
    if pm.isNull():
        showWarning("Could not load the image.")
        return

    # Scale very large images down to a workable canvas (keeps good quality).
    MAXW, MAXH = 1400, 820
    if pm.width() > MAXW or pm.height() > MAXH:
        pm = pm.scaled(MAXW, MAXH, Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)

    parent = getattr(editor, "parentWindow", None) or mw
    dlg = ImageEditorDialog(parent, pm)
    if not dlg.exec():
        return

    data = _png_bytes(dlg.canvas.result())
    stem = os.path.splitext(os.path.basename(fname))[0][:40]
    newname = "%s-edited-%s.png" % (stem, hashlib.md5(data).hexdigest()[:8])
    try:
        newfn = mw.col.media.write_data(newname, data)
    except Exception as exc:
        showWarning("Could not save the edited image:\n%s" % exc)
        return

    note = getattr(editor, "note", None)
    if note is None:
        return
    changed = False
    for i, val in enumerate(note.fields):
        if fname in val:
            note.fields[i] = val.replace(fname, newfn)
            changed = True
    if not changed:
        tooltip("Saved %s, but couldn't find the image in a field." % newfn)
        return
    try:
        if getattr(note, "id", 0):
            mw.col.update_note(note)
    except Exception:
        pass
    try:
        editor.loadNoteKeepingFocus()
    except Exception:
        try:
            editor.loadNote()
        except Exception:
            pass
    tooltip("Image updated ✓")


# ── Context menu hook ────────────────────────────────────────────────────────────

def _on_context_menu(webview, menu):
    try:
        req = webview.lastContextMenuRequest()
        if req is None:
            return
        if req.mediaType() != QWebEngineContextMenuRequest.MediaType.MediaTypeImage:
            return
        url = req.mediaUrl().toString()
    except Exception:
        return

    fname = urllib.parse.unquote(url.rsplit("/", 1)[-1].split("?")[0])
    editor = getattr(webview, "editor", None)
    if not fname or editor is None or url.startswith("data:"):
        return

    menu.addSeparator()
    act = menu.addAction("✏️  Draw / edit image")
    act.triggered.connect(lambda: _open_editor(editor, fname))


gui_hooks.editor_will_show_context_menu.append(_on_context_menu)
