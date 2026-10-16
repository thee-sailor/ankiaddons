"""
PDF annotator with auto-save.

Opens a PDF in a window, lets you draw (pen, highlighter, eraser, text; colour,
size, undo), and writes the drawings into the PDF as annotations, saving
automatically when the window is closed. Rendering/saving uses PyMuPDF (fitz),
installed on first use if missing.
"""

from __future__ import annotations

import os
import subprocess
import sys

from aqt import mw
from aqt.qt import *  # noqa: F401,F403
from aqt.utils import showWarning, tooltip

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _ensure_fitz():
    try:
        import fitz  # noqa: F401
        return fitz
    except Exception:
        pass
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "pymupdf"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
        import fitz  # noqa: F401
        return fitz
    except Exception:
        return None


def _rgb01(name: str):
    c = QColor(name)
    return (c.redF(), c.greenF(), c.blueF())


# ── per-page drawing surface (vector strokes) ──────────────────────────────────

class PageCanvas(QWidget):
    def __init__(self, dlg: "Annotator"):
        super().__init__()
        self.dlg = dlg
        self.base: QPixmap | None = None
        self.strokes: list = []          # list of stroke dicts for the current page
        self._cur = None
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_page(self, base: QPixmap, strokes: list):
        self.base = base
        self.strokes = strokes
        self.setFixedSize(base.size())
        self.update()

    def _pos(self, e):
        return e.position().toPoint()

    def mousePressEvent(self, e):
        if self.base is None:
            return
        pos = self._pos(e)
        tool = self.dlg.tool
        self.dlg._push_undo()            # snapshot pre-action state for undo
        if tool == "text":
            txt, ok = QInputDialog.getText(self, "Add text", "Text:")
            if ok and txt:
                self.strokes.append({"text": txt, "pos": (pos.x(), pos.y()),
                                     "color": self.dlg.color.name(), "width": self.dlg.width})
                self.dlg.mark_dirty()
                self.update()
            else:
                self.dlg._pop_undo()
            return
        if tool == "eraser":
            self._erase(pos)
            return
        self._cur = {"points": [(pos.x(), pos.y())], "color": self.dlg.color.name(),
                     "width": self.dlg.width, "tool": tool}
        self.update()

    def mouseMoveEvent(self, e):
        pos = self._pos(e)
        if self.dlg.tool == "eraser" and (e.buttons() & Qt.MouseButton.LeftButton):
            self._erase(pos)
            return
        if self._cur is not None:
            self._cur["points"].append((pos.x(), pos.y()))
            self.update()

    def mouseReleaseEvent(self, e):
        if self._cur is not None:
            self.strokes.append(self._cur)
            self._cur = None
            self.dlg.mark_dirty()
            self.update()

    def _erase(self, pos):
        r = max(8, self.dlg.width * 2)
        kept = []
        removed = False
        for s in self.strokes:
            if "text" in s:
                tx, ty = s["pos"]
                if abs(tx - pos.x()) < 120 and abs(ty - pos.y()) < 40:
                    removed = True
                    continue
            else:
                hit = any(abs(px - pos.x()) <= r and abs(py - pos.y()) <= r
                          for px, py in s["points"])
                if hit:
                    removed = True
                    continue
            kept.append(s)
        if removed:
            self.strokes[:] = kept
            self.dlg.mark_dirty()
            self.update()

    def _draw_stroke(self, p: QPainter, s: dict):
        if "text" in s:
            f = QFont()
            f.setPixelSize(max(14, s["width"] * 6))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(s["color"]))
            p.drawText(QPoint(s["pos"][0], s["pos"][1] + f.pixelSize()), s["text"])
            return
        c = QColor(s["color"])
        w = s["width"]
        if s["tool"] == "highlighter":
            c.setAlpha(90)
            w = s["width"] * 3
        p.setPen(QPen(c, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        pts = s["points"]
        if len(pts) == 1:
            p.drawPoint(QPoint(*pts[0]))
        else:
            for i in range(1, len(pts)):
                p.drawLine(QPoint(*pts[i - 1]), QPoint(*pts[i]))

    def paintEvent(self, e):
        p = QPainter(self)
        if self.base:
            p.drawPixmap(0, 0, self.base)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for s in self.strokes:
            self._draw_stroke(p, s)
        if self._cur:
            self._draw_stroke(p, self._cur)
        p.end()


# ── annotator window ───────────────────────────────────────────────────────────

class Annotator(QDialog):
    def __init__(self, parent, path: str, fitz):
        super().__init__(parent)
        self.setWindowTitle("Annotate — " + os.path.basename(path))
        self.fitz = fitz
        self.path = path
        self.doc = fitz.open(path)
        self.zoom = 2.0
        self.page = 0
        self.page_strokes: dict[int, list] = {}
        self._dirty = False
        self._saved = False

        self.tool = "pen"
        self.color = QColor("#ff3b30")
        self.width = 4
        self.undo_stack: list = []       # (page_index, strokes-snapshot)

        self.canvas = PageCanvas(self)

        root = QVBoxLayout(self)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        self._tool_group = QButtonGroup(self)
        for key, label, tip in [("pen", "✏️", "Pen"), ("highlighter", "🖍️", "Highlighter"),
                                ("eraser", "🧽", "Eraser"), ("text", "T", "Text")]:
            b = QToolButton(); b.setText(label); b.setToolTip(tip); b.setCheckable(True)
            b.setFixedSize(34, 30)
            b.clicked.connect(lambda _c=False, k=key: setattr(self, "tool", k))
            if key == "pen":
                b.setChecked(True)
            self._tool_group.addButton(b)
            bar.addWidget(b)

        bar.addSpacing(8)
        self._color_btn = QPushButton(); self._color_btn.setFixedSize(30, 28)
        self._color_btn.clicked.connect(self._pick_color)
        self._paint_color()
        bar.addWidget(self._color_btn)
        bar.addWidget(QLabel("Size"))
        self._size = QSlider(Qt.Orientation.Horizontal)
        self._size.setRange(1, 40); self._size.setValue(self.width); self._size.setFixedWidth(100)
        self._size.valueChanged.connect(lambda v: setattr(self, "width", v))
        bar.addWidget(self._size)
        undo_b = QPushButton("↶ Undo"); undo_b.clicked.connect(self._undo); bar.addWidget(undo_b)
        clr_b = QPushButton("Clear page"); clr_b.clicked.connect(self._clear_page); bar.addWidget(clr_b)
        bar.addStretch()

        self._prev = QPushButton("◀"); self._prev.clicked.connect(lambda: self._go(self.page - 1))
        self._next = QPushButton("▶"); self._next.clicked.connect(lambda: self._go(self.page + 1))
        self._page_lbl = QLabel("")
        bar.addWidget(self._prev); bar.addWidget(self._page_lbl); bar.addWidget(self._next)
        root.addLayout(bar)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self.canvas)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._scroll, 1)

        hint = QLabel("Drawings save automatically into the PDF when you close this window.")
        hint.setStyleSheet("color:#888; font-size:11px;")
        root.addWidget(hint)

        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self._save)

        self.resize(min(1200, QGuiApplication.primaryScreen().size().width() - 80),
                    min(900, QGuiApplication.primaryScreen().size().height() - 80))
        self._load_page(0)

    # -- tool ui --
    def _paint_color(self):
        self._color_btn.setStyleSheet(
            "background:%s;border:1px solid #888;border-radius:4px;" % self.color.name())

    def _pick_color(self):
        c = QColorDialog.getColor(self.color, self, "Colour")
        if c.isValid():
            self.color = c
            self._paint_color()

    def mark_dirty(self):
        self._dirty = True

    def _snapshot_current(self):
        self.page_strokes[self.page] = self.canvas.strokes

    def _undo(self):
        if self.undo_stack:
            idx, snap = self.undo_stack.pop()
            self.page_strokes[idx] = snap
            if idx == self.page:
                self.canvas.strokes = self.page_strokes[idx]
                self.canvas.update()

    def _pop_undo(self):
        if self.undo_stack:
            self.undo_stack.pop()

    def _push_undo(self):
        self.undo_stack.append((self.page, list(self.canvas.strokes)))
        if len(self.undo_stack) > 60:
            self.undo_stack.pop(0)

    def _clear_page(self):
        self._push_undo()
        self.canvas.strokes.clear()
        self.mark_dirty()
        self.canvas.update()

    # -- paging --
    def _render_base(self, idx: int) -> QPixmap:
        page = self.doc[idx]
        mat = self.fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                     QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(img)

    def _load_page(self, idx: int):
        base = self._render_base(idx)
        strokes = self.page_strokes.setdefault(idx, [])
        self.canvas.set_page(base, strokes)
        self._page_lbl.setText("  %d / %d  " % (idx + 1, self.doc.page_count))
        self._prev.setEnabled(idx > 0)
        self._next.setEnabled(idx < self.doc.page_count - 1)

    def _go(self, idx: int):
        if 0 <= idx < self.doc.page_count and idx != self.page:
            self._snapshot_current()
            self.page = idx
            self._load_page(idx)

    # intercept canvas strokes to also record undo
    def record_stroke_commit(self):
        pass

    # -- save --
    def _save(self):
        if self._saved:
            return
        self._snapshot_current()
        wrote = False
        for idx, strokes in self.page_strokes.items():
            if not strokes:
                continue
            page = self.doc[idx]
            for s in strokes:
                try:
                    if "text" in s:
                        x, y = s["pos"]
                        fs = max(8, s["width"] * 3) / self.zoom
                        rect = self.fitz.Rect(x / self.zoom, y / self.zoom,
                                              x / self.zoom + 320, y / self.zoom + fs + 8)
                        page.add_freetext_annot(rect, s["text"], fontsize=fs,
                                                text_color=_rgb01(s["color"]))
                    else:
                        pts = [self.fitz.Point(px / self.zoom, py / self.zoom)
                               for px, py in s["points"]]
                        if not pts:
                            continue
                        annot = page.add_ink_annot([pts])
                        annot.set_colors(stroke=_rgb01(s["color"]))
                        annot.set_border(width=max(0.5, s["width"] / self.zoom))
                        if s["tool"] == "highlighter":
                            annot.set_opacity(0.4)
                        annot.update()
                    wrote = True
                except Exception as exc:
                    print("[Annotator] stroke save failed:", exc)
        if not wrote:
            try:
                self.doc.close()
            except Exception:
                pass
            self._saved = True
            return
        ok = False
        try:
            self.doc.saveIncr()
            ok = True
        except Exception:
            try:
                tmp = self.path + ".__annotated.pdf"
                self.doc.save(tmp, garbage=3, deflate=True)
                self.doc.close()
                os.replace(tmp, self.path)
                ok = True
            except Exception as exc:
                showWarning("Could not save annotations (is the file open elsewhere?):\n%s" % exc)
        try:
            self.doc.close()
        except Exception:
            pass
        self._saved = True
        if ok:
            tooltip("Annotations saved ✓", period=2500)

    def closeEvent(self, e):
        self._save()
        super().closeEvent(e)


# ── public ─────────────────────────────────────────────────────────────────────

_OPEN: list = []   # keep references so the non-modal windows aren't GC'd


def open_annotator(parent, pdf_path: str) -> bool:
    if not os.path.isfile(pdf_path):
        showWarning("File not found:\n%s" % pdf_path)
        return False
    fitz = _ensure_fitz()
    if fitz is None:
        showWarning("The PDF engine (PyMuPDF) couldn't be installed.\n"
                    "Check your internet connection and restart Anki, or set the "
                    "file type to open in the browser instead.")
        return False
    try:
        dlg = Annotator(parent or mw, pdf_path, fitz)
    except Exception as exc:
        showWarning("Could not open the annotator:\n%s" % exc)
        return False
    _OPEN.append(dlg)
    dlg.finished.connect(lambda _code=0, d=dlg: _OPEN.remove(d) if d in _OPEN else None)
    dlg.setModal(False)
    dlg.show()
    dlg.raise_()
    return True
