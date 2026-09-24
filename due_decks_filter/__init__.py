"""
Due Decks Filter — hides deck rows where all due counts are zero.
Toggle via a floating button on the deck browser or Tools → Due Decks Only.
"""

from aqt import mw, gui_hooks
from aqt.qt import QAction
from aqt.deckbrowser import DeckBrowser
from aqt.webview import WebContent

_filter_active = True
_menu_action = None

_JS_HIDE = """
(function() {
    document.querySelectorAll('tr.deck-row').forEach(function(row) {
        var counts = row.querySelectorAll('span.count');
        var allZero = counts.length > 0 && Array.from(counts).every(function(s) {
            return s.classList.contains('zero-count');
        });
        row.style.display = allZero ? 'none' : '';
    });
})();
"""

_JS_SHOW = """
document.querySelectorAll('tr.deck-row').forEach(function(row) {
    row.style.display = '';
});
"""

_JS_INJECT_BTN = """
(function(active) {
    // Remove existing button if present
    var old = document.getElementById('due-filter-btn');
    if (old) old.remove();

    var btn = document.createElement('button');
    btn.id = 'due-filter-btn';
    btn.textContent = active ? '✓ Due Only' : 'Due Only';
    btn.style.cssText = [
        'position: fixed',
        'top: 6px',
        'right: 58px',
        'z-index: 9999',
        'padding: 6px 14px',
        'border-radius: 20px',
        'border: none',
        'font-size: 12px',
        'font-weight: 700',
        'cursor: pointer',
        'transition: background 0.2s, color 0.2s',
        active
            ? 'background:#7c3aed; color:#fff;'
            : 'background:#2d2d4e; color:#a0a0c0;'
    ].join(';');

    btn.onmouseenter = function() {
        btn.style.background = active ? '#9f6ff5' : '#3d3d6e';
    };
    btn.onmouseleave = function() {
        btn.style.background = active ? '#7c3aed' : '#2d2d4e';
    };
    btn.onclick = function() {
        pycmd('due_filter_toggle');
    };

    var bar = document.body;
    bar.style.position = 'relative';
    bar.appendChild(btn);
})(ACTIVE_STATE);
"""


def _inject_button():
    state = 'true' if _filter_active else 'false'
    mw.toolbar.web.eval(_JS_INJECT_BTN.replace('ACTIVE_STATE', state))


def _apply():
    mw.deckBrowser.web.eval(_JS_HIDE)


def _remove():
    mw.deckBrowser.web.eval(_JS_SHOW)


def _set_filter(active: bool):
    global _filter_active
    _filter_active = active
    if _menu_action:
        _menu_action.setChecked(active)
    if active:
        _apply()
    else:
        _remove()
    _inject_button()


def _on_render(deck_browser: DeckBrowser):
    from aqt.qt import QTimer
    def _do():
        if _filter_active:
            _apply()
        _inject_button()
    QTimer.singleShot(150, _do)


def _handle_pycmd(handled, message, context):
    if message == 'due_filter_toggle':
        _set_filter(not _filter_active)
        return (True, None)
    return handled


def _setup():
    global _menu_action

    action = QAction("Due Decks Only", mw)
    action.setCheckable(True)
    action.setChecked(True)
    action.toggled.connect(lambda checked: _set_filter(checked))
    mw.form.menuTools.addAction(action)
    _menu_action = action

    gui_hooks.deck_browser_did_render.append(_on_render)
    from aqt.qt import QTimer as _QTimer
    gui_hooks.top_toolbar_did_init_links.append(
        lambda links, tb: _QTimer.singleShot(200, _inject_button)
    )
    gui_hooks.webview_did_receive_js_message.append(_handle_pycmd)


gui_hooks.main_window_did_init.append(_setup)
