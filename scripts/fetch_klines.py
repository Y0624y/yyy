#!/usr/bin/env python3
"""拉 Binance U 本位合约 K 线 + 计算 SMC 结构指标"""

import requests
import json
import sys
from datetime import datetime

BINANCE_FAPI = "https://fapi.binance.com/fapi/v1/klines"

def fetch(symbol: str, interval: str, limit: int = 100):
    """拉 K 线原始数据"""
    url = f"{BINANCE_FAPI}?symbol={symbol.upper()}&interval={interval}&limit={limit}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    candles = []
    for c in data:
        candles.append({
            "time": datetime.fromtimestamp(c[0]/1000).strftime("%m-%d %H:%M"),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        })
    return candles

def find_swings(candles):
    """找摆动高低点 (3-bar 确认)"""
    swings = []
    for i in range(2, len(candles) - 2):
        # Swing High
        if candles[i]["high"] > candles[i-1]["high"] and candles[i]["high"] > candles[i+1]["high"] and \
           candles[i]["high"] > candles[i-2]["high"] and candles[i]["high"] > candles[i+2]["high"]:
            swings.append({"type": "HH", "price": candles[i]["high"], "idx": i, "time": candles[i]["time"]})
        # Swing Low
        if candles[i]["low"] < candles[i-1]["low"] and candles[i]["low"] < candles[i+1]["low"] and \
           candles[i]["low"] < candles[i-2]["low"] and candles[i]["low"] < candles[i+2]["low"]:
            swings.append({"type": "LL", "price": candles[i]["low"], "idx": i, "time": candles[i]["time"]})
    return swings

def find_fvg(candles):
    """找 Fair Value Gap (3-candle pattern)"""
    fvgs = []
    for i in range(1, len(candles) - 1):
        # Bullish FVG: candle[i-1] high < candle[i+1] low
        if candles[i-1]["high"] < candles[i+1]["low"]:
            fvgs.append({"type": "bullish", "top": candles[i+1]["low"], "bottom": candles[i-1]["high"], "idx": i, "time": candles[i]["time"]})
        # Bearish FVG: candle[i-1] low > candle[i+1] high
        if candles[i-1]["low"] > candles[i+1]["high"]:
            fvgs.append({"type": "bearish", "top": candles[i+1]["high"], "bottom": candles[i-1]["low"], "idx": i, "time": candles[i]["time"]})
    return fvgs

def find_ob(candles, swings):
    """在最近的摆动点找 Order Block"""
    obs = []
    for s in swings[-6:]:
        idx = s["idx"]
        if s["type"] == "HH":
            # Bearish OB: 最后一根阳线的前一根阴线
            for j in range(idx, max(0, idx-5), -1):
                if candles[j]["close"] < candles[j]["open"]:
                    obs.append({"type": "bearish", "high": candles[j]["high"], "low": candles[j]["low"], "time": candles[j]["time"]})
                    break
        elif s["type"] == "LL":
            for j in range(idx, max(0, idx-5), -1):
                if candles[j]["close"] > candles[j]["open"]:
                    obs.append({"type": "bullish", "high": candles[j]["high"], "low": candles[j]["low"], "time": candles[j]["time"]})
                    break
    return obs

def analyze_trend(candles, swings):
    """判断趋势结构"""
    if len(swings) < 4:
        return "数据不足"

    recent = swings[-6:] if len(swings) >= 6 else swings
    hh = [s for s in recent if s["type"] == "HH"]
    ll = [s for s in recent if s["type"] == "LL"]

    results = []
    # 检查 HH 是否抬高
    if len(hh) >= 2:
        if hh[-1]["price"] > hh[-2]["price"]:
            results.append("HH↑(看涨)")
        else:
            results.append("HH↓(看跌)")
    # 检查 LL 是否抬高
    if len(ll) >= 2:
        if ll[-1]["price"] > ll[-2]["price"]:
            results.append("LL↑(看涨)")
        else:
            results.append("LL↓(看跌)")

    return results

def atr(candles, period=14):
    """计算 ATR"""
    if len(candles) < period + 1:
        return 0
    trs = []
    for i in range(1, min(len(candles), period+20)):
        c = candles[-i]
        p = candles[-i-1]
        tr = max(c["high"] - c["low"], abs(c["high"] - p["close"]), abs(c["low"] - p["close"]))
        trs.append(tr)
    trs = trs[:period]
    return sum(trs) / len(trs) if trs else 0

def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    interval = sys.argv[2] if len(sys.argv) > 2 else "15m"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 100

    candles = fetch(symbol, interval, limit)
    swings = find_swings(candles)
    fvgs = find_fvg(candles)
    obs = find_ob(candles, swings)
    trend = analyze_trend(candles, swings)
    cur_atr = atr(candles)

    last = candles[-1]

    print(f"\n{'='*60}")
    print(f"  {symbol} | {interval} | {candles[0]['time']} → {candles[-1]['time']}")
    print(f"{'='*60}")
    print(f"  当前价:  {last['close']:.2f}")
    print(f"  最高:    {last['high']:.2f}")
    print(f"  最低:    {last['low']:.2f}")
    print(f"  ATR(14): {cur_atr:.2f}")
    print()

    print(f"  📊 趋势结构: {' | '.join(trend) if trend else '无明确结构'}")
    print()

    # 近 24 根 K 的区间
    n = min(24, len(candles))
    recent = candles[-n:]
    high_24 = max(c["high"] for c in recent)
    low_24 = min(c["low"] for c in recent)
    print(f"  📏 近{n}根K线区间: {low_24:.2f} ~ {high_24:.2f} ({(high_24-low_24)/last['close']*100:.2f}%)")

    # 关键摆动点
    if swings:
        recent_swings = swings[-6:]
        print(f"\n  🔄 最近摆动点:")
        for s in recent_swings:
            emoji = "🔴" if s["type"] == "HH" else "🟢"
            print(f"     {emoji} {s['type']} @ {s['price']:.2f} [{s['time']}]")

    # FVG
    recent_fvgs = [f for f in fvgs if f["idx"] > len(candles) - 25]
    if recent_fvgs:
        print(f"\n  📐 FVG (近24根):")
        for f in recent_fvgs[-4:]:
            t = "牛旗🚩" if f["type"] == "bullish" else "熊旗🏴"
            print(f"     {t} {f['top']:.2f} ~ {f['bottom']:.2f} [{f['time']}]")

    # OB
    if obs:
        print(f"\n  📦 Order Block:")
        for o in obs[-4:]:
            t = "供给区" if o["type"] == "bearish" else "需求区"
            print(f"     {t} {o['low']:.2f} ~ {o['high']:.2f} [{o['time']}]")

    # 当前价格相对位置
    if high_24 != low_24:
        pos = (last["close"] - low_24) / (high_24 - low_24) * 100
        print(f"\n  📍 当前在{n}K区间位置: {pos:.0f}% ({'折价区' if pos < 30 else '溢价区' if pos > 70 else '均衡区'})")

    # 打印最近几根K线
    print(f"\n  📋 最近8根K线:")
    for c in candles[-8:]:
        direction = "🟢" if c["close"] > c["open"] else "🔴"
        print(f"     {direction} {c['time']} O:{c['open']:.2f} H:{c['high']:.2f} L:{c['low']:.2f} C:{c['close']:.2f}")

    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
