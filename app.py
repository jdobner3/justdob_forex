from flask import Flask, render_template, jsonify, redirect, url_for, session, request
from dotenv import load_dotenv
import os
import sqlite3
import json
import time
import threading
from datetime import datetime, timezone
from twelvedata import TDClient
import numpy as np
import msal

# ── Load local env file if present ────────────────────────────────────────────
load_dotenv("twelvedata_apikey.env")

app = Flask(__name__)

# ── Config from environment variables ─────────────────────────────────────────
API_KEY       = os.getenv("TWELVE_DATA_API_KEY")
SECRET_KEY    = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
CLIENT_ID     = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID     = os.getenv("AZURE_TENANT_ID")
REDIRECT_URI  = os.getenv("REDIRECT_URI", "http://localhost:5000/auth/callback")

app.secret_key = SECRET_KEY

# ── Microsoft Auth Config ──────────────────────────────────────────────────────
AUTHORITY     = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES        = ["User.Read"]

def get_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )

# ── Auth helpers ───────────────────────────────────────────────────────────────
def login_required(f):
    """Decorator — redirect to login if not authenticated."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ── Settings ───────────────────────────────────────────────────────────────────
PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD", "EUR/GBP",
]
INTERVAL         = "1h"
BARS             = 100
ZONE_TOLERANCE   = 0.00030
LEVEL_PROXIMITY  = 0.00100
MIN_TOUCHES      = 2
MIN_RR           = 1.5
API_DELAY        = 8
DB_PATH          = "forex.db"

# ── Database ───────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT,
            pair        TEXT,
            direction   TEXT,
            pattern     TEXT,
            strength    TEXT,
            at_level    REAL,
            touches     INTEGER,
            current     REAL,
            target      REAL,
            stop        REAL,
            rr          REAL,
            rsi         REAL,
            score       INTEGER,
            grade       TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT,
            pairs_scanned INTEGER,
            setups_found  INTEGER,
            results       TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_scan(results):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    ts   = datetime.now(timezone.utc).isoformat()
    c.execute("""
        INSERT INTO scans (timestamp, pairs_scanned, setups_found, results)
        VALUES (?, ?, ?, ?)
    """, (ts, len(PAIRS), len(results), json.dumps(results)))
    for r in results:
        c.execute("""
            INSERT INTO signals
            (timestamp, pair, direction, pattern, strength, at_level,
             touches, current, target, stop, rr, rsi, score, grade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts, r["pair"], r["direction"], r["pattern"], r["strength"],
            r["at_level"], r["touches"], r["current"], r.get("target"),
            r["stop"], r["rr"], r["rsi"], r["score"], r["grade"]
        ))
    conn.commit()
    conn.close()

def get_recent_signals(limit=50):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT timestamp, pair, direction, pattern, strength,
               at_level, touches, current, target, stop, rr, rsi, score, grade
        FROM signals ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    keys = ["timestamp","pair","direction","pattern","strength",
            "at_level","touches","current","target","stop","rr","rsi","score","grade"]
    return [dict(zip(keys, row)) for row in rows]

def get_scan_history(limit=20):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT timestamp, pairs_scanned, setups_found
        FROM scans ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [{"timestamp": r[0], "pairs_scanned": r[1], "setups_found": r[2]} for r in rows]

# ── Scanner Engine ─────────────────────────────────────────────────────────────
def find_swing_highs(high_series, lookback=3):
    swings = []
    for i in range(lookback, len(high_series) - lookback):
        window = high_series.iloc[i - lookback: i + lookback + 1]
        if high_series.iloc[i] == window.max():
            swings.append(high_series.iloc[i])
    return swings

def find_swing_lows(low_series, lookback=3):
    swings = []
    for i in range(lookback, len(low_series) - lookback):
        window = low_series.iloc[i - lookback: i + lookback + 1]
        if low_series.iloc[i] == window.min():
            swings.append(low_series.iloc[i])
    return swings

def cluster_levels(prices, tolerance):
    if not prices:
        return []
    prices = sorted(prices)
    zones  = []
    used   = [False] * len(prices)
    for i in range(len(prices)):
        if used[i]:
            continue
        cluster = [prices[i]]
        for j in range(i + 1, len(prices)):
            if abs(prices[j] - prices[i]) <= tolerance:
                cluster.append(prices[j])
                used[j] = True
        used[i] = True
        zones.append((round(np.mean(cluster), 5), len(cluster)))
    return sorted(zones, key=lambda x: x[1], reverse=True)

def detect_patterns(open_, close, high, low, idx=-1):
    patterns = []
    o1 = open_.iloc[idx];   c1 = close.iloc[idx]
    h1 = high.iloc[idx];    l1 = low.iloc[idx]
    o2 = open_.iloc[idx-1]; c2 = close.iloc[idx-1]
    h2 = high.iloc[idx-1];  l2 = low.iloc[idx-1]

    body1       = abs(c1 - o1)
    full_range1 = h1 - l1
    upper_wick1 = h1 - max(c1, o1)
    lower_wick1 = min(c1, o1) - l1
    body2       = abs(c2 - o2)
    bullish1    = c1 > o1
    bearish1    = c1 < o1
    bullish2    = c2 > o2
    bearish2    = c2 < o2

    if full_range1 == 0 or body1 == 0:
        return patterns

    if (lower_wick1 >= body1 * 2.0 and upper_wick1 <= body1 * 0.5
            and lower_wick1 >= full_range1 * 0.55):
        patterns.append(("Hammer / Bull Pin Bar", "BUY",
                          "Strong" if lower_wick1 >= body1 * 3 else "Moderate"))

    if (upper_wick1 >= body1 * 2.0 and lower_wick1 <= body1 * 0.5
            and upper_wick1 >= full_range1 * 0.55):
        patterns.append(("Shooting Star / Bear Pin Bar", "SELL",
                          "Strong" if upper_wick1 >= body1 * 3 else "Moderate"))

    if bullish1 and bearish2 and c1 > o2 and o1 < c2 and body1 > body2 * 1.1:
        patterns.append(("Bullish Engulfing", "BUY",
                          "Strong" if body1 > body2 * 1.5 else "Moderate"))

    if bearish1 and bullish2 and o1 > c2 and c1 < o2 and body1 > body2 * 1.1:
        patterns.append(("Bearish Engulfing", "SELL",
                          "Strong" if body1 > body2 * 1.5 else "Moderate"))

    if body1 <= full_range1 * 0.1 and full_range1 > 0.00010:
        patterns.append(("Doji", "NEUTRAL", "Informational"))

    if body1 >= full_range1 * 0.75 and full_range1 > 0.00020:
        direction = "BUY" if bullish1 else "SELL"
        label     = "Strong Bull Momentum" if bullish1 else "Strong Bear Momentum"
        patterns.append((label, direction, "Strong"))

    if h1 < h2 and l1 > l2:
        patterns.append(("Inside Bar", "NEUTRAL", "Informational"))

    return patterns

def score_setup(pattern_strength, zone_touches, rr, direction, rsi):
    score = 0
    if pattern_strength == "Strong":     score += 30
    elif pattern_strength == "Moderate": score += 15
    if zone_touches >= 4:   score += 30
    elif zone_touches == 3: score += 20
    elif zone_touches == 2: score += 10
    if rr >= 3.0:   score += 25
    elif rr >= 2.0: score += 18
    elif rr >= 1.5: score += 10
    if direction == "BUY"  and 30 <= rsi <= 60: score += 15
    elif direction == "SELL" and 40 <= rsi <= 70: score += 15
    elif direction == "BUY"  and rsi < 30:        score += 10
    elif direction == "SELL" and rsi > 70:         score += 10
    return score

def grade(score):
    if score >= 80:   return "A+"
    elif score >= 65: return "A"
    elif score >= 50: return "B"
    elif score >= 35: return "C"
    else:             return "D"

def strength_label(touches):
    if touches >= 4: return "MAJOR"
    elif touches == 3: return "Strong"
    elif touches == 2: return "Moderate"
    else: return "Minor"

def run_scan():
    td      = TDClient(apikey=API_KEY)
    results = []

    for i, pair in enumerate(PAIRS):
        try:
            ts = td.time_series(
                symbol=pair, interval=INTERVAL,
                outputsize=BARS, type="forex"
            ).as_pandas()

            ts    = ts.sort_index()
            close = ts["close"].astype(float)
            high  = ts["high"].astype(float)
            low   = ts["low"].astype(float)
            open_ = ts["open"].astype(float)
            current = close.iloc[-1]

            res_zones = cluster_levels(find_swing_highs(high), ZONE_TOLERANCE)
            sup_zones = cluster_levels(find_swing_lows(low),   ZONE_TOLERANCE)
            res_above = sorted([(p, s) for p, s in res_zones if p > current], key=lambda x: x[0])
            sup_below = sorted([(p, s) for p, s in sup_zones if p < current], key=lambda x: x[0], reverse=True)
            nearest_res = res_above[0] if res_above else None
            nearest_sup = sup_below[0] if sup_below else None

            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss
            rsi   = (100 - (100 / (1 + rs))).iloc[-1]

            patterns = detect_patterns(open_, close, high, low, idx=-1)

            near_res = next(((p, s) for p, s in res_zones
                             if abs(current - p) <= LEVEL_PROXIMITY and p > current), None)
            near_sup = next(((p, s) for p, s in sup_zones
                             if abs(current - p) <= LEVEL_PROXIMITY and p < current), None)

            best_score  = 0
            best_signal = None

            for (pat_name, direction, strength) in patterns:
                if direction == "NEUTRAL":
                    continue

                if direction == "BUY" and near_sup:
                    zone_price, zone_touches = near_sup
                    if zone_touches < MIN_TOUCHES: continue
                    if nearest_res:
                        to_target = (nearest_res[0] - current) * 10000
                        to_stop   = (current - zone_price) * 10000 + 5
                        rr        = round(to_target / to_stop, 2) if to_stop > 0 else 0
                    else:
                        rr = 0
                    if rr < MIN_RR: continue
                    sc = score_setup(strength, zone_touches, rr, direction, rsi)
                    if sc > best_score:
                        best_score  = sc
                        best_signal = {
                            "pair": pair, "direction": direction,
                            "pattern": pat_name, "strength": strength,
                            "at_level": zone_price, "touches": zone_touches,
                            "target": nearest_res[0] if nearest_res else None,
                            "stop": round(zone_price - 0.00050, 5),
                            "rr": rr, "rsi": round(rsi, 1),
                            "score": sc, "grade": grade(sc),
                            "current": current,
                            "level_strength": strength_label(zone_touches),
                        }

                elif direction == "SELL" and near_res:
                    zone_price, zone_touches = near_res
                    if zone_touches < MIN_TOUCHES: continue
                    if nearest_sup:
                        to_target = (current - nearest_sup[0]) * 10000
                        to_stop   = (zone_price - current) * 10000 + 5
                        rr        = round(to_target / to_stop, 2) if to_stop > 0 else 0
                    else:
                        rr = 0
                    if rr < MIN_RR: continue
                    sc = score_setup(strength, zone_touches, rr, direction, rsi)
                    if sc > best_score:
                        best_score  = sc
                        best_signal = {
                            "pair": pair, "direction": direction,
                            "pattern": pat_name, "strength": strength,
                            "at_level": zone_price, "touches": zone_touches,
                            "target": nearest_sup[0] if nearest_sup else None,
                            "stop": round(zone_price + 0.00050, 5),
                            "rr": rr, "rsi": round(rsi, 1),
                            "score": sc, "grade": grade(sc),
                            "current": current,
                            "level_strength": strength_label(zone_touches),
                        }

            if best_signal:
                results.append(best_signal)

        except Exception as e:
            print(f"Error scanning {pair}: {e}")

        if i < len(PAIRS) - 1:
            time.sleep(API_DELAY)

    results = sorted(results, key=lambda x: x["score"], reverse=True)
    save_scan(results)
    return results

# ── Scan State ─────────────────────────────────────────────────────────────────
scan_state = {
    "status":    "idle",
    "last_scan": None,
    "results":   [],
    "next_scan": None,
}

def background_scanner():
    while True:
        now       = datetime.now(timezone.utc)
        mins_left = 60 - now.minute
        secs_left = mins_left * 60 - now.second
        scan_state["next_scan"] = (
            now.replace(minute=0, second=0, microsecond=0).timestamp() + 3600
        ) * 1000

        print(f"[Scanner] Next scan in {mins_left}m")
        time.sleep(max(secs_left, 60))

        scan_state["status"] = "scanning"
        try:
            results = run_scan()
            scan_state["results"]   = results
            scan_state["last_scan"] = datetime.now(timezone.utc).isoformat()
            scan_state["status"]    = "idle"
            print(f"[Scanner] Done — {len(results)} setup(s) found")
        except Exception as e:
            scan_state["status"] = "error"
            print(f"[Scanner] Error: {e}")

# ── Auth Routes ────────────────────────────────────────────────────────────────
@app.route("/login")
def login():
    msal_app = get_msal_app()
    auth_url = msal_app.get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    return redirect(auth_url)

@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    if not code:
        return "Authentication failed — no code returned.", 400

    msal_app = get_msal_app()
    result   = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    if "error" in result:
        return f"Authentication error: {result.get('error_description')}", 400

    # Store user info in session
    session["user"] = {
        "name":  result.get("id_token_claims", {}).get("name", "Trader"),
        "email": result.get("id_token_claims", {}).get("preferred_username", ""),
    }

    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    # Redirect to Microsoft logout then back to login
    logout_url = (
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={url_for('login', _external=True)}"
    )
    return redirect(logout_url)

# ── Main Routes ────────────────────────────────────────────────────────────────
@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", user=session.get("user"))

@app.route("/api/scan/run", methods=["POST"])
@login_required
def api_run_scan():
    if scan_state["status"] == "scanning":
        return jsonify({"error": "Scan already running"}), 429
    scan_state["status"] = "scanning"
    def do_scan():
        try:
            results = run_scan()
            scan_state["results"]   = results
            scan_state["last_scan"] = datetime.now(timezone.utc).isoformat()
            scan_state["status"]    = "idle"
        except Exception as e:
            scan_state["status"] = "error"
            print(f"Manual scan error: {e}")
    threading.Thread(target=do_scan, daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/api/scan/status")
@login_required
def api_scan_status():
    return jsonify({
        "status":    scan_state["status"],
        "last_scan": scan_state["last_scan"],
        "results":   scan_state["results"],
        "next_scan": scan_state["next_scan"],
    })

@app.route("/api/signals/history")
@login_required
def api_signal_history():
    return jsonify(get_recent_signals(50))

@app.route("/api/scans/history")
@login_required
def api_scans_history():
    return jsonify(get_scan_history(20))

@app.route("/api/session")
@login_required
def api_session():
    now_utc = datetime.now(timezone.utc)
    hour    = now_utc.hour
    active  = []

    if 0 <= hour < 9:   active.append("Tokyo")
    if 8 <= hour < 17:  active.append("London")
    if 13 <= hour < 22: active.append("New York")

    overlap = None
    if "London" in active and "Tokyo" in active:
        overlap = "Tokyo/London Overlap — High Volatility"
    if "London" in active and "New York" in active:
        overlap = "London/New York Overlap — PEAK Volatility 🔥"

    if overlap:
        quality, tip = "prime", overlap
    elif active:
        quality, tip = "good", f"{' + '.join(active)} session active"
    else:
        quality, tip = "quiet", "All sessions closed — low liquidity, avoid trading"

    return jsonify({
        "utc_time": now_utc.strftime("%H:%M UTC"),
        "active":   active,
        "overlap":  overlap,
        "quality":  quality,
        "tip":      tip,
    })

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    scanner_thread = threading.Thread(target=background_scanner, daemon=True)
    scanner_thread.start()
    print("\n" + "="*55)
    print("  📊 Forex Dashboard running!")
    print("  Open your browser to: http://localhost:5000")
    print("="*55 + "\n")
    app.run(debug=False, port=5000, use_reloader=False)
