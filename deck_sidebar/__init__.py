"""
Deck Browser Sidebar
────────────────────
• Click any http link in a card  → sidebar opens and loads the URL
• Click X on the sidebar         → sidebar closes
• Ctrl+Shift+B / toolbar / menu  → manual toggle
• Available on Deck screen and during card review
"""

from __future__ import annotations
from importlib import import_module

import aqt.utils as _aqt_utils
import aqt.webview as _aqt_webview
from aqt import mw, gui_hooks
from aqt.qt import (
    QDockWidget, Qt, QAction, QKeySequence, QShortcut, QUrl
)
from aqt.utils import tooltip

# ── Import BrowserWidget from existing browser add-on ────────────────────────
try:
    _mod = import_module("918010938.browser")
    BrowserWidget = _mod.BrowserWidget
    _OK = True
except Exception as exc:
    _OK = False
    print(f"[Deck Sidebar] Cannot import browser add-on: {exc}")

# ── State ─────────────────────────────────────────────────────────────────────
_dock:    "QDockWidget | None" = None
_browser: "BrowserWidget | None" = None

_ACTIVE_STATES = {"deckBrowser", "review"}

# True  = user wants sidebar open (show it when entering an active state)
# False = user closed it with X (don't auto-reopen on state changes)
_user_wants_open: bool = False

# Flag to distinguish our programmatic hides from the user clicking X
_hiding_programmatically: bool = False

DOCK_STYLE = """
QDockWidget {
    background: #0f0f17;
    color: #e2e8f0;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}
QDockWidget::title {
    background: #1a1a2e;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    padding: 6px 10px;
    text-align: left;
    font-weight: 600;
    color: #a78bfa;
}
QDockWidget::close-button, QDockWidget::float-button {
    background: transparent;
    border: none;
    padding: 2px;
}
QDockWidget::close-button:hover, QDockWidget::float-button:hover {
    background: rgba(255,255,255,0.10);
    border-radius: 4px;
}
"""

# ── Dock creation ─────────────────────────────────────────────────────────────

def _create_dock() -> None:
    global _dock, _browser
    if _dock is not None or not _OK:
        return

    _browser = BrowserWidget(parent=mw)

    _dock = QDockWidget("🌐  Browser", mw)
    _dock.setObjectName("DeckBrowserSidebar")
    _dock.setStyleSheet(DOCK_STYLE)
    _dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable   |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable
    )
    _dock.setAllowedAreas(
        Qt.DockWidgetArea.LeftDockWidgetArea  |
        Qt.DockWidgetArea.RightDockWidgetArea
    )
    _dock.setWidget(_browser)
    _dock.setMinimumWidth(340)

    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, _dock)
    _dock.visibilityChanged.connect(_on_visibility_changed)
    _dock.hide()


def _on_visibility_changed(visible: bool) -> None:
    """
    Only update _user_wants_open when the change came from the USER
    (clicking X), not from our programmatic hide/show calls.
    """
    global _user_wants_open
    if not visible and not _hiding_programmatically:
        # User clicked X — remember they closed it
        _user_wants_open = False

# ── Show / hide ───────────────────────────────────────────────────────────────

def _show(url: str | None = None) -> None:
    global _user_wants_open
    if _dock is None:
        return
    _user_wants_open = True
    _dock.show()
    _dock.raise_()
    if url and _browser:
        _browser._navigate_active(url)


def _hide_programmatic() -> None:
    """Hide without affecting _user_wants_open (state-change hides)."""
    global _hiding_programmatically
    if _dock is None:
        return
    _hiding_programmatically = True
    _dock.hide()
    _hiding_programmatically = False


def _hide_user() -> None:
    """Hide and mark that the user closed it (toggle)."""
    global _user_wants_open
    _user_wants_open = False
    _hide_programmatic()


def _toggle() -> None:
    if _dock is None:
        tooltip("Browser add-on (918010938) not found.", period=3000)
        return
    if _dock.isVisible():
        _hide_user()
    else:
        _show()

# ── Intercept http link clicks → open in sidebar ──────────────────────────────

_original_open_link = _aqt_utils.openLink


def _patched_open_link(url) -> None:
    url_str = url.toString() if isinstance(url, QUrl) else str(url)

    if url_str.startswith(("http://", "https://")) and _OK:
        _show(url_str)
    else:
        _original_open_link(url)


# Patch in both modules — aqt.webview imports openLink directly with
# "from aqt.utils import openLink", so patching aqt.utils alone has no effect.
_aqt_utils.openLink = _patched_open_link
_aqt_webview.openLink = _patched_open_link

# ── State changes: deck screen ↔ reviewer ─────────────────────────────────────

def _on_state_changed(new_state: str, _old: str) -> None:
    if _dock is None:
        return
    if new_state in _ACTIVE_STATES:
        # Re-show only if the user hadn't explicitly closed it
        if _user_wants_open:
            _dock.show()
            _dock.raise_()
    else:
        # Leaving an active state — hide without changing _user_wants_open
        _hide_programmatic()

# ── Toolbar link ──────────────────────────────────────────────────────────────

def _on_toolbar_init(links: list, toolbar) -> None:
    link = toolbar.create_link(
        cmd="deck-sidebar-toggle",
        label="Browser",
        func=lambda: _toggle(),
        tip="Toggle Browser Sidebar (Ctrl+Shift+B)",
        id="deck-sidebar-btn",
    )
    links.append(link)

# ── Setup ─────────────────────────────────────────────────────────────────────

def _setup() -> None:
    _create_dock()

    action = QAction("Browser Sidebar", mw)
    action.setShortcut(QKeySequence("Ctrl+Shift+B"))
    action.setCheckable(True)
    action.setChecked(False)
    action.triggered.connect(_toggle)
    mw.form.menuTools.addAction(action)
    if _dock:
        _dock.visibilityChanged.connect(action.setChecked)

    sc = QShortcut(QKeySequence("Ctrl+Shift+B"), mw)
    sc.activated.connect(_toggle)

    gui_hooks.state_did_change.append(_on_state_changed)


gui_hooks.main_window_did_init.append(_setup)
gui_hooks.top_toolbar_did_init_links.append(_on_toolbar_init)
