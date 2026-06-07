"""
Entry point. Starts the Flask UI then opens the control panel in the default browser.
"""

import sys
import os
import threading
import webbrowser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PORT = 8080


def _open_browser():
    import time
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    from ui.app import run
    run()
