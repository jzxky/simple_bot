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

## Notes

- Credentials are stored locally in a `.env` file and never committed.
- Bot activity logs are saved to the `logs/` folder, named by start time.
- The bot runs a headed Chrome window — your machine needs a display.
