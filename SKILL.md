---
name: btb
description: BTC/USDT 永续合约交易计划。限价挂单等回调，严格止盈止损，R:R 1:2。通过 cc-connect 微信发送。Use when user types /btb.
---

# BTB — BTC 合约快报

## 权限声明

- Claude 全自动执行，**不问确认**，不等待用户批准
- 所有 Bash 命令、文件读写、网络请求、微信发送一律自动通过
- 复盘后根据数据**自动调整参数**，无需手动确认
- cc-connect 已配置 `mode = bypassPermissions` + `admin_from = *` + `allow_from = *`

## 触发方式

```
/btb <总资金> <最大亏损> <杠杆倍数>
```

例: `/btb 15 5 10` → 资金 15U，最多亏 5U，10 倍杠杆

## 核心规则

- **限价挂单等回调**，不追市价（入场 = 现价 × 0.99）
- **止损 ~1%**，止盈 ~2%，R:R 约 1:2
- **只用 77% 资金作保证金**，留 23% 应急
- **SMC 用来判断方向和微调止盈位**

## 执行流程

### Step 1 — 并行拉数据

```bash
python "C:\Users\qiu'bin\.claude\skills\btb\scripts\btc_plan.py" <资金> <亏损> <杠杆>
python "C:\Users\qiu'bin\.claude\skills\openmobius-skill\scripts\kb_klines.py" indicators --exchange binance --market perp --symbol BTCUSDT --interval 1h --format compact 2>&1
```

### Step 2 — 方向判断

- SMC 1H 摆动 + 内部趋势同向 → 顺势
- 价格在折扣区 + 看涨 FVG → 偏多
- 价格在溢价区 + 看跌 FVG → 偏空
- 矛盾 → 注明"等信号"

确定方向后，如果是做空，重新带方向参数跑脚本:
```bash
python "C:\Users\qiu'bin\.claude\skills\btb\scripts\btc_plan.py" <资金> <亏损> <杠杆> short
```

### Step 3 — 整合输出

脚本输出为基础，SMC 调整止盈位。格式：

```
══ BTC 合约快报 ══
时间: HH:MM

方向: 开多 / 开空

当前价: XX,XXX USDT

限价入场: XX,XXX
止损:     XX,XXX
止盈:     XX,XXX

XXx | X 张
保证金: XU | 应急: XU
亏: XU | 赚: XU
R:R 1:X

理由: 一句话
```

### Step 4 — 发送微信

```bash
cc-connect send -p btb -m "报告内容"
```

---

## 复盘与自优化

### 记录每笔交易

用户平仓后告诉 Claude 结果，Claude 自动更新 `trades.jsonl`:

```
/btb 复盘 止盈 +2.16U
/btb 复盘 止损 -1.08U 被扫后反转
```

记录字段：`date, direction, entry, exit, pnl, result(win/loss), leverage, contracts, budget, smc_swing, smc_internal, zone, atr, notes`

### 查看统计

```bash
python "C:\Users\qiu'bin\.claude\skills\btb\scripts\btc_review.py"
```

### 自动优化规则

积累 5+ 笔交易后，复盘脚本会分析并**自动生效**：

| 维度 | 统计 | 优化动作 |
|------|------|---------|
| 方向胜率 | 多 vs 空 | 哪边胜率低就自动跳过不做 |
| SMC 顺势 | 顺势 vs 逆势 | 逆势胜率 <40% → 强制只做顺势 |
| 价格区域 | 折扣/均衡/溢价 | 某区域胜率极低 → 自动避开 |
| 止损距离 | 被扫后反转次数 | 频繁被扫 → 自动放宽止损 0.5% |
| 盈亏比 | 平均赢/平均亏 | 亏损 > 盈利 → 自动收紧止损或放宽止盈 |

每 5 笔交易后自动跑复盘，优化建议直接写入脚本参数，无需用户确认。
