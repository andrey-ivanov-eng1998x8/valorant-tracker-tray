# valorant-tracker-tray

I wanted a simple way to see my session rank rating (RR) change and recent match outcomes without having to open full-blown tracking websites or overlays that hog memory. This sits in your Windows system tray, polls the local Riot client API, and updates an icon and menu with your current session delta (e.g., +22, -15) and recent matches.

It works entirely locally by reading the Riot Client lockfile. No official API keys needed.

## Installation

Clone this repository and install the dependencies. You need Python 3.10+ on Windows.

```cmd
pip install -r requirements.txt
```

## How to run

Make sure Valorant is running, then start the tracker:

```cmd
python tracker.py
```

By default, it starts in the system tray. If you just want a quick terminal print of your current status without running the tray app, use the CLI flag:

```cmd
python tracker.py --cli
```

## How it works

1. It looks up the Riot Client lockfile in your `%LOCALAPPDATA%` directory to get the local port and generated password.
2. It connects to the local Riot WebSockets/HTTPS server (ignoring the self-signed certificate warning).
3. It fetches your current account details and parses your recent competitive matches to calculate the net RR change since the script was started.

<!-- refreshed: 2026-09-25 -->
