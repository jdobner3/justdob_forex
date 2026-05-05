from dotenv import load_dotenv
import os
from twelvedata import TDClient
import pandas as pd
import numpy as np

# ── Load API key securely ──────────────────────────────────────────────────────
load_dotenv("twelvedata_apikey.env")
API_KEY = os.getenv("TWELVE_DATA_API_KEY")

if not API_KEY:
    print("❌ API key not found. Check your twelvedata_apikey.env file.")
    exit()

# ── Connect to Twelve Data ─────────────────────────────────────────────────────
td = TDClient(apikey=API_KEY)

# ── Settings ───────────────────────────────────────────────────────────────────
PAIR           = "EUR/USD"
INTERVAL       = "1h"
BARS           = 100
ZONE_TOLERANCE = 0.00030   # ~3 pips — how close swings must be to form a zone
LEVEL_PROXIMITY = 0.00100  # ~10 pips — how close price must be to a level for pattern to matter

print(f"\n{'='*60}")
print(f"  📊 FOREX ANALYSIS — {PAIR}  |  Timeframe: {INTERVAL}")
print(f"{'='*60}\n")

# ── Pull price data ────────────────────────────────────────────────────────────
try:
    ts = td.time_series(
        symbol=PAIR,
        interval=INTERVAL,
        outputsize=BARS,
        type="forex"
    ).as_pandas()

    ts    = ts.sort_index()
    close = ts["close"].astype(float)
    high  = ts["high"].astype(float)
    low   = ts["low"].astype(float)
    open_ = ts["open"].astype(float)

    current_price = close.iloc[-1]
    prev_price    = close.iloc[-2]
    change        = current_price - prev_price
    change_pct    = (change / prev_price) * 100

    print(f"  💱 Current Price : {current_price:.5f}")
    print(f"  {'🟢' if change >= 0 else '🔴'} Change (1 bar)  : {change:+.5f}  ({change_pct:+.2f}%)")
    print(f"  📅 Last Candle   : {ts.index[-1]}")

except Exception as e:
    print(f"❌ Error fetching price data: {e}")
    exit()

# ── Structure Level Detection ──────────────────────────────────────────────────
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

def strength_label(touches):
    if touches >= 4: return "🔴 MAJOR"
    elif touches == 3: return "🟠 Strong"
    elif touches == 2: return "🟡 Moderate"
    else: return "⚪ Minor"

swing_highs      = find_swing_highs(high, lookback=3)
swing_lows       = find_swing_lows(low,  lookback=3)
resistance_zones = cluster_levels(swing_highs, ZONE_TOLERANCE)
support_zones    = cluster_levels(swing_lows,  ZONE_TOLERANCE)

resistances_above = sorted([(p, s) for p, s in resistance_zones if p > current_price], key=lambda x: x[0])
supports_below    = sorted([(p, s) for p, s in support_zones    if p < current_price], key=lambda x: x[0], reverse=True)

nearest_resistance = resistances_above[0][0] if resistances_above else None
nearest_support    = supports_below[0][0]    if supports_below    else None

# ── Candle Pattern Detection ───────────────────────────────────────────────────
def analyze_candles(open_, close, high, low, idx=-1):
    """
    Analyze the last 2 candles for meaningful price action patterns.
    idx=-1 means the most recent closed candle.
    Returns a list of detected patterns with direction and strength.
    """
    patterns = []

    o1 = open_.iloc[idx]
    c1 = close.iloc[idx]
    h1 = high.iloc[idx]
    l1 = low.iloc[idx]

    o2 = open_.iloc[idx - 1]
    c2 = close.iloc[idx - 1]
    h2 = high.iloc[idx - 1]
    l2 = low.iloc[idx - 1]

    body1      = abs(c1 - o1)
    full_range1 = h1 - l1
    upper_wick1 = h1 - max(c1, o1)
    lower_wick1 = min(c1, o1) - l1

    body2      = abs(c2 - o2)
    full_range2 = h2 - l2

    bullish1 = c1 > o1
    bearish1 = c1 < o1
    bullish2 = c2 > o2
    bearish2 = c2 < o2

    # Avoid division by zero
    if full_range1 == 0 or body1 == 0:
        return patterns

    # ── PIN BAR / HAMMER (bullish) ─────────────────────────────────────────────
    # Long lower wick, small body near top — buyers rejected a push lower
    if (lower_wick1 >= body1 * 2.0 and
        upper_wick1 <= body1 * 0.5 and
        lower_wick1 >= full_range1 * 0.55):
        patterns.append({
            "name": "🔨 Hammer / Bullish Pin Bar",
            "direction": "BUY",
            "meaning": "Sellers pushed price down hard but buyers stepped in and rejected it. Strong reversal signal.",
            "strength": "Strong" if lower_wick1 >= body1 * 3 else "Moderate"
        })

    # ── SHOOTING STAR / BEARISH PIN BAR ───────────────────────────────────────
    # Long upper wick, small body near bottom — sellers rejected a push higher
    if (upper_wick1 >= body1 * 2.0 and
        lower_wick1 <= body1 * 0.5 and
        upper_wick1 >= full_range1 * 0.55):
        patterns.append({
            "name": "⭐ Shooting Star / Bearish Pin Bar",
            "direction": "SELL",
            "meaning": "Buyers pushed price up hard but sellers came in and smashed it back down. Strong reversal signal.",
            "strength": "Strong" if upper_wick1 >= body1 * 3 else "Moderate"
        })

    # ── BULLISH ENGULFING ──────────────────────────────────────────────────────
    # Big green candle completely swallows previous red candle
    if (bullish1 and bearish2 and
        c1 > o2 and o1 < c2 and
        body1 > body2 * 1.1):
        patterns.append({
            "name": "🟢 Bullish Engulfing",
            "direction": "BUY",
            "meaning": "Buyers completely overpowered sellers. The green candle swallowed the previous red one — momentum shift to upside.",
            "strength": "Strong" if body1 > body2 * 1.5 else "Moderate"
        })

    # ── BEARISH ENGULFING ──────────────────────────────────────────────────────
    # Big red candle completely swallows previous green candle
    if (bearish1 and bullish2 and
        o1 > c2 and c1 < o2 and
        body1 > body2 * 1.1):
        patterns.append({
            "name": "🔴 Bearish Engulfing",
            "direction": "SELL",
            "meaning": "Sellers completely overpowered buyers. The red candle swallowed the previous green one — momentum shift to downside.",
            "strength": "Strong" if body1 > body2 * 1.5 else "Moderate"
        })

    # ── DOJI (indecision) ──────────────────────────────────────────────────────
    # Tiny body relative to range — buyers and sellers equal, market undecided
    if body1 <= full_range1 * 0.1 and full_range1 > 0.00010:
        patterns.append({
            "name": "➖ Doji (Indecision)",
            "direction": "NEUTRAL",
            "meaning": "Buyers and sellers are perfectly balanced. Market is pausing — watch the NEXT candle for direction.",
            "strength": "Informational"
        })

    # ── STRONG MOMENTUM CANDLE ─────────────────────────────────────────────────
    # Large body, small wicks — pure directional momentum, possible breakout
    if (body1 >= full_range1 * 0.75 and
        full_range1 > 0.00020):
        direction = "BUY" if bullish1 else "SELL"
        patterns.append({
            "name": f"{'🚀' if bullish1 else '💥'} Strong Momentum Candle ({'Bullish' if bullish1 else 'Bearish'})",
            "direction": direction,
            "meaning": f"{'Buyers' if bullish1 else 'Sellers'} are in full control this candle — almost no wicks, pure body. Could signal a breakout if at a key level.",
            "strength": "Strong"
        })

    # ── INSIDE BAR (compression) ───────────────────────────────────────────────
    # Current candle is completely inside the previous — market compressing
    if h1 < h2 and l1 > l2:
        patterns.append({
            "name": "📦 Inside Bar (Compression)",
            "direction": "NEUTRAL",
            "meaning": "Price is coiling inside the previous candle's range. Energy is building. Expect a breakout soon — direction TBD.",
            "strength": "Informational"
        })

    return patterns

# ── Check if pattern is near a key level ──────────────────────────────────────
def near_level(price, levels, proximity):
    for level_price, touches in levels:
        if abs(price - level_price) <= proximity:
            return level_price, touches
    return None, None

# ── Run pattern detection ──────────────────────────────────────────────────────
patterns = analyze_candles(open_, close, high, low, idx=-1)

# Check proximity to structure
near_res_price, near_res_touches = near_level(current_price, resistance_zones, LEVEL_PROXIMITY)
near_sup_price, near_sup_touches = near_level(current_price, support_zones,    LEVEL_PROXIMITY)
at_level = near_res_price is not None or near_sup_price is not None

# ── Output: Moving Averages ────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print("  📈 MOVING AVERAGES")
print(f"{'─'*60}")

ma20 = close.rolling(window=20).mean().iloc[-1]
ma50 = close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else None

print(f"  MA20 : {ma20:.5f}  {'← Price ABOVE (bullish)' if current_price > ma20 else '← Price BELOW (bearish)'}")
if ma50:
    print(f"  MA50 : {ma50:.5f}  {'← Price ABOVE (bullish)' if current_price > ma50 else '← Price BELOW (bearish)'}")

# ── Output: RSI ───────────────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print("  ⚡ RSI  (14 period)")
print(f"{'─'*60}")

delta = close.diff()
gain  = delta.clip(lower=0).rolling(14).mean()
loss  = (-delta.clip(upper=0)).rolling(14).mean()
rs    = gain / loss
rsi   = (100 - (100 / (1 + rs))).iloc[-1]

if rsi >= 70:   rsi_label = "⚠️  OVERBOUGHT"
elif rsi <= 30: rsi_label = "⚠️  OVERSOLD"
elif rsi >= 55: rsi_label = "🟢 Bullish momentum"
elif rsi <= 45: rsi_label = "🔴 Bearish momentum"
else:           rsi_label = "⚪ Neutral"

print(f"  RSI  : {rsi:.1f}  {rsi_label}")

# ── Output: Structure Levels ──────────────────────────────────────────────────
print(f"\n{'─'*60}")
print("  🧱 STRUCTURE LEVELS")
print(f"{'─'*60}")

print("  📛 RESISTANCE ABOVE:")
if resistances_above:
    for i, (price, touches) in enumerate(resistances_above[:4]):
        dist = (price - current_price) * 10000
        print(f"    {i+1}. {price:.5f}  {strength_label(touches)}  {touches} touch(es)  {dist:.1f} pips away")
else:
    print("    None detected")

print("  📗 SUPPORT BELOW:")
if supports_below:
    for i, (price, touches) in enumerate(supports_below[:4]):
        dist = (current_price - price) * 10000
        print(f"    {i+1}. {price:.5f}  {strength_label(touches)}  {touches} touch(es)  {dist:.1f} pips away")
else:
    print("    None detected")

# ── Output: Candle Patterns ───────────────────────────────────────────────────
print(f"\n{'─'*60}")
print("  🕯️  CANDLE PATTERN ANALYSIS  (last closed candle)")
print(f"{'─'*60}")

if near_res_price:
    print(f"  ⚠️  Price is within 10 pips of RESISTANCE at {near_res_price:.5f} ({near_res_touches} touches)")
if near_sup_price:
    print(f"  ⚠️  Price is within 10 pips of SUPPORT at {near_sup_price:.5f} ({near_sup_touches} touches)")
if not at_level:
    print(f"  ℹ️  Price is NOT near a key structure level (patterns less significant here)")

print()

if patterns:
    for p in patterns:
        print(f"  {p['name']}  [{p['strength']}]")
        print(f"  → {p['meaning']}")

        # Amplify or dampen based on level proximity
        if at_level:
            if p["direction"] == "BUY" and near_sup_price:
                print(f"  ✅ CONFIRMED by structure — this pattern is AT support. Higher probability buy signal.")
            elif p["direction"] == "SELL" and near_res_price:
                print(f"  ✅ CONFIRMED by structure — this pattern is AT resistance. Higher probability sell signal.")
            elif p["direction"] in ["BUY", "SELL"]:
                print(f"  ⚠️  Pattern detected but near the OPPOSITE level — trade with caution.")
        else:
            if p["direction"] in ["BUY", "SELL"]:
                print(f"  ⚠️  Pattern in open space — no structure confirmation. Lower probability.")
        print()
else:
    print("  No significant pattern on the last candle.")
    print("  This is normal — most candles don't signal anything. Patience is the edge.")

# ── Plain English Summary ─────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  🧠 PLAIN ENGLISH SUMMARY")
print(f"{'='*60}")

# Trend
if current_price > ma20 and (ma50 is None or current_price > ma50):
    trend = "bullish"
elif current_price < ma20 and (ma50 is None or current_price < ma50):
    trend = "bearish"
else:
    trend = "mixed / undecided"

# Signal summary
buy_signals  = [p for p in patterns if p["direction"] == "BUY"]
sell_signals = [p for p in patterns if p["direction"] == "SELL"]
neutral      = [p for p in patterns if p["direction"] == "NEUTRAL"]

print(f"\n  Trend     : {trend}")
print(f"  RSI       : {rsi:.1f} — {rsi_label}")

if nearest_resistance and nearest_support:
    to_res = (nearest_resistance - current_price) * 10000
    to_sup = (current_price - nearest_support) * 10000
    rr_buy  = round(to_res / to_sup, 2) if to_sup > 0 else "N/A"
    rr_sell = round(to_sup / to_res, 2) if to_res > 0 else "N/A"
    pct     = (to_sup / (to_res + to_sup)) * 100
    print(f"  Position  : {pct:.0f}% from support → resistance")
    print(f"  R/R Buy   : {rr_buy}:1  |  R/R Sell : {rr_sell}:1")

print()

# Final call
if buy_signals and near_sup_price:
    print(f"  🟢 BUY SIGNAL DETECTED")
    print(f"  Pattern + structure support align. Price is near support at {near_sup_price:.5f}.")
    print(f"  Watch for price to hold above support and move toward {nearest_resistance:.5f if nearest_resistance else 'next resistance'}.")
    print(f"  Suggested stop: just below {near_sup_price:.5f if near_sup_price else 'support'}")
elif sell_signals and near_res_price:
    print(f"  🔴 SELL SIGNAL DETECTED")
    print(f"  Pattern + structure resistance align. Price is near resistance at {near_res_price:.5f}.")
    print(f"  Watch for price to reject and fall toward {nearest_support:.5f if nearest_support else 'next support'}.")
    print(f"  Suggested stop: just above {near_res_price:.5f if near_res_price else 'resistance'}")
elif neutral:
    print(f"  ⚪ INDECISION — Market is pausing.")
    print(f"  Watch the next candle for directional confirmation before acting.")
elif patterns and not at_level:
    print(f"  ⚠️  Pattern detected but NOT at a key level.")
    print(f"  Wait for price to reach structure before acting on this signal.")
else:
    print(f"  ⏳ NO SIGNAL — Nothing to act on right now.")
    print(f"  This is completely normal. The market doesn't always set up.")
    print(f"  Patience here IS the trade. Wait for a clean setup at a level.")

print(f"\n{'='*60}")
print("  ✅ Done. Run again on the next candle for a fresh read.")
print(f"{'='*60}\n")
