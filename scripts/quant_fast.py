#!/usr/bin/env python3
"""快扫系统 - 1H+15m 双周期，抓结构 + 位置 + K线三重确认。
3D=慢（等日线），快扫=快（15m结构确认即入场）。
小仓快进快出，不扛单。"""

import subprocess, sys, json, os, ssl
import urllib.request as urlreq
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')
BJT = timezone(timedelta(hours=8))

# ============== 配置 ==============
MOBIUS = r"C:\Users\qiu'bin\.claude\skills\openmobius-skill\scripts\kb_klines.py"
TEMP = r"C:\Users\qiu'bin\Desktop\btb\scripts\_fast_ohlcv.json"

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
OKX_INST = {'BTCUSDT': 'BTC-USDT-SWAP', 'ETHUSDT': 'ETH-USDT-SWAP', 'SOLUSDT': 'SOL-USDT-SWAP'}

# ============== OKX 直取 ==============
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def okx_get(path):
    url = f"https://www.oxyizhgwne.org{path}"
    req = urlreq.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlreq.urlopen(req, timeout=8, context=ctx) as r:
        return json.loads(r.read())

def okx_ticker(sym):
    try:
        d = okx_get(f"/api/v5/market/ticker?instId={OKX_INST[sym]}")["data"][0]
        return {'price': float(d['last']), 'high24': float(d['high24h']), 'low24': float(d['low24h'])}
    except:
        return None

def okx_15m(sym, limit=60):
    try:
        raw = okx_get(f"/api/v5/market/candles?instId={OKX_INST[sym]}&bar=15m&limit={limit}")["data"]
        raw.reverse()
        return [[int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])] for c in raw]
    except:
        return []

# ============== Mobius SMC ==============
def fetch_smc(sym, interval, limit=60):
    p = subprocess.run(
        f'python "{MOBIUS}" fetch --exchange bybit --market perp '
        f'--symbol {sym} --interval {interval} --limit {limit} --output "{TEMP}" 2>&1',
        shell=True, capture_output=True, text=True, encoding='utf-8')
    try:
        with open(TEMP, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data['primary']['candles']
    except:
        return []

def parse_smc(raw):
    d = {}
    for line in raw.split('\n'):
        line = line.strip()
        if 'current_price:' in line:
            d['price'] = float(line.split(':')[1].strip())
        if 'smc_swing_trend=' in line:
            if ':  ' in line:
                line = line.split(':  ', 1)[1]
            for p in line.split(','):
                p = p.strip()
                if '=' in p:
                    k, v = p.split('=', 1)
                    k, v = k.strip(), v.strip()
                    try:
                        d[k] = float(v) if '.' in v or v.lstrip('-').isdigit() else (v == 'True')
                    except:
                        d[k] = v
        if 'zones:' in line:
            for part in line.split('|'):
                part = part.strip()
                for zname in ['premium', 'equilibrium', 'discount']:
                    if f'{zname}=' in part:
                        vals = part.split(f'{zname}=')[-1].strip().split('-')
                        if len(vals) == 2:
                            try:
                                d[f'{zname}_lo'] = float(vals[0])
                                d[f'{zname}_hi'] = float(vals[1])
                            except:
                                pass
    return d

# ============== V形反转检测 ==============
def detect_v_reversal(candles):
    """检测 V底/V顶 反转形态。返回 ('V底'|'V顶'|None, score)"""
    if len(candles) < 8:
        return None, 0

    # V底：连跌3+根 → 急跌加速 → 反转阳线拉回
    last5 = candles[-5:]
    bodies = [(c[4] - c[1], c[2] - c[3]) for c in last5]  # (body, range)
    wicks_low = [min(c[1], c[4]) - c[3] for c in last5]   # lower wick

    # 前3根连续下跌
    first3_down = all(last5[i][4] < last5[i][1] for i in range(3))
    # 后2根反转：第4根长下影或阳线，第5根阳线
    candle4_reversal = (wicks_low[3] > abs(bodies[3][0]) * 1.5) or (last5[3][4] > last5[3][1])
    candle5_bull = last5[4][4] > last5[4][1]

    if first3_down and candle4_reversal and candle5_bull:
        return 'V底', 2.0

    # V顶：连涨3+根 → 急涨加速 → 反转阴线砸回
    wicks_high = [c[2] - max(c[1], c[4]) for c in last5]  # upper wick
    first3_up = all(last5[i][4] > last5[i][1] for i in range(3))
    candle4_reversal_top = (wicks_high[3] > abs(bodies[3][0]) * 1.5) or (last5[3][4] < last5[3][1])
    candle5_bear = last5[4][4] < last5[4][1]

    if first3_up and candle4_reversal_top and candle5_bear:
        return 'V顶', 2.0

    return None, 0


# ============== KDJ ==============
def calc_kdj(candles, n=9):
    """KDJ随机指标。返回 {k, d, j, zone} 或 None"""
    if len(candles) < n + 2:
        return None
    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    closes = [c[4] for c in candles]

    k_vals, d_vals = [], []
    pk, pd = 50, 50
    for i in range(n, len(closes)):
        hh = max(highs[i-n:i])
        ll = min(lows[i-n:i])
        rng = hh - ll
        rsv = (closes[i] - ll) / rng * 100 if rng > 0 else 50
        ki = 2/3 * pk + 1/3 * rsv
        di = 2/3 * pd + 1/3 * ki
        k_vals.append(ki)
        d_vals.append(di)
        pk, pd = ki, di

    k, d = k_vals[-1], d_vals[-1]
    j = 3 * k - 2 * d
    pk2 = k_vals[-2] if len(k_vals) >= 2 else k
    pd2 = d_vals[-2] if len(d_vals) >= 2 else d

    zone = 'overbought' if k > 80 else ('oversold' if k < 20 else 'neutral')
    return {'k': round(k, 1), 'd': round(d, 1), 'j': round(j, 1),
            'prev_k': round(pk2, 1), 'prev_d': round(pd2, 1), 'zone': zone}


def kdj_lock(kdj, direction):
    """KDJ极端值硬锁。返回 (blocked, reason)"""
    if not kdj:
        return False, ''
    j = kdj['j']
    if direction == 'short' and j < -5:
        return True, f'J={j:.0f}<-5 极端超卖 禁空!'
    if direction == 'long' and j > 105:
        return True, f'J={j:.0f}>105 极端超买 禁多!'
    return False, ''


# ============== 流动性扫荡 ==============
def find_swing_points(candles, lookback=5):
    """找摆动高低点"""
    swings = []
    n = len(candles)
    for i in range(lookback, n - lookback):
        h = candles[i][2]
        l = candles[i][3]
        is_high = all(h >= candles[j][2] for j in range(i - lookback, i + lookback + 1) if j != i)
        is_low = all(l <= candles[j][3] for j in range(i - lookback, i + lookback + 1) if j != i)
        if is_high:
            swings.append({'index': i, 'type': 1, 'level': h})
        elif is_low:
            swings.append({'index': i, 'type': -1, 'level': l})
    return swings


def detect_liquidity_sweep(candles, direction='short'):
    """检测流动性扫荡。返回 (has_sweep, score, detail)"""
    swings = find_swing_points(candles, lookback=5)
    if len(swings) < 4:
        return False, 0, ''

    all_h = [c[2] for c in candles]
    all_l = [c[3] for c in candles]
    pip = (max(all_h) - min(all_l)) * 0.005

    # Equal Highs — 空头用
    highs = [s for s in swings if s['type'] == 1 and s['index'] < len(candles) - 3]
    for i, h1 in enumerate(highs):
        group = [h1]
        for h2 in highs[i+1:]:
            if abs(h2['level'] - h1['level']) <= pip:
                group.append(h2)
            else:
                break
        if len(group) >= 2:
            last_idx = max(g['index'] for g in group)
            avg = sum(g['level'] for g in group) / len(group)
            for c in range(last_idx + 1, len(candles)):
                if candles[c][2] > avg + pip * 0.5:
                    return True, 1.0, f'EqualHighs ${avg:.1f}(x{len(group)})已扫→多方止损被吃'

    # Equal Lows — 多头用
    lows = [s for s in swings if s['type'] == -1 and s['index'] < len(candles) - 3]
    for i, l1 in enumerate(lows):
        group = [l1]
        for l2 in lows[i+1:]:
            if abs(l2['level'] - l1['level']) <= pip:
                group.append(l2)
            else:
                break
        if len(group) >= 2:
            last_idx = max(g['index'] for g in group)
            avg = sum(g['level'] for g in group) / len(group)
            for c in range(last_idx + 1, len(candles)):
                if candles[c][3] < avg - pip * 0.5:
                    return True, 1.0, f'EqualLows ${avg:.1f}(x{len(group)})已扫→空方止损被吃'

    return False, 0, ''


# ============== K线形态（2档确认 + 量验证） ==============
def candle_signal(candles, direction='short'):
    """ICT确认蜡烛规则：信号K后2根内需确认K同向收盘。
    candles[-3..-2]=信号窗口 candles[-2..-1]=确认窗口
    确认K量>=信号K量 → 强确认。无确认=弱分。"""

    if len(candles) < 5:
        return 0, 'K线不够'

    def k_body(ck): return abs(ck[4] - ck[1])
    def k_tr(ck): return max(ck[2] - ck[3], 0.0001)
    def k_uw(ck): return ck[2] - max(ck[1], ck[4])
    def k_lw(ck): return min(ck[1], ck[4]) - ck[3]

    score = 0
    reasons = []

    # 信号K: 看 candles[-3] 和 candles[-2]（给2根窗口找信号）
    signal_found = False
    signal_idx = -2
    signal_name = ''

    for si in [-3, -2]:
        sk = candles[si]
        s_body = k_body(sk); s_tr = k_tr(sk)
        s_uw = k_uw(sk); s_lw = k_lw(sk)

        if direction == 'short':
            if s_uw >= s_body * 2 and s_lw < s_uw * 0.3:
                signal_found = True; signal_idx = si; signal_name = '射击之星'; break
            if s_uw / max(s_tr, 0.0001) >= 0.6 and s_body / max(s_tr, 0.0001) < 0.5:
                signal_found = True; signal_idx = si; signal_name = '长上影'; break
            if s_body / max(s_tr, 0.0001) < 0.3:
                signal_found = True; signal_idx = si; signal_name = '十字星'; break
            # 熊吞没（si vs si-1）
            if si == -2 and len(candles) >= 4:
                p = candles[-3]
                if p[4] > p[1] and sk[4] < sk[1] and sk[1] > p[4] and sk[4] < p[1]:
                    signal_found = True; signal_idx = si; signal_name = '熊吞没'; break
        else:  # long
            if s_lw >= s_body * 2 and s_uw < s_lw * 0.3:
                signal_found = True; signal_idx = si; signal_name = '锤子线'; break
            if s_lw / max(s_tr, 0.0001) >= 0.6 and s_body / max(s_tr, 0.0001) < 0.5:
                signal_found = True; signal_idx = si; signal_name = '长下影'; break
            if s_body / max(s_tr, 0.0001) < 0.3:
                signal_found = True; signal_idx = si; signal_name = '十字星'; break
            if si == -2 and len(candles) >= 4:
                p = candles[-3]
                if p[4] < p[1] and sk[4] > sk[1] and sk[1] < p[4] and sk[4] > p[1]:
                    signal_found = True; signal_idx = si; signal_name = '牛吞没'; break

    if not signal_found:
        return 0, '无反转信号'

    # 确认窗口: 信号K之后的蜡烛（信号K在si，确认看si+1 和 si+2）
    signal_vol = candles[signal_idx][5]
    confirm_idxs = [signal_idx + 1, signal_idx + 2]
    confirm_idxs = [ci for ci in confirm_idxs if ci < 0]

    confirmed = False
    confirm_vol_ok = False
    confirm_detail = ''

    for ci in confirm_idxs:
        ck = candles[ci]
        c_vol = ck[5]
        if direction == 'short':
            c_ok = ck[4] < ck[1]
        else:
            c_ok = ck[4] > ck[1]

        if c_ok:
            confirmed = True
            confirm_detail = f'第{ci - signal_idx}根确认✅'
            if c_vol >= signal_vol * 0.8:
                confirm_vol_ok = True
                confirm_detail += '+量OK'
            break

    # 评分
    if confirmed:
        # 基础分按信号类型
        base = {'射击之星': 1.5, '锤子线': 1.5, '熊吞没': 1.5, '牛吞没': 1.5,
                '长上影': 1.0, '长下影': 1.0, '十字星': 0.75}.get(signal_name, 0.5)
        if confirm_vol_ok:
            base *= 1.0
        else:
            base *= 0.7
        score = base
        reasons.append(f'信号:{signal_name} | {confirm_detail}')
    else:
        score = 0.25
        reasons.append(f'信号:{signal_name} | 2根内无确认❌')

    return min(3, round(score, 1)), ' | '.join(reasons) if reasons else '无反转信号'

# ============== 量价衰竭 ==============
def volume_quick(candles, direction='short'):
    """成交量衰竭判断 — 短线核心：衰竭 = 变盘前兆。卖盘/买盘力竭 + 缩量 = 入场。

    做空看：买盘衰竭（反弹一波比一波量小）
    做多看：卖盘衰竭（下跌一波比一波量小）
    """
    if len(candles) < 12:
        return 0, 'K线不够'

    score = 0
    details = []
    vols = [c[5] for c in candles]

    # 1. 总成交量萎缩（全盘冷清 → 变盘前兆）
    recent_vol = sum(vols[-6:])
    prior_vol = sum(vols[-12:-6])
    if prior_vol > 0 and recent_vol < prior_vol * 0.7:
        score += 0.5
        pct = (1 - recent_vol / prior_vol) * 100
        details.append(f'量缩{pct:.0f}%(变盘前兆)')

    # 2. 波段衰竭检测
    # 切分涨跌波段
    waves = []
    cur_vol, cur_dir = 0, 0
    for i in range(1, min(15, len(candles))):
        idx = len(candles) - 1 - i
        c = candles[idx]
        di = 1 if c[4] > c[1] else (-1 if c[4] < c[1] else 0)
        if di == cur_dir:
            cur_vol += c[5]
        else:
            if cur_vol > 0:
                waves.append({'dir': cur_dir, 'vol': cur_vol})
            cur_dir, cur_vol = di, c[5]
    if cur_vol > 0:
        waves.append({'dir': cur_dir, 'vol': cur_vol})

    if direction == 'short':
        # 买盘衰竭：上涨波量一波比一波小
        up_waves = [w for w in waves if w['dir'] == 1]
        if len(up_waves) >= 3:
            v0, v1, v2 = up_waves[-3]['vol'], up_waves[-2]['vol'], up_waves[-1]['vol']
            if v2 < v1 < v0:
                decay = (1 - v2 / max(v0, 1)) * 100
                if decay >= 40:
                    score += 2.0
                    details.append(f'买盘枯竭(-{decay:.0f}%)三波缩量')
                elif decay >= 25:
                    score += 1.0
                    details.append(f'买盘衰减(-{decay:.0f}%)')
            elif v2 < v1:
                score += 0.5
                details.append('反弹量缩(买盘力竭)')
        else:
            details.append(f'涨波{len(up_waves)}个(需3+)')

        # 卖盘在加：下跌波量大于前波
        down_waves = [w for w in waves if w['dir'] == -1]
        if len(down_waves) >= 2:
            if down_waves[-1]['vol'] > down_waves[-2]['vol']:
                score += 0.5
                details.append('卖压增加(空头控盘)')

    else:  # long
        # 卖盘衰竭：下跌波量一波比一波小
        down_waves = [w for w in waves if w['dir'] == -1]
        if len(down_waves) >= 3:
            v0, v1, v2 = down_waves[-3]['vol'], down_waves[-2]['vol'], down_waves[-1]['vol']
            if v2 < v1 < v0:
                decay = (1 - v2 / max(v0, 1)) * 100
                if decay >= 40:
                    score += 2.0
                    details.append(f'卖盘枯竭(-{decay:.0f}%)三波缩量')
                elif decay >= 25:
                    score += 1.0
                    details.append(f'卖盘衰减(-{decay:.0f}%)')
            elif v2 < v1:
                score += 0.5
                details.append('下跌量缩(卖盘力竭)')
        else:
            details.append(f'跌波{len(down_waves)}个(需3+)')

        # 买盘在加
        up_waves = [w for w in waves if w['dir'] == 1]
        if len(up_waves) >= 2:
            if up_waves[-1]['vol'] > up_waves[-2]['vol']:
                score += 0.5
                details.append('买压增加(多头控盘)')

    # 3. 单根放量拒绝（最强即时信号）
    if len(vols) >= 10:
        avg10 = sum(vols[-10:]) / 10
        last_c = candles[-1]
        body = abs(last_c[4] - last_c[1])
        tr = max(last_c[2] - last_c[3], 0.0001)
        upper_wick = last_c[2] - max(last_c[1], last_c[4])
        lower_wick = min(last_c[1], last_c[4]) - last_c[3]

        if last_c[5] > avg10 * 1.5:
            if direction == 'short' and upper_wick / max(tr, 0.0001) >= 0.6:
                score += 1.5
                details.append('天量+长上影=空头拒绝')
            elif direction == 'long' and lower_wick / max(tr, 0.0001) >= 0.6:
                score += 1.5
                details.append('天量+长下影=多头拒绝')

    # 4. 成交量枯竭（成交少 = 发力结束）
    if len(vols) >= 20:
        avg20 = sum(vols[-20:]) / 20
        avg5 = sum(vols[-5:]) / 5
        if avg5 < avg20 * 0.5:
            score += 0.75
            details.append('成交枯竭(变盘在即)')

    return min(3, score), ' | '.join(details) if details else '无量价异常'

# ============== 关键位置 ==============
def near_key_level(price, smc_15, smc_1h, candles, direction='short'):
    """检查是否靠近关键结构位置"""
    score = 0
    details = []

    # PD Array 阻力/支撑
    for key in ['smc_internal_high_active', 'smc_swing_high_active']:
        level = smc_15.get(key, 0)
        if direction == 'short' and level > price:
            dist = (level - price) / price
            if dist <= 0.005:
                score += 1.5
                details.append(f'贴阻力 ${level:,.2f} (≤0.5%)')
                break
            elif dist <= 0.01:
                score += 0.75
                details.append(f'近阻力 ${level:,.2f} (≤1%)')
                break

    for key in ['smc_internal_low_active', 'smc_swing_low_active']:
        level = smc_15.get(key, 0)
        if direction == 'long' and level < price:
            dist = (price - level) / price
            if dist <= 0.005:
                score += 1.5
                details.append(f'贴支撑 ${level:,.2f} (≤0.5%)')
                break
            elif dist <= 0.01:
                score += 0.75
                details.append(f'近支撑 ${level:,.2f} (≤1%)')
                break

    # 区域判断
    if direction == 'short':
        zone = smc_15.get('premium_hi', 0)
        if zone and price >= zone:
            score += 0.5
            details.append('在溢价区(做空有利)')
        eq_hi = smc_15.get('equilibrium_hi', 0)
        if eq_hi and price >= eq_hi:
            score += 0.25
            details.append('均衡区上方')
    else:
        zone = smc_15.get('discount_lo', 0)
        if zone and price <= zone:
            score += 0.5
            details.append('在折扣区(做多有利)')
        eq_lo = smc_15.get('equilibrium_lo', 0)
        if eq_lo and price <= eq_lo:
            score += 0.25
            details.append('均衡区下方')

    return min(3, score), details

# ============== 主扫描 ==============
def scan_single(sym):
    name = {'BTCUSDT': 'BTC', 'ETHUSDT': 'ETH', 'SOLUSDT': 'SOL'}[sym]

    # 拉数据
    tick = okx_ticker(sym)
    if not tick:
        return None
    price = tick['price']

    c15 = okx_15m(sym, 60)
    if not c15:
        return None

    # SMC 15m + 1H + 4H (用 indicators 命令)
    smc_15_raw = subprocess.run(
        f'python "{MOBIUS}" indicators --exchange bybit --market perp '
        f'--symbol {sym} --interval 15m --format compact 2>&1',
        shell=True, capture_output=True, text=True, encoding='utf-8').stdout
    smc_15 = parse_smc(smc_15_raw)

    smc_1h_raw = subprocess.run(
        f'python "{MOBIUS}" indicators --exchange bybit --market perp '
        f'--symbol {sym} --interval 1h --format compact 2>&1',
        shell=True, capture_output=True, text=True, encoding='utf-8').stdout
    smc_1h = parse_smc(smc_1h_raw)

    smc_4h_raw = subprocess.run(
        f'python "{MOBIUS}" indicators --exchange bybit --market perp '
        f'--symbol {sym} --interval 4h --format compact 2>&1',
        shell=True, capture_output=True, text=True, encoding='utf-8').stdout
    smc_4h = parse_smc(smc_4h_raw)

    # 方向判断 — 15m结构定方向
    sw_15 = int(smc_15.get('smc_swing_trend', 0))
    int_15 = int(smc_15.get('smc_internal_trend', 0))
    sw_1h = int(smc_1h.get('smc_swing_trend', 0))
    sw_4h = int(smc_4h.get('smc_swing_trend', 0))

    if sw_15 == -1 and int_15 == -1:
        direction = 'short'
        struct_base = 2.5
    elif sw_15 == 1 and int_15 == 1:
        direction = 'long'
        struct_base = 2.5
    elif sw_15 == -1:
        direction = 'short'
        struct_base = 1.5
    elif sw_15 == 1:
        direction = 'long'
        struct_base = 1.5
    else:
        direction = '-'
        struct_base = 0

    if direction == '-':
        return {'sym': name, 'price': price, 'dir': '-', 'score': 0, 'verdict': 'NO SIGNAL',
                'struct': 0, 'struct_detail': '15m方向不明',
                'position': 0, 'pos_detail': '-', 'candle': 0, 'candle_detail': '-',
                'volume': 0, 'volume_detail': '-', 'trigger': 0, 'trigger_detail': '-',
                'kdj': None, 'kdj_blocked': False, 'kdj_block_reason': '',
                'sweep': False, 'sweep_detail': '',
                'trend_mode': False, 'counter_trend': False,
                'smc_15': {}, 'smc_1h': {}, 'smc_4h': {}}

    # 1H 同向
    if (direction == 'short' and sw_1h == -1) or (direction == 'long' and sw_1h == 1):
        struct_base += 0.5

    # 逆大势检测
    counter_trend = ((direction == 'long' and sw_4h == -1) or
                     (direction == 'short' and sw_4h == 1))

    # KDJ 极端值硬锁
    kdj = calc_kdj(c15, n=9)
    kdj_blocked, kdj_block_reason = kdj_lock(kdj, direction)

    # 流动性扫荡
    sweep_detected, sweep_score, sweep_detail = detect_liquidity_sweep(c15, direction)

    struct_detail = f'15m:{"双空" if (sw_15==-1 and int_15==-1) else ("双多" if (sw_15==1 and int_15==1) else "偏"+direction)} 1H:{"同向" if struct_base>1.5 else "冲突"}'
    if counter_trend:
        struct_detail += ' ⚠️逆4H'

    # 结构分
    struct_score = min(3, struct_base)

    # 量价双方向：衰竭信号独立于结构方向
    v_score, v_details = volume_quick(c15, direction)
    opp_dir = 'long' if direction == 'short' else 'short'
    v_score_opp, v_details_opp = volume_quick(c15, opp_dir)

    # 关键位置（双向）
    pos_score, pos_details = near_key_level(price, smc_15, smc_1h, c15, direction)
    pos_score_opp, pos_details_opp = near_key_level(price, smc_15, smc_1h, c15, opp_dir)

    # K线（双向）
    c_score, c_details = candle_signal(c15, direction)
    c_score_opp, c_details_opp = candle_signal(c15, opp_dir)

    # 三重确认：量比≥65% 或 J值极端 或 K线确认，任一达标即可
    sell_vol = sum(c[5] for c in c15[-15:] if c[4] < c[1])
    buy_vol = sum(c[5] for c in c15[-15:] if c[4] > c[1])
    total_v = sell_vol + buy_vol
    sell_ratio = sell_vol / total_v if total_v > 0 else 0.5
    buy_ratio = buy_vol / total_v if total_v > 0 else 0.5

    j_val = kdj['j'] if kdj else 0
    vol_ok = (direction == 'short' and sell_ratio >= 0.65) or (direction == 'long' and buy_ratio >= 0.65)
    kdj_ok = (direction == 'short' and j_val > 100) or (direction == 'long' and j_val < 0)

    if vol_ok or kdj_ok:
        if c_score < 1.0:
            boost = 0
            if vol_ok: boost += 0.5
            if kdj_ok: boost += 0.5
            c_score = max(c_score, 0.5 + boost)
            confirm_parts = []
            if vol_ok: confirm_parts.append(f'量比{sell_ratio:.0%}' if direction == 'short' else f'量比{buy_ratio:.0%}')
            if kdj_ok: confirm_parts.append(f'J={j_val:.0f}极端')
            c_details = ' | '.join(confirm_parts) + '(替K线) | ' + c_details

    # 衰竭覆盖：反向量价+位置+K线强于结构方向 → 翻方向
    opp_power = v_score_opp + pos_score_opp * 0.5 + c_score_opp * 0.5
    this_power = v_score + pos_score * 0.5 + c_score * 0.5
    direction_flipped = False

    if opp_power > this_power + 1.0 and struct_score < 3.0:
        direction = opp_dir
        direction_flipped = True
        v_score, v_details = v_score_opp, v_details_opp
        pos_score, pos_details = pos_score_opp, pos_details_opp
        c_score, c_details = c_score_opp, c_details_opp
        # 重算结构方向
        if opp_dir == 'short':
            if sw_15 == -1 and int_15 == -1:
                struct_base = 2.5
            elif sw_15 == -1:
                struct_base = 1.5
            else:
                struct_base = 1.0
        else:
            if sw_15 == 1 and int_15 == 1:
                struct_base = 2.5
            elif sw_15 == 1:
                struct_base = 1.5
            else:
                struct_base = 1.0
        struct_score = min(3, struct_base)
        counter_trend = ((direction == 'long' and sw_4h == -1) or
                         (direction == 'short' and sw_4h == 1))
        struct_detail = f'15m:衰竭覆盖→{opp_dir} 原:{"双空" if (sw_15==-1 and int_15==-1) else ("双多" if (sw_15==1 and int_15==1) else "偏"+opp_dir)}'

    # ⑤ 反转触发 — V形 + 关键位拒绝（提前入场）
    vpat_name, vpat_score = detect_v_reversal(c15)
    trigger_score = 0
    trigger_details = []

    if vpat_name:
        trigger_score += vpat_score
        trigger_details.append(f'{vpat_name}(+{vpat_score})')

    # 关键位拒绝：位置分≥1.5 + K线拒绝 → 加速入场
    if pos_score >= 1.0 and c_score >= 0.75:
        trigger_score += 1.0
        trigger_details.append('关键位拒绝(提前入场)')
    elif pos_score >= 0.5 and c_score >= 1.0:
        trigger_score += 0.75
        trigger_details.append('近关键位+弱拒绝')

    trigger_score = min(2, trigger_score)
    if not trigger_details:
        trigger_details.append('-')

    # 流动性扫荡加分
    if sweep_detected:
        trigger_score += 0.5
        trigger_details.append(f'流动性扫荡(+0.5): {sweep_detail}')

    # 趋势模式
    sw_d = int(smc_4h.get('smc_swing_trend', 0))
    trend_mode = (sw_4h == sw_1h == sw_15 and sw_15 != 0 and
                  (sw_d == sw_4h or sw_d == 0))

    total = struct_score + v_score + pos_score + c_score + trigger_score

    # 判决（KDJ硬锁 > 量价分数）
    if kdj_blocked:
        verdict = 'NO'
        kdj_verdict = f'⛔ {kdj_block_reason}'
    elif total >= 7:
        verdict = 'TRADE'
    elif total >= 5:
        verdict = 'SCALP'
    elif total >= 3:
        verdict = 'WEAK'
    else:
        verdict = 'NO'

    return {
        'sym': name,
        'price': price,
        'dir': direction,
        'score': round(total, 1),
        'verdict': verdict,
        'trend_mode': trend_mode,
        'struct': struct_score,
        'struct_detail': struct_detail,
        'position': pos_score,
        'pos_detail': ', '.join(pos_details) if pos_details else '未到关键位',
        'candle': c_score,
        'candle_detail': c_details,
        'volume': v_score,
        'volume_detail': v_details,
        'trigger': trigger_score,
        'trigger_detail': ', '.join(trigger_details) if trigger_details else '-',
        'kdj': kdj,
        'kdj_blocked': kdj_blocked,
        'kdj_block_reason': kdj_block_reason,
        'sweep': sweep_detected,
        'sweep_detail': sweep_detail,
        'candles': c15,
        'smc_15': smc_15,
        'smc_1h': smc_1h,
        'smc_4h': smc_4h,
        'counter_trend': counter_trend,
    }


# ============== ATR ==============
def calc_atr(candles, period=14):
    """ATR 平均真实波幅 — 动态止损基准"""
    if len(candles) < period + 1:
        return 0
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i][2], candles[i][3], candles[i-1][4]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    # EMA of last 'period' TRs
    atr = sum(trs[-period:]) / period
    return atr


# ============== 生成方案（双模式 + ATR动态SL） ==============
def make_plan(r, candles=None):
    """SL = max(1.0×ATR%, 0.8%)。波动大时自动放宽，波动小时不太紧。"""
    if not r or r['verdict'] not in ('TRADE', 'SCALP'):
        return None

    price = r['price']
    direction = r['dir']
    sym = r['sym']
    smc = r['smc_15']
    trend = r.get('trend_mode', False)

    # ATR 动态计算
    atr = calc_atr(candles) if candles else 0
    atr_pct = (atr / price * 100) if atr > 0 and price > 0 else 0

    if trend:
        sl_pct = max(atr_pct * 1.5, 1.2)
        sl_level = price * (1 + sl_pct / 100) if direction == 'short' else price * (1 - sl_pct / 100)
        if direction == 'short':
            tp_level = smc.get('smc_swing_low_active', price * 0.97)
            if tp_level >= price * 0.99:
                tp_level = price * 0.975
        else:
            tp_level = smc.get('smc_swing_high_active', price * 1.03)
            if tp_level <= price * 1.01:
                tp_level = price * 1.025
        trail = True
    else:
        sl_pct = max(atr_pct * 1.0, 0.8)
        sl_level = price * (1 + sl_pct / 100) if direction == 'short' else price * (1 - sl_pct / 100)

        # 双TP：50%仓位吃1.5xATR，50%仓位吃2xATR
        tp1_dist = atr * 1.5 if atr > 0 else price * sl_pct / 100 * 1.2
        tp2_dist = atr * 2.0 if atr > 0 else price * sl_pct / 100 * 1.6
        if direction == 'short':
            tp_level = price - tp1_dist
            tp2_level = price - tp2_dist
        else:
            tp_level = price + tp1_dist
            tp2_level = price + tp2_dist
        trail = False

    tp_pct = abs(tp_level - price) / price * 100
    sl_pct_actual = abs(sl_level - price) / price * 100
    rr = round(tp_pct / max(sl_pct_actual, 0.001), 2)

    # R:R 底线 1:1.2（快进快出）
    if rr < 1.2:
        tp_level = price * (1 + sl_pct_actual * 1.2 / 100) if direction == 'long' else price * (1 - sl_pct_actual * 1.2 / 100)
        tp_pct = sl_pct_actual * 1.2 / 100 * 100
        rr = 1.2

    margin = 3 if r['verdict'] == 'TRADE' else 2
    risk_u = round(margin * 10 * sl_pct_actual / 100, 2)
    reward_u = round(margin * 10 * tp_pct / 100, 2)

    return {
        'sym': sym, 'direction': direction,
        'entry': round(price, 1) if sym == 'SOL' else round(price, 0),
        'sl': round(sl_level, 1) if sym == 'SOL' else round(sl_level, 0),
        'tp': round(tp_level, 1) if sym == 'SOL' else round(tp_level, 0),
        'tp2': round(tp2_level, 1) if 'tp2_level' in dir() else None,
        'margin': margin, 'leverage': 10,
        'risk_u': risk_u, 'reward_u': reward_u,
        'rr': round(rr, 2), 'score': r['score'],
        'trend': trend, 'trail': trail,
    }


# ============== MAIN ==============
if __name__ == '__main__':
    now = datetime.now(BJT).strftime('%m-%d %H:%M')
    print(f"\n{'='*55}")
    print(f"  ⚡ 快扫 v1.0 — 1H+15m 双周期  |  {now} 北京时间")
    print(f"{'='*55}")

    results = []
    for sym in SYMBOLS:
        print(f"  [{sym[:3]}] 扫...", end=' ')
        r = scan_single(sym)
        if r:
            results.append(r)
            print(f"{r['score']}/9 {r['verdict']}")
        else:
            print('FAIL')

    # 排序
    results.sort(key=lambda x: x['score'], reverse=True)

    print(f"\n{'─'*55}")
    print(f"  {'排名':<4} {'币':<5} {'价格':<12} {'方向':<6} {'得分':<6} {'判决'}")
    print(f"{'─'*55}")
    for i, r in enumerate(results):
        emoji = '🥇' if i == 0 else ('🥈' if i == 1 else '🥉')
        print(f"  {emoji:<4} {r['sym']:<5} ${r['price']:<11,.2f} {r['dir']:<6} {r['score']:<5.1f}  {r['verdict']}")

    best = results[0] if results else None

    if best:
        print(f"\n{'─'*55}")
        print(f"  🎯 BEST: {best['sym']} | {best['dir'].upper()} | {best['score']}/9 | {best['verdict']}")
        print(f"{'─'*55}")
        print(f"  ①结构  {best['struct']:.1f}/3  — {best['struct_detail']}")
        print(f"  ②位置  {best['position']:.1f}/3  — {best['pos_detail']}")
        print(f"  ③K线   {best['candle']:.1f}/3  — {best['candle_detail']}")
        print(f"  ④量价  {best['volume']:.1f}/3  — {best['volume_detail']}")
        print(f"  ⑤反转  +{best.get('trigger', 0):.1f}/2  — {best.get('trigger_detail', '-')}")
        # KDJ + 流动性
        if best.get('kdj_blocked'):
            print(f"  ⛔ KDJ硬锁! {best.get('kdj_block_reason', '')}")
        elif best.get('kdj'):
            kdj = best['kdj']
            print(f"  ⑥KDJ   J={kdj['j']:.0f} K={kdj['k']:.0f} D={kdj['d']:.0f} ({kdj['zone']})")
        sweep = f"🔍 {best['sweep_detail']}" if best.get('sweep') else '未扫荡'
        print(f"  ⑦流动性 {sweep}")

        # 趋势模式标识
        if best.get('trend_mode'):
            print(f"  🔥 趋势模式 — 日+4H+1H 三同向，追踪止损吃波段")
        # 逆大势处理
        if best.get('counter_trend'):
            if best['score'] >= 7:
                print(f"  ⚠️  逆4H但分高({best['score']:.0f})→全仓做")
            else:
                print(f"  ⚠️  逆4H且分低→仓位减半")
        plan = make_plan(best, best.get('candles', [])) if best['verdict'] not in ('NO SIGNAL', 'WEAK') else None
        if plan:
            if best.get('counter_trend') and best['score'] < 7:
                plan['margin'] = max(1, plan['margin'] // 2)
                plan['risk_u'] = round(plan['margin'] * 10 * abs(plan['sl']/plan['entry'] - 1), 2)
                plan['reward_u'] = round(plan['margin'] * 10 * abs(plan['tp']/plan['entry'] - 1), 2)
            print(f"\n  📋 方案")
            print(f"  {'─'*45}")
            print(f"  入场  ${plan['entry']:,.2f}")
            print(f"  SL    ${plan['sl']:,.2f}  ({plan['sl']/plan['entry']-1:+.2%})")
            print(f"  TP    ${plan['tp']:,.2f}")
            print(f"  仓位  {plan['margin']}U {plan['leverage']}x {'🔁追踪SL' if plan.get('trail') else '⚡5K走'}")
            print(f"  风险  ±{plan['risk_u']:.2f}U  |  回报  ~{plan['reward_u']:.2f}U  |  R:R 1:{plan['rr']}")
            if plan.get('trail'):
                print(f"  浮盈≥5U→SL保本  ≥10U→锁50%利润")
        else:
            print(f"\n  ⚠️  分数不够，不出方案")

    print(f"\n  🟢 快扫阈值: ≥7全仓3U | ≥5头皮2U | <5不做")
    print(f"     出场: 0.5R保本 | 1R追踪 | 10根不赚砍")
    print()
