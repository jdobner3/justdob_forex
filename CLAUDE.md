# FOREX DASHBOARD — PROJECT BRIEF FOR CLAUDE CODE
# Read this entire file before writing any code.
# Last updated: May 2026

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJECT OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A personal forex trading assistant dashboard that:
- Scans 8 major currency pairs every hour
- Detects real price action setups (structure levels + candle patterns)
- Scores and ranks setups by quality (0-100)
- Shows live session clock (Tokyo / London / New York)
- Stores all signals and scan history in SQLite
- Displays everything in a dark themed web dashboard
- Will be deployed to Render.com

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TECH STACK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Python 3.12.10
- Flask 3.1.3
- SQLite (built into Python, no setup needed)
- Twelve Data API for forex data (free tier)
- python-dotenv for API key management
- numpy, pandas for data analysis
- HTML / CSS / JS frontend (no React, no npm, no node)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

forex/
├── app.py                    ← Main Flask server (EXISTS)
├── CLAUDE.md                 ← This file (EXISTS)
├── twelvedata_apikey.env     ← API key file (EXISTS — do not touch)
├── forex_analysis.py         ← Single pair analysis script (EXISTS)
├── forex_scanner.py          ← Multi pair scanner script (EXISTS)
├── requirements.txt          ← NEEDS TO BE CREATED
├── Procfile                  ← NEEDS TO BE CREATED (for Render.com)
├── .gitignore                ← NEEDS TO BE CREATED
├── README.md                 ← NEEDS TO BE CREATED
├── forex.db                  ← Auto created on first run (SQLite)
└── templates/
    └── dashboard.html        ← Main dashboard UI (EXISTS)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT EXISTS AND WORKS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

app.py contains:
- Flask routes:
    GET  /                      → serves dashboard
    POST /api/scan/run          → triggers manual scan
    GET  /api/scan/status       → returns scan state + results
    GET  /api/signals/history   → returns last 50 signals
    GET  /api/scans/history     → returns last 20 scan logs
    GET  /api/session           → returns active session info
- SQLite database init, save, and read functions
- Full scanner engine with these functions:
    find_swing_highs()
    find_swing_lows()
    cluster_levels()
    detect_patterns()
    score_setup()
    grade()
    strength_label()
- Background thread that auto-scans at top of every hour
- Manual scan trigger via POST /api/scan/run
- Shared scan_state dict for status tracking between threads

dashboard.html contains:
- Dark themed UI (CSS variables, no external CSS framework)
- Live UTC clock (updates every second)
- Session bar with Tokyo / London / New York pills
- Run Scan Now button with spinner during scan
- Setup cards showing: pair, direction, pattern, entry,
  stop, target, grade, score bar, R/R ratio
- Signal history table (last 50)
- Scan log (last 20 scans)
- Stats grid: total scans, signals found, buys, sells
- Trade checklist sidebar (5 rules)
- Session times sidebar (CT timezone)
- JavaScript polling every 3 seconds for scan status
- Auto refresh of history every 60 seconds

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRADING LOGIC — DO NOT CHANGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PAIRS:
  EUR/USD, GBP/USD, USD/JPY, USD/CHF,
  AUD/USD, USD/CAD, NZD/USD, EUR/GBP

SCANNER SETTINGS:
  INTERVAL        = 1h
  BARS            = 100
  ZONE_TOLERANCE  = 0.00030   (~3 pips — zone clustering)
  LEVEL_PROXIMITY = 0.00100   (~10 pips — near a level)
  MIN_TOUCHES     = 2         (minimum zone strength)
  MIN_RR          = 1.5       (minimum risk/reward ratio)
  API_DELAY       = 8         (seconds between API calls)

CANDLE PATTERNS:
  Hammer / Bullish Pin Bar        → BUY
  Shooting Star / Bearish Pin Bar → SELL
  Bullish Engulfing               → BUY
  Bearish Engulfing               → SELL
  Doji                            → NEUTRAL
  Strong Momentum Candle          → BUY or SELL
  Inside Bar                      → NEUTRAL

SETUP SCORING (0-100):
  Pattern strength:
    Strong   = 30 pts
    Moderate = 15 pts
  Zone strength:
    4+ touches = 30 pts
    3 touches  = 20 pts
    2 touches  = 10 pts
  Risk/Reward:
    3.0+:1 = 25 pts
    2.0+:1 = 18 pts
    1.5+:1 = 10 pts
  RSI confirmation:
    RSI confirms direction = 15 pts

GRADES:
  A+ = 80+   Prime Setup  🔥
  A  = 65+   Strong Setup ✅
  B  = 50+   Watch This   👀
  C  = 35+   Weak Setup   ⚠️
  D  = <35   Skip         ❌

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRIORITIES — WORK THROUGH IN ORDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PRIORITY 1 — Verify local setup works:
  - Run app.py and confirm no errors
  - Confirm dashboard loads at http://localhost:5000
  - Confirm Run Scan Now button triggers a scan
  - Confirm signals are saved to forex.db
  - Fix any bugs found

PRIORITY 2 — Create missing deployment files:

  requirements.txt:
    flask
    python-dotenv
    twelvedata
    numpy
    pandas
    requests
    gunicorn

  Procfile:
    web: gunicorn --workers 1 app:app

  .gitignore:
    *.env
    forex.db
    __pycache__/
    *.pyc
    .DS_Store
    *.db

  README.md should include:
    - What the app does
    - How to run locally (python app.py)
    - Required environment variables
    - How to deploy to Render.com
    - Note: never commit the .env file

PRIORITY 3 — GitHub setup:
  - Initialize git repo in the project folder
  - Create initial commit with all project files
  - Push to a new GitHub repository
  - Confirm the .env file is NOT committed (it is in .gitignore)

PRIORITY 4 — Deploy to Render.com:
  - Connect the GitHub repo to Render.com
  - Set this environment variable in Render dashboard:
      Key:   TWELVE_DATA_API_KEY
      Value: (the key value from twelvedata_apikey.env)
  - Deploy and confirm the app runs live
  - Share the live URL with the user

PRIORITY 5 — Improvements (do after deployment):
  - Trade journal tab: log actual trades with entry price,
    exit price, result in pips, win/loss, and notes field
  - Win/loss stats: total trades, win rate, avg pips won/lost,
    best pair, worst pair
  - Multi-timeframe scanner: add 4h timeframe alongside 1h
  - Economic calendar: show major news events that could
    affect open positions (use a free API)
  - Browser price alerts: notify user when a pair reaches
    a key structure level

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. API KEY SECURITY
   The key lives in twelvedata_apikey.env locally.
   On Render it is an environment variable.
   app.py already handles both via os.getenv().
   Never hardcode the key anywhere. Never commit the .env file.

2. RATE LIMITS
   Twelve Data free tier = 8 calls/minute, 800/day.
   API_DELAY = 8 seconds between calls must stay in place
   or the scanner will get rate limited and fail silently.

3. SQLITE ON RENDER
   Render has an ephemeral filesystem — forex.db will reset
   on redeploy. This is acceptable for now. Future upgrade
   is PostgreSQL but do not implement that yet.

4. GUNICORN WORKERS
   The background scanner thread runs inside Flask.
   gunicorn must use --workers 1 to avoid multiple scanner
   threads running simultaneously and hitting rate limits.
   The Procfile already specifies this.

5. FLASK TEMPLATES
   dashboard.html must stay inside the templates/ folder.
   Flask finds it via render_template('dashboard.html').
   Do not move it.

6. DO NOT CHANGE TRADING LOGIC
   The candle patterns, scoring system, structure detection,
   and grade thresholds are intentional and calibrated.
   Ask before changing any of these values.

7. USER CONTEXT
   The user is not a developer. Keep all instructions and
   terminal commands simple and step by step. Explain what
   each command does in plain English.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
START HERE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Start with Priority 1. Run the app locally and confirm
everything works before creating any new files or touching
any existing code. Work through priorities 1 through 4 in
order. Always ask before modifying trading logic or scoring.
