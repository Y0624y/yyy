#!/usr/bin/env python3
"""OKX 交易脚本 — 自动选择可用域名"""
import json, hmac, hashlib, base64, time, urllib.request, ssl, sys, io

# Fix encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = "519f88bf-614b-4908-8219-a979c5918280"
SECRET_KEY = "E4F2E1963AFD0F4F3B80EFA06AE59978"
PASSPHRASE = "Qq20050518@"
BASES = ["https://www.okx.com", "https://www.oxyizhgwne.org"]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def find_working_base():
    for base in BASES:
        try:
            url = base + "/api/v5/public/time"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
                json.loads(r.read())
            return base
        except:
            continue
    return None


BASE = find_working_base()


def okx_request(method, path, body=""):
    ts = str(int(time.time() * 1000))
    sign_msg = ts + method + path + body
    sign = base64.b64encode(
        hmac.new(SECRET_KEY.encode(), sign_msg.encode(), hashlib.sha256).digest()
    ).decode()

    headers = {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json",
    }

    data = body.encode() if body else None
    req = urllib.request.Request(
        BASE + path, data=data, headers=headers,
        method="POST" if data else "GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "msg": e.read().decode()}


def cmd_balance():
    resp = okx_request("GET", "/api/v5/account/balance")
    if "error" in resp:
        print(f"[ERROR] {resp['msg']}")
        return
    for d in resp.get("data", []):
        for det in d.get("details", []):
            eq = float(det.get("eq", 0))
            if eq > 0:
                print(f"  {det['ccy']}: {det['eq']} (avail: {det['availEq']})")
    if not any(
        float(det.get("eq", 0)) > 0
        for d in resp.get("data", [])
        for det in d.get("details", [])
    ):
        print("  empty")


def cmd_position():
    resp = okx_request("GET", "/api/v5/account/positions")
    if "error" in resp:
        print(f"[ERROR] {resp['msg']}")
        return
    has = False
    for d in resp.get("data", []):
        pos = float(d.get("pos", 0))
        if pos != 0:
            has = True
            side = "LONG" if d.get("posSide") == "long" else "SHORT"
            print(f"  {d['instId']} {side} {pos} | PnL:{d.get('upl','0')}U | Entry:{d.get('avgPx')}")
    if not has:
        print("  no position")


def cmd_order(inst, side, sz, px=None):
    body = {
        "instId": inst,
        "tdMode": "cross",
        "side": side,
        "ordType": "limit" if px else "market",
        "sz": str(sz),
    }
    if px:
        body["px"] = str(px)
    resp = okx_request("POST", "/api/v5/trade/order", json.dumps(body))
    if "error" in resp:
        print(f"[ERROR] {resp['msg']}")
    else:
        data = resp.get("data", [{}])[0]
        sCode = data.get("sCode", "-1")
        if sCode == "0":
            print(f"OK {data.get('sMsg','')} | ID:{data.get('ordId','')}")
        else:
            print(f"FAIL {data.get('sMsg','')} | code:{sCode}")


def cmd_close(inst):
    resp = okx_request("GET", "/api/v5/account/positions")
    for d in resp.get("data", []):
        if d["instId"] == inst and float(d.get("pos", 0)) != 0:
            side = "sell" if d.get("posSide") == "long" else "buy"
            close_sz = str(abs(float(d.get("pos", 0))))
            pos_side = d.get("posSide")
            body = {
                "instId": inst,
                "tdMode": "cross",
                "side": side,
                "ordType": "market",
                "sz": close_sz,
                "posSide": pos_side,
            }
            r = okx_request("POST", "/api/v5/trade/order", json.dumps(body))
            if "error" in r:
                print(f"[ERROR] {r['msg']}")
            else:
                dd = r.get("data", [{}])[0]
                print(f"CLOSED: {dd.get('sMsg','OK')}")
            return
    print("no position to close")


if __name__ == "__main__":
    if BASE is None:
        print("[ERROR] Cannot connect to OKX")
        sys.exit(1)

    print(f"Connected: {BASE}")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python okx_trade.py balance")
        print("  python okx_trade.py position")
        print("  python okx_trade.py sell SOL-USDT-SWAP 1 77.50")
        print("  python okx_trade.py buy SOL-USDT-SWAP 1 77.00")
        print("  python okx_trade.py market SOL-USDT-SWAP sell 1")
        print("  python okx_trade.py close SOL-USDT-SWAP")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "balance":
        cmd_balance()
    elif cmd == "position":
        cmd_position()
    elif cmd == "sell":
        cmd_order(sys.argv[2], "sell", sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "buy":
        cmd_order(sys.argv[2], "buy", sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "market":
        inst, side, sz = sys.argv[2], sys.argv[3], sys.argv[4]
        cmd_order(inst, side, sz)
    elif cmd == "close":
        cmd_close(sys.argv[2])
    else:
        print(f"Unknown: {cmd}")
