#!/usr/bin/env python3
"""每15分钟检查 ETH/SOL 退场条件，触发时通过 cc-connect 发微信通知"""
import json
import time
import ssl
import urllib.request
import subprocess
import sys
from datetime import datetime

# 退场条件
EXIT_RULES = {
    "ETH": {"price": 2030, "above": True},   # 15m 收 > 2030 就走
    "SOL": {"price": 83.20, "above": True},  # 15m 收 > 83.20 就走
}

OKX_BASE = "https://www.oxyizhgwne.org"


def okx_get(path: str) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"{OKX_BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        return json.loads(r.read())


def get_price(inst_id: str) -> float:
    try:
        data = okx_get(f"/api/v5/market/ticker?instId={inst_id}-SWAP")
        return float(data["data"][0]["last"])
    except Exception as e:
        print(f"获取 {inst_id} 价格失败: {e}")
        return 0


def send_alert(msg: str):
    """通过 cc-connect 发送微信通知"""
    try:
        subprocess.run(["cc-connect", "send", "-p", "btb", "-m", msg],
                       capture_output=True, timeout=15)
    except Exception as e:
        print(f"发送通知失败: {e}")


def main():
    # 检查模式：一次性检查还是持续监控
    continuous = "--continuous" in sys.argv

    while True:
        now = datetime.now().strftime("%H:%M:%S")
        eth = get_price("ETH-USDT")
        sol = get_price("SOL-USDT")

        alerts = []
        status = []

        if eth > 0:
            eth_triggered = eth > EXIT_RULES["ETH"]["price"]
            status.append(f"ETH={eth:.2f} {'⚠️触发!' if eth_triggered else '正常'}")
            if eth_triggered:
                alerts.append(f"🔥 ETH 退场! 当前 {eth:.2f} > {EXIT_RULES['ETH']['price']}，立即平仓!")

        if sol > 0:
            sol_triggered = sol > EXIT_RULES["SOL"]["price"]
            status.append(f"SOL={sol:.2f} {'⚠️触发!' if sol_triggered else '正常'}")
            if sol_triggered:
                alerts.append(f"🔥 SOL 退场! 当前 {sol:.2f} > {EXIT_RULES['SOL']['price']}，立即平仓!")

        print(f"[{now}] {' | '.join(status)}")

        if alerts:
            alert_msg = "\n".join(alerts) + f"\n时间: {now}"
            print(alert_msg)
            send_alert(alert_msg)

        if not continuous:
            break

        time.sleep(900)  # 15 分钟


if __name__ == "__main__":
    main()
