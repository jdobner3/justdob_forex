from dotenv import load_dotenv
import os
import time
from twelvedata import TDClient
import numpy as np

# ── Load API key securely ──────────────────────────────────────────────────────
load_dotenv("twelvedata_apikey.env")
API_KEY = os.getenv("TWELVE_DATA_API_KEY")

if not API_KEY:
    print("❌ API key not found. Check your twelvedata_apikey.env file.")
    exit()

td = TDClient(apikey=API_KEY)

# ── Settings ───────────────────────────────────────────────────────────────────
PAIRS = [
    "EUR/USD",  # Euro vs US Dollar
    "GBP/USD",  # British Pound vs US Dollar
    "USD/JPY",  # US Dollar vs Japanese Yen
    "USD/CHF",  # US Dollar vs Swiss Franc
    "AUD/USD",  # Australian Dollar vs US Dollar
    "USD/CAD",  # US Dollar vs Canadian Dollar
    "NZD/USD",  # New Zealand Dollar vs US Dollar
    "EUR/GBP",  # Euro vs British Pound
]

INTERVAL         = "1h"
BARS             = 100
ZONE_TOLERANCE   = 0.00030   # ~3 pips clustering tolerance
LEVEL_PROXIMITY  = 0.00100   # ~10 pips to be "at a level"
MIN_TOUCHES      = 2         # minimum zone strength to qualify
MIN_RR           = 1.5       # minimum risk/reward to qualify
API_DELAY        = 8         # seconds between calls (free tier = 8/min)

# ── Core Functions ─────────────────────────────────────────────────────────────
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

    # Hammer / Bullish Pin Bar
    if (lower_wick1 >= body1 * 2.0 and
            upper_wick1 <= body1 * 0.5 and
            lower_wick1 >= full_range1 * 0.55):
        patterns.append(("🔨 Hammer/Bull Pin Bar", "BUY",
                          "Strong" if lower_wick1 >= body1 * 3 else "Moderate"))

    # Shooting Star / Bearish Pin Bar
    if (upper_wick1 >= body1 * 2.0 and
            lower_wick1 <= body1 * 0.5 and
            upper_wick1 >= full_range1 * 0.55):
        patterns.append(("⭐ Shooting Star/Bear Pin Bar", "SELL",
                          "Strong" if upper_wick1 >= body1 * 3 else "Moderate"))

    # Bullish Engulfing
    if (bullish1 and bearish2 and c1 > o2 and o1 < c2 and body1 > body2 * 1.1):
        patterns.append(("🟢 Bullish Engulfing", "BUY",
                          "Strong" if body1 > body2 * 1.5 else "Moderate"))

    # Bearish Engulfing
    if (bearish1 and bullish2 and o1 > c2 and c1 < o2 and body1 > body2 * 1.1):
        patterns.append(("🔴 Bearish Engulfing", "SELL",
                          "Strong" if body1 > body2 * 1.5 else "Moderate"))

    # Doji
    if body1 <= full_range1 * 0.1 and full_range1 > 0.00010:
        patterns.append(("➖ Doji", "NEUTRAL", "Informational"))

    # Strong Momentum Candle
    if body1 >= full_range1 * 0.75 and full_range1 > 0.00020:
        direction = "BUY" if bullish1 else "SELL"
        label     = "🚀 Strong Bull Momentum" if bullish1 else "💥 Strong Bear Momentum"
        patterns.append((label, direction, "Strong"))

    # Inside Bar
    if h1 < h2 and l1 > l2:
        patterns.append(("📦 Inside Bar", "NEUTRAL", "Informational"))

    return patterns

def strength_label(touches):
    if touches >= 4: return "MAJOR"
    elif touches == 3: return "Strong"
    elif touches == 2: return "Moderate"
    else: return "Minor"

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
    if score >= 80:   return "A+ 🔥 Prime Setup"
    elif score >= 65: return "A  ✅ Strong Setup"
    elif score >= 50: return "B  👀 Watch This"
    elif score >= 35: return "C  ⚠️  Weak Setup"
    else:             return "D  ❌ Skip"

# ── Scanner ────────────────────────────────────────────────────────────────────
print(f"\n{'='*65}")
print(f"  📡 FOREX MULTI-PAIR SCANNER  |  Timeframe: {INTERVAL}")
print(f"  Scanning {len(PAIRS)} pairs — this takes ~{len(PAIRS) * API_DELAY}s on free tier...")
print(f"{'='*65}\n")

results = []
skipped = []

for i, pair in enumerate(PAIRS):
    print(f"  [{i+1}/{len(PAIRS)}] Scanning {pair}...", end="", flush=True)

    try:
        ts = td.time_series(
            symbol=pair,
            interval=INTERVAL,
            outputsize=BARS,
            type="forex"
        ).as_pandas()

        ts    = ts.sort_index()
        close = ts["close"].astype(float)
        high  = ts["high"].astype(float)
        low   = ts["low"].astype(float)
        open_ = ts["open"].astype(float)

        current = close.iloc[-1]

        # Structure levels
        res_zones = cluster_levels(find_swing_highs(high), ZONE_TOLERANCE)
        sup_zones = cluster_levels(find_swing_lows(low),   ZONE_TOLERANCE)
        res_above = sorted([(p, s) for p, s in res_zones if p > current], key=lambda x: x[0])
        sup_below = sorted([(p, s) for p, s in sup_zones if p < current], key=lambda x: x[0], reverse=True)
        nearest_res = res_above[0] if res_above else None
        nearest_sup = sup_below[0] if sup_below else None

        # RSI
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss
        rsi   = (100 - (100 / (1 + rs))).iloc[-1]

        # Patterns
        patterns = detect_patterns(open_, close, high, low, idx=-1)

        # Proximity check
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
                if zone_touches < MIN_TOUCHES:
                    continue
                if nearest_res:
                    to_target = (nearest_res[0] - current) * 10000
                    to_stop   = (current - zone_price) * 10000 + 5
                    rr        = round(to_target / to_stop, 2) if to_stop > 0 else 0
                else:
                    rr = 0
                if rr < MIN_RR:
                    continue
                score = score_setup(strength, zone_touches, rr, direction, rsi)
                if score > best_score:
                    best_score  = score
                    best_signal = {
                        "pair": pair, "direction": direction,
                        "pattern": pat_name, "strength": strength,
                        "at_level": zone_price, "touches": zone_touches,
                        "target": nearest_res[0] if nearest_res else None,
                        "stop": round(zone_price - 0.00050, 5),
                        "rr": rr, "rsi": round(rsi, 1),
                        "score": score, "current": current,
                    }

            elif direction == "SELL" and near_res:
                zone_price, zone_touches = near_res
                if zone_touches < MIN_TOUCHES:
                    continue
                if nearest_sup:
                    to_target = (current - nearest_sup[0]) * 10000
                    to_stop   = (zone_price - current) * 10000 + 5
                    rr        = round(to_target / to_stop, 2) if to_stop > 0 else 0
                else:
                    rr = 0
                if rr < MIN_RR:
                    continue
                score = score_setup(strength, zone_touches, rr, direction, rsi)
                if score > best_score:
                    best_score  = score
                    best_signal = {
                        "pair": pair, "direction": direction,
                        "pattern": pat_name, "strength": strength,
                        "at_level": zone_price, "touches": zone_touches,
                        "target": nearest_sup[0] if nearest_sup else None,
                        "stop": round(zone_price + 0.00050, 5),
                        "rr": rr, "rsi": round(rsi, 1),
                        "score": score, "current": current,
                    }

        if best_signal:
            results.append(best_signal)
            print(f" ✅ Setup found! Score: {best_signal['score']}/100")
        else:
            skipped.append(pair)
            print(f" — No qualifying setup")

    except Exception as e:
        skipped.append(pair)
        print(f" ❌ Error: {e}")

    if i < len(PAIRS) - 1:
        time.sleep(API_DELAY)

# ── Results ────────────────────────────────────────────────────────────────────
print(f"\n{'='*65}")
print(f"  📊 SCAN COMPLETE — {len(results)} setup(s) found across {len(PAIRS)} pairs")
print(f"{'='*65}")

if not results:
    print("""
  ⏳ NO QUALIFYING SETUPS RIGHT NOW.

  This is completely normal — the scanner is strict on purpose.
  It filtered everything out because nothing met all 3 gates:

    Gate 1: Price at a structure level (2+ touches)
    Gate 2: Candle pattern confirmed at that level
    Gate 3: Risk/Reward of at least 1.5:1

  Best times to run this scanner:
    → Sunday 5pm CT  (markets reopen)
    → Monday 3am CT  (London session open)
    → Monday 8am CT  (New York session open)
""")
else:
    results = sorted(results, key=lambda x: x["score"], reverse=True)
    print(f"\n  Ranked best → weakest:\n")

    for rank, r in enumerate(results, 1):
        direction_icon = "🟢 BUY" if r["direction"] == "BUY" else "🔴 SELL"
        print(f"  {'─'*60}")
        print(f"  #{rank}  {r['pair']}  |  {direction_icon}  |  {grade(r['score'])}  ({r['score']}/100)")
        print(f"  {'─'*60}")
        print(f"  Pattern  : {r['pattern']}  [{r['strength']}]")
        print(f"  Level    : {r['at_level']:.5f}  ({strength_label(r['touches'])} — {r['touches']} touches)")
        print(f"  Price    : {r['current']:.5f}")
        print(f"  RSI      : {r['rsi']}")
        print()
        print(f"  📌 TRADE PLAN:")
        print(f"    Entry  → Next candle open (~{r['current']:.5f})")
        print(f"    Stop   → {r['stop']:.5f}")
        if r["target"]:
            pips_target = abs(r["target"] - r["current"]) * 10000
            pips_stop   = abs(r["stop"]   - r["current"]) * 10000
            print(f"    Target → {r['target']:.5f}  ({pips_target:.1f} pips)")
            print(f"    Risk   → {pips_stop:.1f} pips  |  R/R: {r['rr']}:1")
        print()

    if skipped:
        print(f"  {'─'*60}")
        print(f"  ⏭️  No qualifying setup: {', '.join(skipped)}")

print(f"\n{'='*65}")
print(f"  ✅ Scanner done.")
print(f"  Best run times: Sunday 5pm CT | Mon 3am CT | Mon 8am CT")
print(f"{'='*65}\n")
