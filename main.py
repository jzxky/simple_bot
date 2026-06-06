"""
Entry point. Starts the Flask UI (which also controls the bot).
Open http://localhost:5000 in your browser.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ui.app import run

if __name__ == "__main__":
    run()
