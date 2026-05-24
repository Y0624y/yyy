"""Fetch BTC/USDT swap data from OKX and generate a contract trading plan."""
import sys
import json
import ssl
import urllib.request
from datetime import datetime

# ── Config ──────────────────────────────────────────────
OKX_BASE = "https://www.oxyizhgwne.org"
INST_ID = "BTC-USDT-SWAP"
CONTRACT_VALUE = 0.01  # OKX perpetual: 1 contract = 0.01 BTC
LOT_SIZE = 0.01        # minimum order increment

# ── Trading style (from user's preferred approach) ──────
PULLBACK = 0.01   # entry: 1% away from current (limit order)
STOP_PCT = 0.01   # stop: 1% away from entry
TP_PCT = 0.02     # take profit: 2% away from entry (R:R ~1:2)
MARGIN_PCT = 0.77 # use ~77% of budget, keep 23% reserve

# ── Helpers ─────────────────────────────────────────────
def okx_get(path: str) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"{OKX_BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        return json.loads(r.read())


def fmt(p: float) -> str:
    return f"{p:,.1f}"


def main():
    budget = float(sys.argv[1])    # total capital USDT
    max_loss = float(sys.argv[2])  # max acceptable loss USDT
    leverage = float(sys.argv[3]) if len(sys.argv) > 3 else 10
    direction = sys.argv[4] if len(sys.argv) > 4 else "long"

    is_long = direction == "long"

    # ── 1. Ticker ───────────────────────────────────────
    ticker = okx_get(f"/api/v5/market/ticker?instId={INST_ID}")["data"][0]
    current = float(ticker["last"])
    high24 = float(ticker["high24h"])
    low24 = float(ticker["low24h"])

    # ── 2. Candles for context ───────────────────────────
    candles = okx_get(
        f"/api/v5/market/candles?instId={INST_ID}&bar=1H&limit=12"
    )["data"]
    candles.reverse()
    ranges = [float(c[2]) - float(c[3]) for c in candles]
    atr = sum(ranges) / len(ranges)

    # ── 3. Calculate plan ───────────────────────────────
    margin_used = budget * MARGIN_PCT

    if is_long:
        entry = current * (1 - PULLBACK)
        stop_price = entry * (1 - STOP_PCT)
        tp_price = entry * (1 + TP_PCT)
        stop_distance = entry - stop_price
    else:
        entry = current * (1 + PULLBACK)
        stop_price = entry * (1 + STOP_PCT)
        tp_price = entry * (1 - TP_PCT)
        stop_distance = stop_price - entry

    nominal_per_contract = CONTRACT_VALUE * entry
    position_value = margin_used * leverage
    contracts = float(position_value / nominal_per_contract)
    contracts = (contracts // LOT_SIZE) * LOT_SIZE

    actual_margin = contracts * nominal_per_contract / leverage
    per_contract_loss = stop_distance * CONTRACT_VALUE
    total_risk = per_contract_loss * contracts
    expected_profit = abs(tp_price - entry) * CONTRACT_VALUE * contracts

    # ── 4. Build output ─────────────────────────────────
    dir_label = "做多" if is_long else "做空"
    lines = [
        "══ BTC/USDT 永续合约 ══",
        f"时间: {datetime.now().strftime('%m-%d %H:%M')}",
        "",
        f"方向: {dir_label}",
        f"当前价:    {fmt(current)} USDT",
        f"24H 高/低: {fmt(high24)} / {fmt(low24)}",
        "",
        f"限价入场:  {fmt(entry)} USDT  (回调 {PULLBACK*100:.0f}%)",
        f"止损:      {fmt(stop_price)} USDT  (-{STOP_PCT*100:.0f}%)",
        f"止盈:      {fmt(tp_price)} USDT  (+{TP_PCT*100:.0f}%)",
        "",
        f"杠杆: {leverage:.0f}x | {contracts} 张",
        f"保证金: {actual_margin:.1f}U / 预算 {budget:.0f}U  (留 {budget-actual_margin:.1f}U 应急)",
        f"预计亏损: {total_risk:.2f}U  (上限 {max_loss:.0f}U)",
        f"预计盈利: {expected_profit:.2f}U",
        f"风险收益比: 1:{expected_profit/total_risk:.1f}" if total_risk > 0 else "",
        "",
        f"ATR: {atr:.0f} 点 | 止损距离: {stop_distance:.0f} 点",
    ]

    output = "\n".join(lines)
    sys.stdout.buffer.write(output.encode("utf-8"))


if __name__ == "__main__":
    main()
