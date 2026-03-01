import json
import os
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

BASE = "https://fapi.binance.com"
KST  = timezone(timedelta(hours=9))

# GitHub Secrets에서 자동으로 읽어옴
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


# ────────────────────────────────────────
# 텔레그램 전송
# ────────────────────────────────────────
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


# ────────────────────────────────────────
# 바이낸스 데이터
# ────────────────────────────────────────
def fetch_klines(symbol, interval="15m", limit=2):
    params = urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    url = f"{BASE}/fapi/v1/klines?{params}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_funding(symbol):
    params = urlencode({"symbol": symbol, "limit": 1})
    url = f"{BASE}/fapi/v1/fundingRate?{params}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if data:
            return float(data[-1]["fundingRate"]) * 100
        return None

def utc_ms_to_kst(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(KST)


# ────────────────────────────────────────
# 메시지 포맷
# ────────────────────────────────────────
def build_message(eth, btc, funding_line):
    t  = utc_ms_to_kst(int(eth[0])).strftime("%Y-%m-%d %H:%M KST")
    eo, eh, el, ec = eth[1], eth[2], eth[3], eth[4]
    ev = float(eth[5])
    bo, bh, bl, bc = btc[1], btc[2], btc[3], btc[4]
    bv = float(btc[5])

    eth_arrow = "🟢" if float(ec) >= float(eo) else "🔴"
    btc_arrow = "🟢" if float(bc) >= float(bo) else "🔴"

    msg = (
        f"⏰ <b>15분봉 마감</b> | {t}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{eth_arrow} <b>ETHUSDT</b>\n"
        f"  O={eo}  H={eh}\n"
        f"  L={el}  C={ec}\n"
        f"  V={ev:,.0f}\n"
        f"\n"
        f"{btc_arrow} <b>BTCUSDT</b>\n"
        f"  O={bo}  H={bh}\n"
        f"  L={bl}  C={bc}\n"
        f"  V={bv:,.0f}\n"
    )

    if funding_line:
        msg += f"━━━━━━━━━━━━━━━━\n💰 {funding_line}\n"

    return msg


# ────────────────────────────────────────
# 메인 (1회 실행 구조)
# ────────────────────────────────────────
def main():
    print("=== ETHUSDT 15분봉 감시 실행 ===")

    eth_kl = fetch_klines("ETHUSDT", "15m", 2)
    btc_kl = fetch_klines("BTCUSDT", "15m", 2)

    eth_closed = eth_kl[-2]
    btc_closed = btc_kl[-2]

    candle_time = utc_ms_to_kst(int(eth_closed[0]))

    # 펀딩비 (매 정각에만)
    funding_line = ""
    if candle_time.minute == 0:
        try:
            fr = fetch_funding("ETHUSDT")
            if fr is not None:
                funding_line = f"Funding: {fr:+.4f}%"
        except:
            pass

    msg = build_message(eth_closed, btc_closed, funding_line)
    send_telegram(msg)
    print(f"[{candle_time.strftime('%H:%M')}] 전송 완료")

if __name__ == "__main__":
    main()
