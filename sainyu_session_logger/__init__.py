"""
Sainyu Session Logger — companion to the "Focus Music & Pomodoro Player" add-on.

It logs your whole pomodoro cycle — every study phase AND every break — as notes
inside your collection, so they travel over normal AnkiWeb sync to AnkiDroid,
where Sainyu mirrors each one as a time entry. No network, no Tailscale.

How it stays accurate: a 1-second tracker watches the pomodoro's phase index and
run/pause state, accumulating real *active* seconds per phase (pauses don't
count). When a phase ends (it advanced, you skipped/reset it, or you closed
Anki), the phase is written as one session:

    { uid, activity, kind, start, end, cards, source }

stored as JSON in a single "Data" field of the "SainyuSession" note type, in the
"Sainyu Session Log" deck, tagged `sainyu-session`, with its card suspended so it
never appears as due. Study phases are auto-labelled by the deck you actually
reviewed (leaf name); breaks are labelled by the phase name.
"""

import json
import re
import time
import uuid
from collections import Counter, deque

from aqt import mw, gui_hooks
from aqt.qt import QTimer
from aqt.utils import tooltip

MODEL_NAME = "SainyuSession"
DECK_NAME = "Sainyu Session Log"
TAG = "sainyu-session"
# A single always-overwritten note carrying the review forecast AnkiDroid can't
# compute on its own (its ContentProvider only exposes due-today counts).
FORECAST_TAG = "sainyu-forecast"
# Cap the "due today" card list written into that note, to bound its size.
FORECAST_CARD_CAP = 150
# Ignore a phase that barely ran (skipping through the cycle), in seconds.
MIN_SECONDS = 20
# Cap a single tick's delta so a slept/backgrounded app can't inflate a phase.
MAX_TICK_DELTA = 2.0

# Rolling record of (epoch_seconds, deck_name) for answered cards, so a phase can
# be labelled by the deck studied within its own time window.
_reviews = deque(maxlen=8000)

# The phase currently being tracked, or None between/outside phases.
#   {index, start, active, kind, name}
_active = None
_last_tick = None
_timer = None


def _on_answer(reviewer, card, ease):
    try:
        did = getattr(card, "odid", 0) or card.did  # original deck if filtered
        _reviews.append((time.time(), mw.col.decks.name(did)))
    except Exception:
        pass


def _ensure_model(col):
    m = col.models.by_name(MODEL_NAME)
    if m:
        return m
    m = col.models.new(MODEL_NAME)
    col.models.add_field(m, col.models.new_field("Data"))
    t = col.models.new_template("Card 1")
    t["qfmt"] = "{{Data}}"
    t["afmt"] = "{{Data}}"
    col.models.add_template(m, t)
    col.models.add(m)
    return col.models.by_name(MODEL_NAME)


def _log_note(data, tag=TAG):
    col = mw.col
    if not col:
        return
    model = _ensure_model(col)
    did = col.decks.id(DECK_NAME)  # creates the deck if missing
    note = col.new_note(model)
    note["Data"] = json.dumps(data, separators=(",", ":"))
    note.add_tag(tag)
    col.add_note(note, did)
    try:
        col.sched.suspend_cards([c.id for c in note.cards()])
    except Exception:
        pass  # not fatal — the note still syncs


def _join_names(items, cap=6):
    """'A' · 'A and B' · 'A, B and C'; caps very long lists with '+N more'."""
    items = list(items)
    extra = len(items) - cap if len(items) > cap else 0
    if extra:
        items = items[:cap]
    if not items:
        return ""
    if len(items) == 1:
        base = items[0]
    elif len(items) == 2:
        base = "%s and %s" % (items[0], items[1])
    else:
        base = ", ".join(items[:-1]) + " and " + items[-1]
    return base + (" +%d more" % extra if extra else "")


def _finalize(a, end):
    """Write the just-ended phase `a` as a session note. A study phase lists
    EVERY distinct deck/topic studied in it as one entry (e.g. 'Pathology mcqs,
    RBC metabolism and Virology'), since several short cards fit in one session."""
    dur = a["active"]
    if dur < MIN_SECONDS:
        return
    end_ms = int(end * 1000)
    start_ms = int((end - dur) * 1000)
    if a.get("kind") == "work":
        window = [d for (t, d) in list(_reviews) if a["start"] - 2 <= t <= end + 2]
        cards = len(window)
        decks = []
        for d in window:
            leaf = d.split("::")[-1]
            if leaf not in decks:
                decks.append(leaf)          # distinct, in order first studied
        label = _join_names(decks) if decks else (a.get("name") or "Study")
    else:
        cards = 0
        decks = []
        label = a.get("name") or "Break"
    data = {
        "uid": uuid.uuid4().hex,
        "activity": label,
        "decks": decks,
        "kind": "work" if a.get("kind") == "work" else "break",
        "start": start_ms,
        "end": end_ms,
        "cards": cards,
        "source": "desktop-pomodoro",
    }
    try:
        _log_note(data)
        mins = max(1, round(dur / 60))
        extra = f" · {cards} cards" if data["kind"] == "work" else ""
        tooltip(f"Sainyu: {label} · {mins}m{extra}", period=2200)
    except Exception:
        pass


def _tick():
    """Called ~1×/sec: track the active phase and finalise on transitions."""
    global _active, _last_tick
    fm = getattr(mw, "focus_music", None)
    now = time.time()
    dt = min(MAX_TICK_DELTA, now - _last_tick) if _last_tick else 0.0
    _last_tick = now
    if not fm:
        return
    try:
        idx = int(fm.phase_index)
        running = bool(fm.timer_running)
        phase = fm.phases[idx]
    except Exception:
        return

    if _active is None:
        if running:
            _active = {"index": idx, "start": now, "active": 0.0, "kind": phase.get("kind"), "name": phase.get("name")}
        return

    if idx != _active["index"]:
        _finalize(_active, now)
        _active = {"index": idx, "start": now, "active": 0.0, "kind": phase.get("kind"), "name": phase.get("name")} if running else None
    elif running:
        _active["active"] += dt


def _flush():
    """Log the in-progress phase when the profile/collection is closing."""
    global _active
    if _active is not None:
        _finalize(_active, time.time())
        _active = None


_TAG_RE = re.compile(r"<[^>]+>")


def _plain(s):
    """First-field text for the due-card preview: drop HTML and collapse space."""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", s or "")).strip()


def _esc(name):
    """Escape a deck name for an Anki search term wrapped in double quotes."""
    return name.replace("\\", "\\\\").replace('"', '\\"')


def _write_forecast():
    """Recompute the per-deck review forecast (today / within a week / within a
    month) plus the list of cards due today, and store it as one note tagged
    `sainyu-forecast` — overwriting any previous one — so it rides AnkiWeb sync
    to AnkiDroid. Review workload only (new-card daily limits aren't "due"), so
    counts are cumulative and monotonic: today <= week <= month."""
    col = mw.col
    if not col:
        return
    try:
        def count(search):
            return len(col.find_cards(search))

        decks = []
        total = {"today": 0, "week": 0, "month": 0}
        for d in col.decks.all_names_and_ids(skip_empty_default=True, include_filtered=False):
            if d.name == DECK_NAME:
                continue
            # Own cards only (exclude sub-decks) so rows never double-count.
            own = '(deck:"{0}" -deck:"{0}::*")'.format(_esc(d.name))
            today = count("{0} is:due".format(own))
            week = count("{0} (is:due or prop:due<=7)".format(own))
            month = count("{0} (is:due or prop:due<=30)".format(own))
            total["today"] += today
            total["week"] += week
            total["month"] += month
            if month > 0:
                decks.append({"name": d.name, "today": today, "week": week, "month": month})
        decks.sort(key=lambda x: -x["month"])

        due_today = []
        for cid in col.find_cards('is:due -deck:"{0}"'.format(_esc(DECK_NAME)))[:FORECAST_CARD_CAP]:
            try:
                card = col.get_card(cid)
                note = card.note()
                due_today.append({"q": _plain(note.fields[0])[:120], "deck": col.decks.name(card.did)})
            except Exception:
                continue

        data = {
            "generated": int(time.time() * 1000),
            "decks": decks,
            "total": total,
            "dueToday": due_today,
            "source": "desktop-forecast",
        }

        old = col.find_notes("tag:{0}".format(FORECAST_TAG))
        if old:
            try:
                col.remove_notes(old)
            except Exception:
                pass
        _log_note(data, tag=FORECAST_TAG)
    except Exception:
        pass  # a forecast is best-effort; never disturb Anki


def _install():
    global _timer, _last_tick
    if _timer is not None:
        return
    _last_tick = time.time()
    _timer = QTimer(mw)
    _timer.setInterval(1000)
    _timer.timeout.connect(_tick)
    _timer.start()


def _on_profile_open():
    _install()
    _write_forecast()


def _on_profile_close():
    _flush()
    _write_forecast()  # capture this session's reviews so the synced forecast is current


gui_hooks.reviewer_did_answer_card.append(_on_answer)
gui_hooks.profile_did_open.append(_on_profile_open)
gui_hooks.profile_will_close.append(_on_profile_close)
