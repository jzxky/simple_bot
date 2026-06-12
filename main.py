"""
Entry point. Starts the Flask UI then opens the control panel in the default browser.
"""

import sys
import os
import threading
import webbrowser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_env_var

PORT = int(get_env_var("UI_PORT", "8080"))


def _open_browser():
    import time
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    no_ui = "--noui" in sys.argv
    if not no_ui:
        threading.Thread(target=_open_browser, daemon=True).start()
    from ui.app import run
    run()
