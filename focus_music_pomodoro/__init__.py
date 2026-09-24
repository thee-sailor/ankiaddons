# Focus Music & Pomodoro Player
#
# Based on the "Focus Music & Pomodoro Player" add-on published on AnkiWeb
# (add-on ID 1540641384): https://ankiweb.net/shared/info/1540641384
# Original author: the AnkiWeb publisher of that add-on (name not recorded in
# the distributed package). This is a modified version that adds a customizable
# multi-phase cycle, per-phase notifications, and a phase-jump menu.
#
# Credit for the original work belongs to its author. If you are that author
# and want a specific credit line or a different license for this folder,
# please open an issue on the repository.

import os
import random
import json
import time
from datetime import datetime
from aqt import mw, gui_hooks
from aqt.qt import *
from aqt.utils import showInfo, tooltip, openLink
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QTextCharFormat, QFont, QIcon, QPixmap

# Default repeating cycle (edit in Settings). Each phase: name, minutes, kind.
# kind "work"  → counts toward the daily goal and plays music
# kind "break" → pauses music, doesn't count
DEFAULT_PHASES = [
    {"name": "Study",             "minutes": 20, "kind": "work"},
    {"name": "Genuine break",     "minutes": 3,  "kind": "break"},
    {"name": "Value-added break", "minutes": 5,  "kind": "break"},
]

KIND_LABELS = [("Study (work)", "work"), ("Break", "break")]


# --- RESIZE EVENT FILTER ---
class _ResizeFilter(QObject):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self._cb = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Resize:
            self._cb()
        return False


# --- CONFIGURATION DIALOG ---
class ConfigDialog(QDialog):
    def __init__(self, parent, phases, daily_goal, music_path, notify_popup):
        super().__init__(parent)
        self.setWindowTitle("Pomodoro Settings")
        self.setMinimumSize(500, 500)
        self.music_path = music_path
        self.rows = [dict(p) for p in phases] if phases else [dict(p) for p in DEFAULT_PHASES]

        root = QVBoxLayout(self)

        head = QLabel("<b>Cycle phases</b> — they run top-to-bottom, then repeat.")
        root.addWidget(head)
        hint = QLabel("Add as many as you like (e.g. Study → Genuine break → "
                      "Value-added break → …). A notification fires at each change.")
        hint.setStyleSheet("color:#888; font-size:11px;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Phase name", "Minutes", "Type"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table)

        btns = QHBoxLayout()
        for label, fn in (("＋ Add", self.add_row), ("－ Remove", self.remove_row),
                          ("↑ Up", self.move_up), ("↓ Down", self.move_down)):
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            btns.addWidget(b)
        root.addLayout(btns)

        form = QFormLayout()
        self.goal_spin = QSpinBox()
        self.goal_spin.setRange(1, 50)
        self.goal_spin.setValue(daily_goal)
        self.goal_spin.setSuffix(" 🍅")
        form.addRow("Daily goal (study phases):", self.goal_spin)

        self.notify_cb = QCheckBox("Pop-up between phases (waits for you to click OK)")
        self.notify_cb.setChecked(notify_popup)
        self.notify_cb.setToolTip("On: a dialog announces the next phase and the "
                                  "countdown resumes when you click OK.\n"
                                  "Off: a quick tooltip appears and the next phase "
                                  "starts automatically.")
        form.addRow("Notifications:", self.notify_cb)

        self.path_label = QLabel(self.music_path if self.music_path else "Default (Add-on Folder)")
        self.path_label.setStyleSheet("color: #777; font-size: 10px;")
        btn_browse = QPushButton("📂 Choose Music Folder")
        btn_browse.clicked.connect(self.browse_folder)
        ml = QVBoxLayout()
        ml.addWidget(btn_browse)
        ml.addWidget(self.path_label)
        form.addRow("Music:", ml)
        root.addLayout(form)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

        self._render()

    def _render(self):
        self.table.setRowCount(len(self.rows))
        for r, p in enumerate(self.rows):
            self.table.setItem(r, 0, QTableWidgetItem(str(p.get("name", "Phase"))))
            spin = QSpinBox()
            spin.setRange(1, 240)
            spin.setValue(int(p.get("minutes", 5)))
            spin.setSuffix(" min")
            self.table.setCellWidget(r, 1, spin)
            combo = QComboBox()
            for lab, _k in KIND_LABELS:
                combo.addItem(lab)
            combo.setCurrentIndex(0 if p.get("kind", "work") == "work" else 1)
            self.table.setCellWidget(r, 2, combo)

    def _read(self):
        rows = []
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 0)
            name = name_item.text().strip() if name_item else ""
            spin = self.table.cellWidget(r, 1)
            minutes = spin.value() if spin else 5
            combo = self.table.cellWidget(r, 2)
            kind = KIND_LABELS[combo.currentIndex()][1] if combo else "work"
            rows.append({"name": name or "Phase", "minutes": int(minutes), "kind": kind})
        self.rows = rows

    def add_row(self):
        self._read()
        self.rows.append({"name": "New phase", "minutes": 5, "kind": "break"})
        self._render()
        self.table.setCurrentCell(len(self.rows) - 1, 0)

    def remove_row(self):
        self._read()
        r = self.table.currentRow()
        if 0 <= r < len(self.rows) and len(self.rows) > 1:
            self.rows.pop(r)
            self._render()

    def move_up(self):
        self._read()
        r = self.table.currentRow()
        if r > 0:
            self.rows[r - 1], self.rows[r] = self.rows[r], self.rows[r - 1]
            self._render()
            self.table.setCurrentCell(r - 1, 0)

    def move_down(self):
        self._read()
        r = self.table.currentRow()
        if 0 <= r < len(self.rows) - 1:
            self.rows[r + 1], self.rows[r] = self.rows[r], self.rows[r + 1]
            self._render()
            self.table.setCurrentCell(r + 1, 0)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if folder:
            self.music_path = folder
            self.path_label.setText(folder)

    def _on_ok(self):
        self._read()
        if not self.rows:
            self.rows = [dict(p) for p in DEFAULT_PHASES]
        self.accept()

    def get_values(self):
        return self.rows, self.goal_spin.value(), self.music_path, self.notify_cb.isChecked()


# --- HISTORY DIALOG ---
class HistoryDialog(QDialog):
    def __init__(self, parent, history_data, daily_goal, on_reset_callback):
        super().__init__(parent)
        self.setWindowTitle("Pomodoro History"); self.setFixedSize(400, 450)
        self.history_data = history_data; self.daily_goal = daily_goal; self.on_reset_callback = on_reset_callback
        layout = QVBoxLayout()
        self.calendar = QCalendarWidget(); self.calendar.setGridVisible(False)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        is_night = mw.pm.night_mode()
        bg = "#2f2f31" if is_night else "#ffffff"; fg = "#eeeeee" if is_night else "#333333"
        sel = "#3daee9" if is_night else "#007bff"; hov = "#555" if is_night else "#e6e6e6"
        self.calendar.setStyleSheet(f"""
            QCalendarWidget QWidget {{ background-color: {bg}; color: {fg}; }}
            QCalendarWidget QToolButton {{ color: {fg}; background-color: transparent; border: none; margin: 5px; font-weight: bold; }}
            QCalendarWidget QToolButton:hover {{ background-color: {hov}; border-radius: 4px; }}
            QCalendarWidget QAbstractItemView:enabled {{ color: {fg}; background-color: {bg}; selection-background-color: {sel}; selection-color: white; outline: 0; }}
        """)
        self.calendar.selectionChanged.connect(self.update_stats); self.highlight_dates(); layout.addWidget(self.calendar)
        self.stats_label = QLabel("Select a date"); self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stats_label.setStyleSheet(f"font-size: 14px; font-weight: bold; margin: 15px; color: {fg};"); layout.addWidget(self.stats_label)
        self.btn_reset_today = QPushButton("🗑️ Reset Today's History"); self.btn_reset_today.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_today.setStyleSheet("QPushButton { color: #dc3545; border: 1px solid #dc3545; border-radius: 5px; padding: 6px; font-weight: bold; } QPushButton:hover { background-color: #dc3545; color: white; }")
        self.btn_reset_today.clicked.connect(self.reset_today); layout.addWidget(self.btn_reset_today)
        self.setLayout(layout); self.update_stats()

    def highlight_dates(self):
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())
        vf = QTextCharFormat(); vf.setBackground(QBrush(QColor("#d4edda"))); vf.setForeground(QBrush(QColor("#000000"))); vf.setFontWeight(QFont.Weight.Bold)
        gf = QTextCharFormat(); gf.setBackground(QBrush(QColor("#28a745"))); gf.setForeground(QBrush(QColor("white"))); gf.setFontWeight(QFont.Weight.Bold)
        for date_str, count in self.history_data.items():
            try:
                qd = QDate.fromString(date_str, "yyyy-MM-dd")
                self.calendar.setDateTextFormat(qd, gf if count >= self.daily_goal else vf)
            except: continue

    def update_stats(self):
        sd = self.calendar.selectedDate().toString("yyyy-MM-dd"); count = self.history_data.get(sd, 0)
        emoji_str = "🍅" * min(count, 10) + ("..." if count > 10 else "")
        if count == 0:
            self.stats_label.setText(f"{sd}\nNo activity"); self.btn_reset_today.setEnabled(False)
            self.btn_reset_today.setStyleSheet("color: #777; border: 1px solid #777; border-radius: 5px; padding: 6px;")
        else:
            self.stats_label.setText(f"{sd}\nCompleted: {count}\n{emoji_str}"); self.btn_reset_today.setEnabled(True)
            self.btn_reset_today.setStyleSheet("QPushButton { color: #dc3545; border: 1px solid #dc3545; border-radius: 5px; padding: 6px; font-weight: bold; } QPushButton:hover { background-color: #dc3545; color: white; }")

    def reset_today(self):
        sd = self.calendar.selectedDate().toString("yyyy-MM-dd"); today = datetime.now().strftime("%Y-%m-%d")
        if sd == today:
            if QMessageBox.question(self, "Confirm Reset", "Clear today's history?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.on_reset_callback(sd); self.history_data.pop(sd, None); self.highlight_dates(); self.update_stats(); tooltip("History cleared")
        else: tooltip("You can only reset the current day.")


# --- MAIN PLAYER ---
class FocusMusicPlayer:
    def __init__(self):
        self.settings = QSettings("Anki", "FocusMusicAddon")
        self.saved_volume    = int(self.settings.value("volume", 50))
        self.daily_goal      = int(self.settings.value("daily_goal", 4))
        self.music_path      = self.settings.value("music_path", "")
        self.notify_popup    = self.settings.value("notify_popup", True, type=bool)
        try:
            self.history_data = json.loads(self.settings.value("history_data", "{}"))
        except Exception:
            self.history_data = {}

        # --- multi-phase cycle ---
        self.phases = self._load_phases()
        self.phase_index = int(self.settings.value("phase_index", 0))
        if not (0 <= self.phase_index < len(self.phases)):
            self.phase_index = 0

        self.addon_path = os.path.dirname(__file__)
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(self.saved_volume / 100)

        self.timer_end_timestamp = float(self.settings.value("timer_end_timestamp", 0))
        self.timer_was_running = self.settings.value("timer_was_running", False, type=bool)

        self.current_time = self._phase_seconds(self.phase_index)
        self.timer = QTimer(); self.timer.timeout.connect(self.update_timer)
        self.timer_running = False; self.paused_by_card = False

        self.load_playlist()
        self.setup_ui()

        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)

        gui_hooks.state_did_change.append(self.update_visibility)
        gui_hooks.reviewer_did_show_question.append(self.on_card_show)
        gui_hooks.profile_will_close.append(self.save_state_on_close)
        gui_hooks.deck_browser_did_render.append(self._hide_native_bottom)

        self.update_visibility(mw.state, None)
        self.update_progress_display()
        self.restore_state()

    # ── phase helpers ───────────────────────────────────────────────────────────

    def _load_phases(self):
        try:
            raw = self.settings.value("phases", "")
            if raw:
                data = json.loads(raw)
                phases = []
                for p in data:
                    if not isinstance(p, dict):
                        continue
                    phases.append({
                        "name": str(p.get("name", "Phase")),
                        "minutes": max(1, int(p.get("minutes", 5))),
                        "kind": "work" if p.get("kind") == "work" else "break",
                    })
                if phases:
                    return phases
        except Exception:
            pass
        return [dict(p) for p in DEFAULT_PHASES]

    def current_phase(self):
        return self.phases[self.phase_index]

    def _phase_seconds(self, i):
        return int(self.phases[i]["minutes"]) * 60

    def _is_work_phase(self):
        return self.current_phase().get("kind") == "work"

    def load_playlist(self):
        valid_extensions = (".mp3", ".mp4", ".m4a", ".wav")
        search_path = self.music_path if self.music_path and os.path.exists(self.music_path) else self.addon_path
        self.playlist = [os.path.join(search_path, f) for f in os.listdir(search_path) if f.lower().endswith(valid_extensions)] if os.path.exists(search_path) else []

    def save_state_on_close(self):
        self.settings.setValue("phase_index", self.phase_index)
        self.settings.setValue("timer_was_running", self.timer_running)
        if self.timer_running:
            self.settings.setValue("timer_end_timestamp", time.time() + self.current_time)
        else:
            self.settings.setValue("timer_end_timestamp", 0)
            self.settings.setValue("saved_remaining_time", self.current_time)

    def restore_state(self):
        if self.timer_was_running:
            remaining = self.timer_end_timestamp - time.time()
            if remaining > 0:
                self.current_time = int(remaining); self.timer.start(1000)
                self.timer_running = True; self.update_ui_for_state_running()
            else:
                self.current_time = self._phase_seconds(self.phase_index)
                self.timer_running = False; self.update_ui_for_state_paused()
        else:
            self.current_time = int(self.settings.value("saved_remaining_time", self._phase_seconds(self.phase_index)))
            self.update_ui_for_state_paused()

    def get_pomodoro_icon(self, color_hex):
        pixmap = QPixmap(32, 32); pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(color_hex))); painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 6, 24, 22)
        painter.setBrush(QBrush(QColor("#2ed573")))
        painter.drawPie(12, 0, 8, 12, 60 * 16, 60 * 16)
        painter.drawPie(14, 0, 6, 10, 60 * 16, 120 * 16)
        painter.end(); return QIcon(pixmap)

    def setup_ui(self):
        is_night = mw.pm.night_mode()
        bg     = "#1e1e2e" if is_night else "#f5f5f7"
        fg     = "#cdd6f4" if is_night else "#333333"
        border = "#313244" if is_night else "#dcdcdc"
        hov    = "#313244" if is_night else "#e8e8ee"
        sep    = "#45475a" if is_night else "#d0d0d8"

        self.container_widget = QWidget()
        self.container_widget.setMinimumHeight(46)
        self.container_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.container_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border-top: 1px solid {border};
            }}
            QPushButton {{
                background: transparent; border: none; color: {fg};
                font-size: 11px; font-weight: 600; border-radius: 6px;
                padding: 3px 8px; min-height: 28px;
            }}
            QPushButton:hover {{ background: {hov}; }}
            QLabel {{
                color: {fg}; font-size: 11px; font-weight: bold; border: none;
            }}
            QSlider::groove:horizontal {{ height: 3px; background: {sep}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: #7c3aed; width: 12px; height: 12px; margin: -5px 0; border-radius: 6px; }}
            QSlider::sub-page:horizontal {{ background: #7c3aed; border-radius: 2px; }}
        """)

        row = QHBoxLayout(self.container_widget)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(4)
        row.setAlignment(Qt.AlignmentFlag.AlignTop)

        def _deck_btn(icon, label, callback):
            b = QPushButton(f"{icon} {label}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(callback)
            return b

        row.addWidget(_deck_btn("📥", "Get Shared",  self._get_shared))
        row.addWidget(_deck_btn("＋", "Create Deck", self._create_deck))
        row.addWidget(_deck_btn("📁", "Import File", self._import_file))

        sep_line = QFrame(); sep_line.setFrameShape(QFrame.Shape.VLine)
        sep_line.setStyleSheet(f"color: {sep}; border: none; border-left: 1px solid {sep};")
        sep_line.setFixedWidth(12); row.addWidget(sep_line)

        self.frame = self.container_widget

        self.btn_play = QPushButton(); self.btn_play.setFixedSize(28, 28)
        self.btn_play.setIcon(self.container_widget.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_play.clicked.connect(self.toggle_play); row.addWidget(self.btn_play)

        self.btn_prev = QPushButton(); self.btn_prev.setFixedSize(28, 28)
        self.btn_prev.setIcon(self.container_widget.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.btn_prev.clicked.connect(self.prev_track); row.addWidget(self.btn_prev)

        self.btn_next = QPushButton(); self.btn_next.setFixedSize(28, 28)
        self.btn_next.setIcon(self.container_widget.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        self.btn_next.clicked.connect(self.next_track); row.addWidget(self.btn_next)

        self.lbl_info = QLabel("Focus Music"); self.lbl_info.setFixedWidth(90)
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter); row.addWidget(self.lbl_info)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal); self.seek_slider.setRange(0, 0)
        self.seek_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.seek_slider.sliderMoved.connect(self.set_position); row.addWidget(self.seek_slider, stretch=1)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet(f"color: {sep}; border: none; border-left: 1px solid {sep};")
        sep2.setFixedWidth(12); row.addWidget(sep2)

        # Current phase — click to jump to any phase in the cycle
        self.btn_phase = QPushButton("")
        self.btn_phase.setFixedWidth(94)
        self.btn_phase.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_phase.setToolTip("Current phase — click to switch to another")
        self.btn_phase.clicked.connect(self.show_phase_menu)
        row.addWidget(self.btn_phase)

        self.btn_timer = QPushButton(); self.btn_timer.setIcon(self.get_pomodoro_icon("#ff4757"))
        self.btn_timer.setIconSize(QSize(20, 20)); self.btn_timer.setFixedSize(28, 28)
        self.btn_timer.setToolTip("Left-click: start/pause · Right-click: reset to first phase")
        self.btn_timer.clicked.connect(self.toggle_timer)
        self.btn_timer.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_timer.customContextMenuRequested.connect(lambda _pos: self.reset_timer())
        row.addWidget(self.btn_timer)

        self.lbl_timer = QLabel(self.format_time(self.current_time))
        self.lbl_timer.setFixedWidth(42); self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.lbl_timer)

        self.lbl_progress = QLabel("0/4"); self.lbl_progress.setToolTip("Daily study phases")
        self.lbl_progress.setFixedWidth(32); self.lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_progress.setStyleSheet("color: #a78bfa; font-weight:700; font-size:11px;")
        row.addWidget(self.lbl_progress)

        sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setStyleSheet(f"color: {sep}; border: none; border-left: 1px solid {sep};")
        sep3.setFixedWidth(12); row.addWidget(sep3)

        lbl_vol = QLabel("🔊"); lbl_vol.setFixedWidth(18); row.addWidget(lbl_vol)
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100); self.vol_slider.setValue(self.saved_volume)
        self.vol_slider.setFixedWidth(55); self.vol_slider.valueChanged.connect(self.set_volume)
        row.addWidget(self.vol_slider)

        self.btn_history = QPushButton("📅"); self.btn_history.setFixedSize(28, 28)
        self.btn_history.setToolTip("History"); self.btn_history.clicked.connect(self.open_history)
        row.addWidget(self.btn_history)

        self.btn_config = QPushButton("⚙️"); self.btn_config.setFixedSize(28, 28)
        self.btn_config.setToolTip("Settings"); self.btn_config.clicked.connect(self.open_settings)
        row.addWidget(self.btn_config)

        # Float the bar as an overlay at the bottom of the central widget
        # so it sits on top of the native deck-browser bottom bar.
        cw = mw.centralWidget()
        self.container_widget.setParent(cw)
        self._reposition_bar()
        self.container_widget.raise_()
        self.container_widget.show()

        self._update_phase_label("#888")

        self._resize_filter = _ResizeFilter(cw, self._reposition_bar)
        cw.installEventFilter(self._resize_filter)

    def _get_shared(self):
        try: openLink("https://ankiweb.net/shared/decks/")
        except: mw.deckBrowser.web.eval("pycmd('shared')")

    def _create_deck(self):
        mw.deckBrowser.web.eval("pycmd('create')")

    def _import_file(self):
        try:
            from aqt.importing import import_file
            import_file(mw)
        except Exception:
            mw.deckBrowser.web.eval("pycmd('import')")

    def get_today_str(self): return datetime.now().strftime("%Y-%m-%d")

    def save_completed_pomodoro(self):
        today = self.get_today_str(); current_count = self.history_data.get(today, 0)
        self.history_data[today] = current_count + 1
        self.settings.setValue("history_data", json.dumps(self.history_data))
        self.update_progress_display()

    def reset_today_history(self, date_key):
        if date_key in self.history_data:
            del self.history_data[date_key]
            self.settings.setValue("history_data", json.dumps(self.history_data)); self.update_progress_display()

    def update_progress_display(self):
        today = self.get_today_str(); count = self.history_data.get(today, 0)
        self.lbl_progress.setText(f"{count}/{self.daily_goal}")
        self.lbl_progress.setStyleSheet("color: #28a745; font-weight:700;" if count >= self.daily_goal else "color: #a78bfa; font-weight:700;")

    def _update_phase_label(self, color):
        name = self.current_phase().get("name", "")
        disp = name if len(name) <= 9 else name[:8] + "…"
        self.btn_phase.setText(f"{disp} ▾")
        self.btn_phase.setToolTip(f"{name} — {self.current_phase().get('minutes')} min\n(click to switch)")
        self.btn_phase.setStyleSheet(
            f"QPushButton {{ color: {color}; font-weight:700; font-size:11px; }}"
        )

    def update_ui_for_state_running(self):
        # Red = study/work, Green = break
        work = self._is_work_phase()
        color = "#ef4444" if work else "#28a745"
        self.lbl_timer.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")
        self.btn_timer.setIcon(self.get_pomodoro_icon("#ff4757" if work else "#2ed573"))
        self._update_phase_label(color)

    def update_ui_for_state_paused(self):
        self.lbl_timer.setStyleSheet("color: #888; font-size: 12px;")
        self.btn_timer.setIcon(self.get_pomodoro_icon("#ff4757"))
        self.lbl_timer.setText(self.format_time(self.current_time))
        self._update_phase_label("#888")

    def open_history(self):
        HistoryDialog(self.container_widget, self.history_data, self.daily_goal, self.reset_today_history).exec()

    def open_settings(self):
        dialog = ConfigDialog(self.container_widget, self.phases, self.daily_goal, self.music_path, self.notify_popup)
        if dialog.exec():
            self.phases, self.daily_goal, self.music_path, self.notify_popup = dialog.get_values()
            self.settings.setValue("phases", json.dumps(self.phases))
            self.settings.setValue("daily_goal", self.daily_goal)
            self.settings.setValue("music_path", self.music_path)
            self.settings.setValue("notify_popup", self.notify_popup)
            self.load_playlist(); self.update_progress_display(); self.reset_timer(); tooltip("Settings Saved")

    def format_time(self, seconds):
        m, s = divmod(max(0, int(seconds)), 60); return f"{m:02}:{s:02}"

    def toggle_timer(self):
        if self.timer_running:
            self.timer.stop(); self.timer_running = False; self.update_ui_for_state_paused()
        else:
            self.timer.start(1000); self.timer_running = True; self.update_ui_for_state_running()
            # Start music if the current phase is a study/work phase
            if self._is_work_phase() and self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.toggle_play()

    def reset_timer(self):
        self.timer.stop(); self.timer_running = False
        self.phase_index = 0
        self.current_time = self._phase_seconds(self.phase_index)
        self.lbl_timer.setText(self.format_time(self.current_time))
        self.update_ui_for_state_paused()

    def show_phase_menu(self):
        """Dropdown to jump straight to any phase (e.g. from Study to a break)."""
        menu = QMenu(self.container_widget)
        act_next = menu.addAction("⏭  Skip to next phase")
        act_next.triggered.connect(self.skip_to_next)
        menu.addSeparator()
        for i, p in enumerate(self.phases):
            emoji = "📖" if p.get("kind") == "work" else "☕"
            mark = "● " if i == self.phase_index else "    "
            act = menu.addAction(f"{mark}{emoji}  {p['name']} — {p['minutes']} min")
            act.triggered.connect(lambda _checked=False, idx=i: self.jump_to_phase(idx))
        menu.addSeparator()
        act_reset = menu.addAction("↺  Reset to first phase")
        act_reset.triggered.connect(self.reset_timer)
        menu.exec(self.btn_phase.mapToGlobal(QPoint(0, self.btn_phase.height())))

    def jump_to_phase(self, index, start=True):
        """Switch to a chosen phase and (by default) start its countdown.
        Skipping a study phase this way does NOT count it toward the goal."""
        if not (0 <= index < len(self.phases)):
            return
        self.timer.stop()
        self.phase_index = index
        self.current_time = self._phase_seconds(index)
        p = self.current_phase()
        if p.get("kind") == "work":
            self.player.play()
        else:
            self.player.pause()
        if start:
            self.timer.start(1000); self.timer_running = True
            self.update_ui_for_state_running()
        else:
            self.timer_running = False
            self.update_ui_for_state_paused()
        tooltip(f"▶ {p['name']} — {p['minutes']} min", period=2500)

    def skip_to_next(self):
        self.jump_to_phase((self.phase_index + 1) % len(self.phases))

    def _advance_phase(self):
        """Move to the next phase in the cycle, wrapping around, and fire the
        boundary notification. Music follows the phase kind."""
        finished = self.current_phase()
        if finished.get("kind") == "work":
            self.save_completed_pomodoro()

        self.phase_index = (self.phase_index + 1) % len(self.phases)
        nxt = self.current_phase()
        self.current_time = self._phase_seconds(self.phase_index)

        # Music: play on study phases, pause on breaks
        if nxt.get("kind") == "work":
            self.player.play()
        else:
            self.player.pause()

        self.update_ui_for_state_paused()  # show next phase name + full time

        emoji = "📖" if nxt.get("kind") == "work" else "☕"
        msg = (f"✅ {finished['name']} finished.\n\n"
               f"{emoji} Next: {nxt['name']} — {nxt['minutes']} min")
        if self.notify_popup:
            showInfo(msg, title="Pomodoro")
        else:
            tooltip(msg, period=4500)

        # Resume the countdown for the next phase
        self.timer.start(1000); self.timer_running = True
        self.update_ui_for_state_running()

    def update_timer(self):
        self.current_time -= 1
        if self.current_time > 0:
            self.lbl_timer.setText(self.format_time(self.current_time))
            return
        # Phase finished — stop before any modal so the timer can't re-fire
        self.timer.stop()
        self.timer_running = False
        self.lbl_timer.setText("00:00")
        QApplication.beep()
        self._advance_phase()

    def on_card_show(self, card):
        has_sound = "[sound:" in card.question() or "<audio" in card.question()
        if has_sound:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause(); self.paused_by_card = True
                self.btn_play.setIcon(self.container_widget.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        elif self.paused_by_card:
            self.player.play(); self.paused_by_card = False
            self.btn_play.setIcon(self.container_widget.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

    def get_random_track(self):
        if not self.playlist: return None
        selection = random.choice(self.playlist); self.current_filename = selection; return selection

    def prev_track(self):
        if self.player.position() > 3000:
            self.player.setPosition(0)
        else:
            track_path = self.get_random_track()
            if track_path:
                self.player.setSource(QUrl.fromLocalFile(track_path)); self.player.play()
                self.btn_play.setIcon(self.container_widget.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause(); self.paused_by_card = False
            self.btn_play.setIcon(self.container_widget.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        else:
            if self.player.mediaStatus() == QMediaPlayer.MediaStatus.NoMedia: self.next_track()
            else: self.player.play()
            self.btn_play.setIcon(self.container_widget.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

    def next_track(self):
        track_path = self.get_random_track()
        if track_path:
            self.player.setSource(QUrl.fromLocalFile(track_path)); self.player.play()
            self.btn_play.setIcon(self.container_widget.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

    def set_volume(self, value):
        self.audio_output.setVolume(value / 100); self.settings.setValue("volume", value)

    def set_position(self, position): self.player.setPosition(position)

    def on_position_changed(self, position):
        if not self.seek_slider.isSliderDown(): self.seek_slider.setValue(position)
        cur_min, cur_sec = divmod(position // 1000, 60)
        title = os.path.basename(self.current_filename) if hasattr(self, 'current_filename') else "Focus Music"
        if len(title) > 12: title = title[:10] + "…"
        self.lbl_info.setText(f"{title} {cur_min}:{cur_sec:02}")

    def on_duration_changed(self, duration): self.seek_slider.setRange(0, duration)

    def on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia: self.next_track()

    def _reposition_bar(self):
        try:
            cw = mw.centralWidget() or mw
            cw_h = cw.height()
            cw_w = cw.width()
            bar_h = 46
            # Extend downward past the visible area to swallow any native bar
            # that sits at or below the centralWidget's bottom edge.
            total_h = bar_h + 60
            y = cw_h - bar_h   # align top of our bar to where it should appear
            self.container_widget.setGeometry(0, y, cw_w, total_h)
            self.container_widget.raise_()
        except Exception:
            pass

    def _hide_native_bottom(self, _deck_browser=None):
        try:
            bottom = mw.deckBrowser.bottom
            # Collapse the inner webview — no layout manipulation
            bottom.web.setFixedHeight(0)
            # Also collapse the BottomBar container itself
            bottom.setFixedHeight(0)
        except Exception:
            pass

    def update_visibility(self, new_state, old_state):
        visible = new_state == "deckBrowser"
        self.container_widget.setVisible(visible)
        if visible:
            self._reposition_bar()


mw.focus_music = FocusMusicPlayer()
