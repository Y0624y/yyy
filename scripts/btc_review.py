"""Review closed trades and suggest parameter adjustments to improve win rate."""
import json
import sys
from collections import defaultdict
from datetime import datetime

TRADES_FILE = r"C:\Users\qiu'bin\.claude\skills\btb\trades.jsonl"


def load_trades():
    trades = []
    with open(TRADES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                trades.append(json.loads(line))
    return trades


def closed(trades):
    return [t for t in trades if t.get("result") in ("win", "loss")]


def win_rate(ts):
    if not ts:
        return 0
    return sum(1 for t in ts if t["result"] == "win") / len(ts) * 100


def avg_pnl(ts):
    if not ts:
        return 0
    return sum(t["pnl"] for t in ts) / len(ts)


def analyze(trades):
    c = closed(trades)
    if len(c) < 3:
        print(f"只有 {len(c)} 笔已平仓交易，至少 3 笔才能分析。")
        return

    total = len(c)
    wins = [t for t in c if t["result"] == "win"]
    losses = [t for t in c if t["result"] == "loss"]
    wr = win_rate(c)
    total_pnl = sum(t["pnl"] for t in c)
    avg_win = avg_pnl(wins) if wins else 0
    avg_loss = avg_pnl(losses) if losses else 0

    print("══ 交易复盘 ══")
    print(f"时间: {datetime.now().strftime('%m-%d %H:%M')}")
    print(f"总交易: {total} | 赢: {len(wins)} | 输: {len(losses)}")
    print(f"胜率: {wr:.0f}%")
    print(f"累计盈亏: {total_pnl:+.2f}U")
    print(f"平均盈利: {avg_win:+.2f}U | 平均亏损: {avg_loss:+.2f}U")
    print(f"盈亏比: {abs(avg_win/avg_loss) if avg_loss else 0:.1f}")

    # Direction breakdown
    print("\n── 方向 ──")
    for d in ("long", "short"):
        dt = [t for t in c if t["direction"] == d]
        if dt:
            print(f"  {d}: {len(dt)}笔, 胜率 {win_rate(dt):.0f}%, 盈亏 {sum(t['pnl'] for t in dt):+.2f}U")

    # Zone breakdown
    print("\n── 价格区域 ──")
    for z in ("discount", "equilibrium", "premium"):
        zt = [t for t in c if t.get("zone") == z]
        if zt:
            print(f"  {z}: {len(zt)}笔, 胜率 {win_rate(zt):.0f}%")

    # SMC alignment
    print("\n── SMC 顺势 vs 逆势 ──")
    aligned = [t for t in c if t.get("smc_aligned", True)]
    contra = [t for t in c if not t.get("smc_aligned", True)]
    if aligned:
        print(f"  顺势: {len(aligned)}笔, 胜率 {win_rate(aligned):.0f}%")
    if contra:
        print(f"  逆势: {len(contra)}笔, 胜率 {win_rate(contra):.0f}%")

    # Suggestions
    print("\n── 优化建议 ──")
    if wr < 40:
        print("  ⚠ 胜率偏低，考虑只在顺势时开单")
    if avg_loss and abs(avg_loss) > abs(avg_win):
        print("  ⚠ 平均亏损 > 平均盈利，止损可能太宽或止盈太早")
    if losses and any(t.get("stopped_early") for t in losses):
        print("  ⚠ 有被扫止损后反转的单子，止损位可能需要放宽")

    # Direction bias
    for d in ("long", "short"):
        dt = [t for t in c if t["direction"] == d]
        if dt and win_rate(dt) < 30:
            print(f"  ⚠ {d} 方向胜率极低 ({win_rate(dt):.0f}%)，考虑暂不做{d}")

    if wr >= 50 and total_pnl > 0:
        print("  ✓ 策略整体正期望，保持当前参数")


def main():
    trades = load_trades()
    analyze(trades)


if __name__ == "__main__":
    main()
