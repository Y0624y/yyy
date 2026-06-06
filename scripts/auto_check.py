#!/usr/bin/env python3
"""每3小时自动 SMC 结构检查 — 打架就闭嘴，同向出方案推微信"""
import json, ssl, urllib.request, subprocess, sys, os, re

OKX = "https://www.oxyizhgwne.org"
SYMBOLS = {"ETH": "ETH-USDT-SWAP", "SOL": "SOL-USDT-SWAP", "BTC": "BTC-USDT-SWAP"}
CC = r"C:\Users\qiu'bin\AppData\Roaming\npm\cc-connect.cmd"


def okx(path):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(OKX + path, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        return json.loads(r.read())


def get_price(inst):
    return float(okx(f"/api/v5/market/ticker?instId={inst}")["data"][0]["last"])


def send_wechat(msg):
    try:
        subprocess.run([CC, "send", "-p", "btb", "-m", msg], capture_output=True, timeout=15)
    except:
        pass


def main():
    # 获取 SMC 结构（调用 kb_klines）
    results = {}
    for name, inst in [("SOL", "SOLUSDT"), ("ETH", "ETHUSDT")]:
        r = subprocess.run(["python", f"C:\\Users\\qiu'bin\\.claude\\skills\\openmobius-skill\\scripts\\kb_klines.py",
                     "indicators", "--exchange", "binance", "--market", "perp",
                     "--symbol", inst, "--interval", "1h", "--format", "compact"],
                    capture_output=True, text=True, timeout=120)
        output = r.stdout + r.stderr
        swing = re.search(r'smc_swing_trend=(-?\d+)', output)
        internal = re.search(r'smc_internal_trend=(-?\d+)', output)
        results[name] = {
            "swing": int(swing.group(1)) if swing else None,
            "internal": int(internal.group(1)) if internal else None
        }

    # 判断
    alerts = []
    for name, r in results.items():
        s, i = r["swing"], r["internal"]
        if s is None:
            continue
        price = get_price(SYMBOLS[name])
        sd = "空" if s == -1 else ("多" if s == 1 else "中性")
        id_ = "多" if i == 1 else ("空" if i == -1 else "中性")

        if s == i:
            direction = "多" if s == 1 else "空"
            alerts.append(f"SIGNAL {name}: swing{sd}+internal{id_} -> {direction} @ {price:.2f}")
        else:
            print(f"{name}: conflict swing{sd}+internal{id_} | {price:.2f}")

    if alerts:
        msg = "SIGNAL!\n" + "\n".join(alerts)
        print(msg)
        send_wechat(msg)
    else:
        print("no signal")


if __name__ == "__main__":
    main()
