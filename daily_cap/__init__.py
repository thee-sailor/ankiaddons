"""
Daily Card Cap — auto-runs on every Anki startup.

Algorithm (max_per_day = M):
  review_slots  = M // 2
  learn_slots   = M - review_slots   (gets extra on odd M)

  1. queue=2 (mature reviews):  cascade so each day ≤ review_slots
  2. queue=3 (day-learning):    cascade so each day ≤ remaining after reviews
     — overdue cards (due < today) are normalised to today before cascading
  3. queue=1 (intraday learning): excess rescheduled to tomorrow as queue=3
  4. queue=0 (new):  newPerDay set to remaining slots after 1+2+3
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Dict, List, Tuple

from aqt import mw, gui_hooks
from aqt.qt import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QCheckBox, QFrame, Qt
)
from aqt.utils import tooltip

# ── Config ─────────────────────────────────────────────────────────────────────

_CFG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
_DEFAULTS  = {"max_per_day": 15, "auto_run_on_startup": True}


def _load_cfg() -> dict:
    try:
        with open(_CFG_PATH, "r", encoding="utf-8") as f:
            return {**_DEFAULTS, **json.load(f)}
    except Exception:
        return dict(_DEFAULTS)


def _save_cfg(cfg: dict):
    try:
        with open(_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except Exception:
        pass


def _split(m: int) -> Tuple[int, int]:
    """(review_slots, learn_slots)."""
    r = m // 2
    return r, m - r

# ── Cascade ────────────────────────────────────────────────────────────────────

def _cascade(id_day: List[Tuple[int, int]], cap: int, first_day: int) -> Dict[int, int]:
    """
    Given a list of (card_id, due_day), ensure no day exceeds `cap`.
    Excess cards are pushed to the next day (greedy forward).
    Returns {card_id: new_due_day} for cards whose due day changes.
    """
    if not id_day:
        return {}

    orig: Dict[int, int] = {}
    bucket: Dict[int, List[int]] = defaultdict(list)
    for cid, day in id_day:
        orig[int(cid)] = int(day)
        bucket[int(day)].append(int(cid))

    max_day = max(bucket)
    day = first_day
    while day <= max_day:
        cards = bucket.get(day, [])
        if len(cards) > cap:
            nxt = day + 1
            bucket[nxt] = bucket.get(nxt, []) + cards[cap:]
            bucket[day]  = cards[:cap]
            if nxt > max_day:
                max_day = nxt
        day += 1

    changes: Dict[int, int] = {}
    for d, cards in bucket.items():
        for cid in cards:
            if orig.get(cid) != d:
                changes[cid] = d
    return changes

# ── Compute ────────────────────────────────────────────────────────────────────

def _compute_all(max_per_day: int):
    """
    Returns (rev_changes, dl_changes, il_reschedule_ids, new_per_day,
             today_before, today_after).
    today_before = total cards due today before any changes.
    today_after  = total cards that will remain for today after changes.
    """
    today   = mw.col.sched.today
    cutoff  = mw.col.sched.day_cutoff
    rev_slots, learn_slots = _split(max_per_day)

    # ── 1. Mature reviews (queue=2) ───────────────────────────────────────────
    all_reviews = mw.col.db.all("SELECT id, due FROM cards WHERE queue=2")
    # Normalise overdue to today so cascade starts from today
    rev_id_day = [(int(r[0]), max(int(r[1]), today)) for r in all_reviews]
    rev_changes = _cascade(rev_id_day, rev_slots, today)

    rev_today_before = sum(1 for _, d in rev_id_day if d == today)
    rev_today_after  = min(rev_today_before, rev_slots)

    # ── 2. Day-learning (queue=3) ─────────────────────────────────────────────
    all_dl = mw.col.db.all("SELECT id, due FROM cards WHERE queue=3")
    # Normalise overdue to today
    dl_id_day = [(int(r[0]), max(int(r[1]), today)) for r in all_dl]

    # Today's cap for learning = remaining slots after reviews kept
    dl_today_cap = max(0, max_per_day - rev_today_after)
    # Future days cap = learn_slots (reviews fill the other half)
    # We split today and future, cascade separately
    dl_today_ids = [cid for cid, d in dl_id_day if d == today]
    dl_future    = [(cid, d) for cid, d in dl_id_day if d != today]

    dl_changes: Dict[int, int] = {}
    dl_excess_today = dl_today_ids[dl_today_cap:]
    dl_kept_today   = dl_today_ids[:dl_today_cap]

    for cid in dl_excess_today:
        dl_changes[cid] = today + 1

    # Merge excess into future and cascade from tomorrow
    future_combined = [(cid, today + 1) for cid in dl_excess_today] + dl_future
    dl_changes.update(_cascade(future_combined, learn_slots, today + 1))

    dl_today_before = len(dl_today_ids)
    dl_today_after  = len(dl_kept_today)

    # ── 3. Intraday learning (queue=1) ────────────────────────────────────────
    il_rows = mw.col.db.all(
        "SELECT id FROM cards WHERE queue=1 AND due<?", cutoff
    )
    il_ids_all   = [int(r[0]) for r in il_rows]
    il_slots_left = max(0, max_per_day - rev_today_after - dl_today_after)
    il_reschedule = il_ids_all[il_slots_left:]

    il_today_before = len(il_ids_all)
    il_today_after  = il_today_before - len(il_reschedule)

    # ── 4. New cards ──────────────────────────────────────────────────────────
    new_per_day = max(0, max_per_day - rev_today_after - dl_today_after - il_today_after)

    # ── Summary ───────────────────────────────────────────────────────────────
    cur_new = _get_current_new_per_day()
    today_before = rev_today_before + dl_today_before + il_today_before + cur_new
    today_after  = rev_today_after  + dl_today_after  + il_today_after  + new_per_day

    return rev_changes, dl_changes, il_reschedule, new_per_day, today_before, today_after


def _get_current_new_per_day() -> int:
    try:
        vals = [c.get("new", {}).get("perDay", 9999)
                for c in mw.col.decks.all_config()]
        return min(vals) if vals else 0
    except Exception:
        return 0


def _set_new_per_day(n: int):
    try:
        for conf in mw.col.decks.all_config():
            conf["new"]["perDay"] = n
            mw.col.decks.save_config(conf)
    except Exception:
        pass

# ── Apply ───────────────────────────────────────────────────────────────────────

def _apply(rev_changes: Dict[int, int],
           dl_changes: Dict[int, int],
           il_reschedule: List[int],
           new_per_day: int):
    now = "CAST(strftime('%s','now') AS INT)"
    tomorrow = mw.col.sched.today + 1

    if rev_changes:
        mw.col.db.executemany(
            f"UPDATE cards SET due=?, mod={now}, usn=-1 WHERE id=?",
            [(due, cid) for cid, due in rev_changes.items()]
        )

    if dl_changes:
        mw.col.db.executemany(
            f"UPDATE cards SET due=?, mod={now}, usn=-1 WHERE id=?",
            [(due, cid) for cid, due in dl_changes.items()]
        )

    if il_reschedule:
        ph = ",".join("?" * len(il_reschedule))
        mw.col.db.execute(
            f"UPDATE cards SET queue=3, due=?, mod={now}, usn=-1 WHERE id IN ({ph})",
            tomorrow, *il_reschedule
        )

    _set_new_per_day(new_per_day)
    mw.col.db.execute(f"UPDATE col SET mod={now}")
    mw.reset()

# ── Stylesheet ──────────────────────────────────────────────────────────────────

STYLE = """
QDialog { background:#1a1a2e; color:#e2e8f0; }
QLabel  { color:#e2e8f0; }
QSpinBox {
    background:#0f0f17; color:#e2e8f0; border:1px solid #3a2a6e;
    border-radius:6px; padding:6px 10px; font-size:16px; min-width:80px;
}
QSpinBox::up-button, QSpinBox::down-button { background:#2a1a5e; border:none; width:20px; }
QCheckBox { color:#e2e8f0; spacing:6px; }
QCheckBox::indicator {
    width:15px; height:15px; border:1px solid #3a2a6e;
    border-radius:3px; background:#0f0f17;
}
QCheckBox::indicator:checked { background:#7c3aed; }
QPushButton {
    background:#2a1a5e; color:#e2e8f0; border:1px solid #3a2a6e;
    border-radius:8px; padding:8px 22px; font-size:13px;
}
QPushButton:hover  { background:#3a2a7e; }
QPushButton#apply  { background:#7c3aed; border-color:#9f6ff5; font-weight:bold; }
QPushButton#apply:hover { background:#9f6ff5; }
QPushButton#cancel { background:#1a1a2e; }
QFrame#div { background:#2a2a40; max-height:1px; }
"""

# ── Dialog ──────────────────────────────────────────────────────────────────────

class CapDialog(QDialog):
    def __init__(self):
        super().__init__(mw)
        self.setWindowTitle("Daily Card Cap")
        self.setMinimumWidth(440)
        self.setStyleSheet(STYLE)

        cfg       = _load_cfg()
        self._max = cfg["max_per_day"]
        self._rev_changes: Dict[int, int] = {}
        self._dl_changes:  Dict[int, int] = {}
        self._il_ids:      List[int]      = []
        self._new_pd: int = 0

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Daily Card Cap")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#a78bfa;")
        root.addWidget(title)

        note = QLabel(
            "Redistributes excess cards to future days — nothing is lost.\n"
            "Reviews and learning are rescheduled to specific future dates."
        )
        note.setStyleSheet("font-size:12px; color:#7c7ca0;")
        root.addWidget(note)

        div0 = QFrame(); div0.setObjectName("div")
        div0.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(div0)

        row = QHBoxLayout()
        lbl = QLabel("Max total cards per day")
        lbl.setStyleSheet("font-size:14px;")
        row.addWidget(lbl); row.addStretch()
        self._spin = QSpinBox()
        self._spin.setRange(1, 500)
        self._spin.setValue(self._max)
        row.addWidget(self._spin)
        root.addLayout(row)

        self._split_lbl = QLabel()
        self._split_lbl.setStyleSheet("font-size:11px; color:#5a5a80;")
        self._split_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        root.addWidget(self._split_lbl)

        self._status = QLabel()
        self._status.setStyleSheet(
            "font-size:20px; font-weight:bold; color:#34d399;"
            "padding:18px; background:#0f0f17; border-radius:10px;"
        )
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._status)

        self._detail = QLabel()
        self._detail.setStyleSheet("font-size:11px; color:#5a5a80;")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setWordWrap(True)
        root.addWidget(self._detail)

        div1 = QFrame(); div1.setObjectName("div")
        div1.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(div1)

        self._auto_cb = QCheckBox("Automatically redistribute cards each time Anki starts")
        self._auto_cb.setChecked(cfg.get("auto_run_on_startup", True))
        root.addWidget(self._auto_cb)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        cancel_btn = QPushButton("Cancel"); cancel_btn.setObjectName("cancel")
        cancel_btn.clicked.connect(self.reject)
        self._apply_btn = QPushButton("Apply"); self._apply_btn.setObjectName("apply")
        self._apply_btn.clicked.connect(self._do_apply)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._apply_btn)
        root.addLayout(btn_row)

        self._spin.valueChanged.connect(self._on_changed)
        self._refresh()

    def _on_changed(self, val: int):
        self._max = val
        self._refresh()

    def _refresh(self):
        rv, lv = _split(self._max)
        self._split_lbl.setText(
            f"{'even' if self._max % 2 == 0 else 'odd'} max → "
            f"{rv} review slots + {lv} learning slots per day"
        )

        (self._rev_changes, self._dl_changes, self._il_ids,
         self._new_pd, before, after) = _compute_all(self._max)

        cur_new = _get_current_new_per_day()
        has_work = (bool(self._rev_changes) or bool(self._dl_changes)
                    or bool(self._il_ids) or cur_new != self._new_pd)

        if has_work:
            self._status.setText(f"Today:  {before}  →  {after}  cards")
            self._status.setStyleSheet(
                "font-size:20px; font-weight:bold; color:#34d399;"
                "padding:18px; background:#0f0f17; border-radius:10px;"
            )
            parts = []
            if self._rev_changes:
                parts.append(f"{len(self._rev_changes)} reviews rescheduled")
            if self._dl_changes:
                parts.append(f"{len(self._dl_changes)} day-learning rescheduled")
            if self._il_ids:
                parts.append(f"{len(self._il_ids)} learning → tomorrow")
            if cur_new != self._new_pd:
                parts.append(f"new/day {cur_new} → {self._new_pd}")
            self._detail.setText(" · ".join(parts))
            self._apply_btn.setText("Apply")
            self._apply_btn.setEnabled(True)
        else:
            self._status.setText(f"Today:  {before}  cards  ✓")
            self._status.setStyleSheet(
                "font-size:20px; font-weight:bold; color:#7c7ca0;"
                "padding:18px; background:#0f0f17; border-radius:10px;"
            )
            self._detail.setText("Already at or under the daily limit.")
            self._apply_btn.setText("Nothing to change")
            self._apply_btn.setEnabled(False)

    def _do_apply(self):
        _apply(self._rev_changes, self._dl_changes, self._il_ids, self._new_pd)
        cfg = _load_cfg()
        cfg["max_per_day"]         = self._max
        cfg["auto_run_on_startup"] = self._auto_cb.isChecked()
        _save_cfg(cfg)
        tooltip(f"Done — today capped at {self._max} cards.", period=3000)
        self.accept()

# ── Auto-run ────────────────────────────────────────────────────────────────────

def _auto_run(_col=None):
    if not mw or not mw.col:
        return
    cfg = _load_cfg()
    if not cfg.get("auto_run_on_startup", True):
        return
    try:
        max_pd = cfg["max_per_day"]
        rev_ch, dl_ch, il_ids, new_pd, before, after = _compute_all(max_pd)
        cur_new = _get_current_new_per_day()
        if rev_ch or dl_ch or il_ids or cur_new != new_pd:
            _apply(rev_ch, dl_ch, il_ids, new_pd)
            tooltip(
                f"Daily Cap: {before} → {after} cards today (max {max_pd}).",
                period=4000
            )
        # No tooltip when already under cap — silent success
    except Exception as e:
        tooltip(f"Daily Cap error: {e}", period=6000)

# ── Menu ────────────────────────────────────────────────────────────────────────

def _setup():
    action = QAction("Cap Daily Cards…", mw)
    action.triggered.connect(lambda: CapDialog().exec())
    mw.form.menuTools.addAction(action)
    gui_hooks.collection_did_load.append(_auto_run)

gui_hooks.main_window_did_init.append(_setup)
