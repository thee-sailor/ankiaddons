import subprocess
from aqt import mw, gui_hooks
from aqt.qt import QAction

# Point these at your local Electron app to launch it from Anki's Tools menu.
RONNBROWSER_DIR = r"C:\path\to\RonnBrowser"
ELECTRON = r"C:\path\to\RonnBrowser\node_modules\.bin\electron.cmd"

def launch_ronnbrowser():
    subprocess.Popen(
        [ELECTRON, "."],
        cwd=RONNBROWSER_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

def add_menu_item():
    action = QAction("Open RonnBrowser", mw)
    action.triggered.connect(launch_ronnbrowser)
    mw.form.menuTools.addAction(action)

gui_hooks.main_window_did_init.append(add_menu_item)