import json
import time
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

BASE    = "https://fapi.binance.com"
KST     = timezone(timedelta(hours=9))
SYMBOLS = ["ETHUSDT", "BTCUSDT"]

# ✅ 여기에 본인 값 입력
TELEGRAM_TOKEN   = "bot_8729423940:AAEtvv2YgpOwMaCug-HysUM0qzQikILhPe8"
TELEGRAM_CHAT_ID = "-1003792921380"


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
    t   = utc_ms_to_kst(int(eth[0])).strftime("%Y-%m-%d %H:%M KST")
    eo, eh, el, ec = eth[1], eth[2], eth[3], eth[4]
    ev  = float(eth[5])
    bo, bh, bl, bc = btc[1], btc[2], btc[3], btc[4]
    bv  = float(btc[5])

    # 등락 방향 이모지
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
# 대기
# ────────────────────────────────────────
def wait_until_next_15m():
    now = datetime.now(tz=KST)
    minutes_to_wait = 15 - (now.minute % 15)
    seconds_to_wait = minutes_to_wait * 60 - now.second + 3  # 3초 여유
    print(f"  → 다음 마감까지 {minutes_to_wait}분 대기중...")
    time.sleep(seconds_to_wait)


# ────────────────────────────────────────
# 메인
# ────────────────────────────────────────
def main():
    print("=== ETHUSDT 실시간 감시 시작 ===")
    send_telegram("✅ ETHUSDT 모니터링 봇 시작!")

    last_candle_time = None

    while True:
        try:
            wait_until_next_15m()

            eth_kl = fetch_klines("ETHUSDT", "15m", 2)
            btc_kl = fetch_klines("BTCUSDT", "15m", 2)

            eth_closed = eth_kl[-2]
            btc_closed = btc_kl[-2]

            candle_time = utc_ms_to_kst(int(eth_closed[0]))

            if candle_time == last_candle_time:
                continue
            last_candle_time = candle_time

            # 펀딩비 (매 정각)
            funding_line = ""
            if candle_time.minute == 0:
                try:
                    fr = fetch_funding("ETHUSDT")
                    if fr is not None:
                        funding_line = f"Funding: {fr:+.4f}%"
                except:
                    pass

            # 텔레그램 전송
            msg = build_message(eth_closed, btc_closed, funding_line)
            send_telegram(msg)
            print(f"[{candle_time.strftime('%H:%M')}] 전송 완료")

        except KeyboardInterrupt:
            print("\n감시 종료")
            send_telegram("🛑 모니터링 봇 종료")
            break
        except Exception as e:
            print(f"오류: {e} — 30초 후 재시도")
            time.sleep(30)

if __name__ == "__main__":
    main()
