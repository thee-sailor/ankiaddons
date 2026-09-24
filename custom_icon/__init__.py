import ctypes
from aqt import mw, gui_hooks
from aqt.qt import QIcon, QApplication

# Set this to the .ico file you want Anki to use for its window/taskbar icon.
ICON_PATH = r"C:\path\to\your\icon.ico"

def _set_icon():
    icon = QIcon(ICON_PATH)
    if icon.isNull():
        return

    # Title bar
    mw.setWindowIcon(icon)

    # Taskbar (app-level)
    QApplication.instance().setWindowIcon(icon)

    # Windows: set a unique AppUserModelID so the taskbar uses our icon
    # instead of the pinned/cached Anki default
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "AnkiCustomIcon.1"
        )
    except Exception:
        pass

gui_hooks.main_window_did_init.append(_set_icon)
