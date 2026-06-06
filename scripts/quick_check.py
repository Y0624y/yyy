#!/usr/bin/env python3
"""一键查 ETH + SOL — 价格、结构、退场判断，一个脚本出结果"""
import json, ssl, urllib.request, sys

OKX = "https://www.oxyizhgwne.org"
EXIT = {"ETH-USDT-SWAP": 2030, "SOL-USDT-SWAP": 83.20}
POS = {"ETH-USDT-SWAP": {"entry": 2018, "sl": 2050}, "SOL-USDT-SWAP": {"entry": 82.80, "sl": 84.00}}

def okx(path):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(OKX + path, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
        return json.loads(r.read())

for inst in ["ETH-USDT-SWAP", "SOL-USDT-SWAP"]:
    t = okx(f"/api/v5/market/ticker?instId={inst}")["data"][0]
    p = float(t["last"])
    name = inst.split("-")[0]
    e = EXIT[inst]
    pos = POS[inst]
    pnl = (pos["entry"] - p) / pos["entry"] * 100 * 10
    alert = "TRIGGERED!" if p > e else "ok"
    print(f"{name} {p:.2f} exit={e} sl={pos['sl']} {alert} pnl~{pnl:+.1f}%")
