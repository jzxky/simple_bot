# simple_bot

A browser automation bot for MafiaMatrix.

## Requirements

- Python 3.10+
- Google Chrome installed

## Setup

**1. Clone the repository**
```
git clone https://github.com/jzxky/simple_bot.git
cd simple_bot
```

**2. Install dependencies**
```
pip install -r requirements.txt
```

**3. Install the Patchright browser driver**
```
python -m patchright install chrome
```

**4. Run the bot**
```
python main.py
```

This opens the control panel at `http://localhost:8080` in your browser. Enter your MafiaMatrix email and password there, configure the settings, then click **Start Bot**.

To run without opening the control panel automatically:
```
python main.py --noui
```

## macOS

Google Chrome must be installed (the bot drives real Chrome, not Chromium). macOS ships an old, managed Python, so install a current one and use a virtual environment.

**1. Install Python 3.10+** (via [Homebrew](https://brew.sh))
```
brew install python@3.12
python3 --version   # should be >= 3.10
```

**2. Clone and enter the repo**
```
git clone https://github.com/jzxky/simple_bot.git
cd simple_bot
```

**3. Create and activate a virtual environment** (run the `activate` line in each new terminal)
```
python3 -m venv .venv
source .venv/bin/activate
```

**4. Install dependencies and the Chrome driver**
```
pip install -r requirements.txt
python main.py --install
```

**5. Run the bot**
```
python main.py
```
This opens the control panel at `http://localhost:8080`. Enter your MafiaMatrix email and password, configure settings, then click **Start Bot**.

macOS notes:
- The bot runs a **headed** Chrome window, so keep the Mac awake with a real display — it won't work headless/SSH-only or with the screen locked for long periods.
- On first run, macOS may ask for permission for automation to control Chrome — allow it.
- Port 8080 must be free; to use another port: `UI_PORT=8090 python main.py`.

## Remote control (no port forwarding)

You can control the bot from anywhere through Player Hub instead of forwarding port 8080:

1. In **Settings**, fill in the Sync server URL (must be `https://`, or a local-network address) and API key, then turn on **Remote control**.
2. The bot connects out to the hub and waits as *Pending* until a hub admin approves it and assigns it to users.
3. Assigned users open the bot from the hub's **Remote** page and get this same control panel.

Optionally set a **Remote password** (Settings, or `UI_REMOTE_PASSWORD` in `.env`): hub users then have to enter it every time they open the bot. Remote control can only be turned on or off on the bot's own computer. Your game email, password, PIN and API key are never sent to the hub, and remote users can't change them, the Sync connection or shut the bot down.

## Notes

- Credentials are stored locally in a `.env` file and never committed.
- Bot activity logs are saved to the `logs/` folder, named by start time.
- The bot runs a headed Chrome window — your machine needs a display.
