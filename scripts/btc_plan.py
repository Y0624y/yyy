"""Fetch BTC/USDT swap data from OKX — raw data only, no plan calculation."""
import json
import ssl
import urllib.request

OKX_BASE = "https://www.oxyizhgwne.org"
INST_ID = "BTC-USDT-SWAP"


def okx_get(path: str) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"{OKX_BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        return json.loads(r.read())


def main():
    ticker = okx_get(f"/api/v5/market/ticker?instId={INST_ID}")["data"][0]
    current = float(ticker["last"])
    high24 = float(ticker["high24h"])
    low24 = float(ticker["low24h"])

    candles = okx_get(f"/api/v5/market/candles?instId={INST_ID}&bar=1H&limit=12")["data"]
    candles.reverse()
    ranges = [float(c[2]) - float(c[3]) for c in candles]
    atr = sum(ranges) / len(ranges)

    print(f"current={current:.1f}")
    print(f"high24={high24:.1f}")
    print(f"low24={low24:.1f}")
    print(f"atr={atr:.1f}")
    print(f"ctVal=0.01")
    print(f"lotSz=0.01")


if __name__ == "__main__":
    main()
