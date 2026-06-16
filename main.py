"""
Entry point. Starts the Flask UI then opens the control panel in the default browser.

Flags:
  --noui      Skip opening the browser tab
  --install   Install the Chrome browser (one-time setup) then exit
"""

import sys
import os
import threading
import webbrowser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_env_var

PORT = int(get_env_var("UI_PORT", "8080"))


def _install_chrome():
    """Install the patchright-managed Chrome. Called via --install flag."""
    print("Installing Chrome browser via patchright...")
    try:
        from patchright._impl._driver import compute_driver_executable, get_driver_env
        import subprocess
        executable = compute_driver_executable()
        env = {**os.environ, **get_driver_env()}
        result = subprocess.run(
            [str(executable), "install", "chrome"],
            env=env,
        )
        if result.returncode == 0:
            print("\nChrome installed successfully. You can now run the bot.")
        else:
            print("\nInstallation failed. Check output above.")
            sys.exit(1)
    except Exception as e:
        print(f"\nInstallation error: {e}")
        sys.exit(1)


def _open_browser():
    import time
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    if "--install" in sys.argv:
        _install_chrome()
        sys.exit(0)

    no_ui = "--noui" in sys.argv
    if not no_ui:
        threading.Thread(target=_open_browser, daemon=True).start()
    from ui.app import run
    run()
