import json
import os
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

# 바이낸스 공개 데이터 미러 (IP 차단 없음)
BASE_DATA  = "https://data-api.binance.vision"  # 캔들 데이터
BASE_FAPI  = "https://fapi.binance.com"          # 펀딩비 (막히면 OKX 대체)
KST        = timezone(timedelta(hours=9))

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ════════════════════════════════════════
# 전략 v3 OB 레벨
# ════════════════════════════════════════
BEAR_OB = [
    ("Bear OB 2차", 2008, 2036, True),
    ("Bear OB 3차", 2073, 2100, True),
    ("Bear OB 4차", 2149, 2150, True),
]
BULL_OB = [
    ("Bull OB 1차", 1921, 1925, True),
    ("Bull OB 2차", 1884, 1892, True),
    ("Bull OB 3차", 1845, 1851, True),
    ("Bull OB 4차", 1796, 1800, True),
]

FUNDING_EXTREME_LONG  = -0.05
FUNDING_EXTREME_SHORT =  0.05
ALLOWED_HOURS = [17, 18, 22, 23, 0, 5, 6]


# ════════════════════════════════════════
# 텔레그램
# ════════════════════════════════════════
def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")


# ════════════════════════════════════════
# 바이낸스 데이터
# ════════════════════════════════════════
def fetch_klines(symbol, interval="15m", limit=3):
    """캔들 데이터 - binance.vision 미러 사용"""
    params = urlencode({
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    })
    url = f"{BASE_DATA}/api/v3/klines?{params}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_klines_futures(symbol, interval="15m", limit=3):
    """선물 캔들 데이터"""
    params = urlencode({
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    })
    url = f"{BASE_DATA}/fapi/v1/klines?{params}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_funding(symbol):
    """펀딩비 - fapi 시도 → 실패 시 None"""
    try:
        params = urlencode({"symbol": symbol, "limit": 1})
        url = f"{BASE_FAPI}/fapi/v1/fundingRate?{params}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data:
                return float(data[-1]["fundingRate"]) * 100
    except:
        pass
    return None

def utc_ms_to_kst(ms):
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).astimezone(KST)


# ════════════════════════════════════════
# OB 분석
# ════════════════════════════════════════
def check_ob(price):
    alerts = []
    for name, low, high, valid in BEAR_OB:
        if valid and low <= price <= high:
            alerts.append(f"🔴 <b>{name} 진입!</b> ({low}~{high})\n   → 숏 포착 구간 주시")
    for name, low, high, valid in BULL_OB:
        if valid and low <= price <= high:
            alerts.append(f"🟢 <b>{name} 진입!</b> ({low}~{high})\n   → 롱 포착 구간 주시")
    return alerts

def get_nearest_ob(price):
    above, below = [], []
    for name, low, high, valid in BEAR_OB:
        if valid:
            if low > price:
                above.append((low - price, f"🔴 {name} {low}~{high}"))
            elif low <= price <= high:
                above.append((0, f"🔴 {name} {low}~{high} ← 진입중"))
    for name, low, high, valid in BULL_OB:
        if valid:
            if high < price:
                below.append((price - high, f"🟢 {name} {low}~{high}"))
            elif low <= price <= high:
                below.append((0, f"🟢 {name} {low}~{high} ← 진입중"))
    above.sort(key=lambda x: x[0])
    below.sort(key=lambda x: x[0])
    result = []
    if above:
        result.append(f"위 저항: {above[0][1]}")
    if below:
        result.append(f"아래 지지: {below[0][1]}")
    return result


# ════════════════════════════════════════
# 시간대
# ════════════════════════════════════════
def check_time_filter(hour):
    return "✅ 진입 허용" if hour in ALLOWED_HOURS else "❌ 금지 시간대"

def check_session(hour):
    if hour in [17, 18]:   return "🇬🇧 런던 오픈"
    if hour in [22, 23, 0]: return "🇺🇸 뉴욕 오픈"
    if hour in [5, 6]:      return "🇺🇸 뉴욕 마감"
    if 9 <= hour <= 15:     return "😴 아시아 저변동"
    return "🌐 일반"

def check_session_alert(minute, hour):
    if minute != 0: return None
    if hour == 17:  return "🇬🇧 <b>런던 오픈!</b> 변동성 시작\n진입 허용 시간대"
    if hour == 22:  return "🇺🇸 <b>뉴욕 오픈!</b> 최대 변동성\n핵심 진입 시간대"
    if hour == 5:   return "🇺🇸 <b>뉴욕 마감!</b> 포지션 정리 구간"
    if hour == 9:   return "😴 <b>아시아장 시작</b>\n저변동성 / 신규 진입 자제"
    return None


# ════════════════════════════════════════
# 캔들 변화율
# ════════════════════════════════════════
def candle_change(o, c):
    return ((float(c) - float(o)) / float(o)) * 100


# ════════════════════════════════════════
# 메시지 빌더
# ════════════════════════════════════════
def build_15m_message(eth, btc, funding, now_kst):
    t   = utc_ms_to_kst(eth[0]).strftime("%H:%M KST")
    eo, eh, el, ec = eth[1], eth[2], eth[3], eth[4]
    ev  = float(eth[5])
    bo, bh, bl, bc = btc[1], btc[2], btc[3], btc[4]

    price     = float(ec)
    eth_chg   = candle_change(eo, ec)
    btc_chg   = candle_change(bo, bc)
    eth_arrow = "🟢" if eth_chg >= 0 else "🔴"
    btc_arrow = "🟢" if btc_chg >= 0 else "🔴"

    hour      = now_kst.hour
    time_ok   = check_time_filter(hour)
    session   = check_session(hour)
    ob_alerts = check_ob(price)
    nearest   = get_nearest_ob(price)

    msg = (
        f"⏰ <b>15분봉</b> | {t} | {session}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{eth_arrow} <b>ETH</b> {ec}  ({eth_chg:+.2f}%)\n"
        f"  H={eh}  L={el}  V={ev:,.0f}\n"
        f"{btc_arrow} <b>BTC</b> {bc}  ({btc_chg:+.2f}%)\n"
        f"━━━━━━━━━━━━━━━━\n"
    )
    for ob in nearest:
        msg += f"📌 {ob}\n"
    msg += f"⏱ {time_ok}\n"

    if funding is not None:
        f_emoji = "🔥" if abs(funding) >= 0.05 else "💰"
        msg += f"{f_emoji} Funding: {funding:+.4f}%\n"

    if ob_alerts:
        msg += "━━━━━━━━━━━━━━━━\n"
        for alert in ob_alerts:
            msg += f"{alert}\n"

    return msg, ob_alerts

def build_1h_message(eth, btc):
    t  = utc_ms_to_kst(eth[0]).strftime("%m/%d %H:%M KST")
    eo, eh, el, ec = eth[1], eth[2], eth[3], eth[4]
    bo, bh, bl, bc = btc[1], btc[2], btc[3], btc[4]
    eth_chg = candle_change(eo, ec)
    btc_chg = candle_change(bo, bc)
    eth_arrow = "🟢" if eth_chg >= 0 else "🔴"
    btc_arrow = "🟢" if btc_chg >= 0 else "🔴"
    return (
        f"📊 <b>1시간봉 마감</b> | {t}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{eth_arrow} <b>ETH</b> {ec}  ({eth_chg:+.2f}%)\n"
        f"  H={eh}  L={el}\n"
        f"{btc_arrow} <b>BTC</b> {bc}  ({btc_chg:+.2f}%)\n"
    )

def build_4h_message(eth, btc):
    t  = utc_ms_to_kst(eth[0]).strftime("%m/%d %H:%M KST")
    eo, eh, el, ec = eth[1], eth[2], eth[3], eth[4]
    bo, bh, bl, bc = btc[1], btc[2], btc[3], btc[4]
    eth_chg = candle_change(eo, ec)
    btc_chg = candle_change(bo, bc)
    eth_arrow = "🟢" if eth_chg >= 0 else "🔴"
    btc_arrow = "🟢" if btc_chg >= 0 else "🔴"
    nearest = get_nearest_ob(float(ec))
    msg = (
        f"📈 <b>4시간봉 마감</b> | {t}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{eth_arrow} <b>ETH</b> {ec}  ({eth_chg:+.2f}%)\n"
        f"  H={eh}  L={el}\n"
        f"{btc_arrow} <b>BTC</b> {bc}  ({btc_chg:+.2f}%)\n"
        f"━━━━━━━━━━━━━━━━\n"
    )
    for ob in nearest:
        msg += f"📌 {ob}\n"
    return msg

def check_funding_alert(funding):
    if funding is None: return None
    if funding <= FUNDING_EXTREME_LONG:
        return (
            f"🚨 <b>펀딩비 극단 알림!</b>\n"
            f"Funding: {funding:+.4f}%\n"
            f"숏 과열 → 역방향 🟢 롱 시그널\n"
            f"(단독 진입 금지 / OB 확인 필수)"
        )
    if funding >= FUNDING_EXTREME_SHORT:
        return (
            f"🚨 <b>펀딩비 극단 알림!</b>\n"
            f"Funding: {funding:+.4f}%\n"
            f"롱 과열 → 역방향 🔴 숏 시그널\n"
            f"(단독 진입 금지 / OB 확인 필수)"
        )
    return None


# ════════════════════════════════════════
# 메인
# ════════════════════════════════════════
def main():
    print("=== ETHUSDT 풀기능 감시 실행 (바이낸스) ===")

    now_kst = datetime.now(tz=KST)
    minute  = now_kst.minute
    hour    = now_kst.hour

    # 캔들 수신 (선물 기준)
    try:
        eth_15m = fetch_klines_futures("ETHUSDT", "15m", 3)
        btc_15m = fetch_klines_futures("BTCUSDT", "15m", 3)
    except:
        # 선물 실패 시 현물 미러로 폴백
        eth_15m = fetch_klines("ETHUSDT", "15m", 3)
        btc_15m = fetch_klines("BTCUSDT", "15m", 3)

    eth_closed = eth_15m[-2]
    btc_closed = btc_15m[-2]

    # 펀딩비
    funding = None
    if minute == 0:
        funding = fetch_funding("ETHUSDT")

    # ① 15분봉 메시지
    msg_15m, ob_alerts = build_15m_message(eth_closed, btc_closed, funding, now_kst)
    send_telegram(msg_15m)
    print(f"[{now_kst.strftime('%H:%M')}] 15분봉 전송 완료")

    # ② OB 진입 경보
    if ob_alerts:
        alert_msg = "⚠️ <b>OB 구간 진입 경보!</b>\n━━━━━━━━━━━━━━━━\n"
        for a in ob_alerts:
            alert_msg += f"{a}\n"
        alert_msg += "\n전략 조건 확인 후 진입 판단하세요"
        send_telegram(alert_msg)
        print("OB 알림 전송")

    # ③ 1시간봉 (매 정각)
    if minute == 0:
        try:
            eth_1h = fetch_klines_futures("ETHUSDT", "1h", 3)
            btc_1h = fetch_klines_futures("BTCUSDT", "1h", 3)
        except:
            eth_1h = fetch_klines("ETHUSDT", "1h", 3)
            btc_1h = fetch_klines("BTCUSDT", "1h", 3)
        msg_1h = build_1h_message(eth_1h[-2], btc_1h[-2])
        send_telegram(msg_1h)
        print("1시간봉 전송 완료")

    # ④ 4시간봉 (4의 배수 정각)
    if minute == 0 and hour % 4 == 0:
        try:
            eth_4h = fetch_klines_futures("ETHUSDT", "4h", 3)
            btc_4h = fetch_klines_futures("BTCUSDT", "4h", 3)
        except:
            eth_4h = fetch_klines("ETHUSDT", "4h", 3)
            btc_4h = fetch_klines("BTCUSDT", "4h", 3)
        msg_4h = build_4h_message(eth_4h[-2], btc_4h[-2])
        send_telegram(msg_4h)
        print("4시간봉 전송 완료")

    # ⑤ 펀딩비 극단 알림
    if funding is not None:
        f_alert = check_funding_alert(funding)
        if f_alert:
            send_telegram(f_alert)
            print("펀딩비 극단 알림 전송")

    # ⑥ 세션 오픈 알림
    session_alert = check_session_alert(minute, hour)
    if session_alert:
        send_telegram(session_alert)
        print("세션 알림 전송")

if __name__ == "__main__":
    main()
