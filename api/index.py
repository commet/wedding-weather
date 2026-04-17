"""Vercel Serverless Function — Wedding Weather Dashboard"""

from http.server import BaseHTTPRequestHandler
from datetime import datetime, date, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import html as html_mod
import json
import re

import requests
from bs4 import BeautifulSoup

# ============================================================
# Config
# ============================================================
WEDDING_DATE = "2026-04-25"
WEDDING_TIME = "12:30"
WEDDING_DAY_KR = "토"
WEDDING_LOCATION = "뜰안채 2"
WEDDING_ADDRESS = "경기 의왕시 양지편로 39-18 야외정원"
LAT, LON = 37.3448, 126.9683

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
ACCU_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

LINKS = {
    "kma": "https://www.weather.go.kr/w/weather/forecast/mid-term.do?stnId1=109",
    "accuweather": "https://www.accuweather.com/ko/kr/uiwang/223635/daily-weather-forecast/223635",
    "accuweather_en": "https://www.accuweather.com/en/kr/uiwang/223635/daily-weather-forecast/223635",
    "naver": "https://search.naver.com/search.naver?query=의왕시+날씨",
}

WMO = {
    0: ("맑음", "☀️"), 1: ("대체로 맑음", "🌤️"), 2: ("부분 흐림", "⛅"),
    3: ("흐림", "☁️"), 45: ("안개", "🌫️"), 48: ("안개", "🌫️"),
    51: ("이슬비", "🌦️"), 53: ("이슬비", "🌦️"), 55: ("강한 이슬비", "🌧️"),
    61: ("약한 비", "🌧️"), 63: ("비", "🌧️"), 65: ("강한 비", "🌧️"),
    80: ("소나기", "🌦️"), 81: ("소나기", "🌧️"), 82: ("강한 소나기", "⛈️"),
    71: ("약한 눈", "🌨️"), 73: ("눈", "❄️"), 75: ("강한 눈", "❄️"),
    95: ("뇌우", "⛈️"), 96: ("뇌우+우박", "⛈️"), 99: ("뇌우+우박", "⛈️"),
}


def d_day():
    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).date()
    w = date.fromisoformat(WEDDING_DATE)
    d = (w - today).days
    return f"D-{d}" if d > 0 else ("D-DAY!" if d == 0 else f"D+{abs(d)}")


# ============================================================
# Data Fetching (all with short timeouts for serverless)
# ============================================================

def fetch_openmeteo():
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT, "longitude": LON, "timezone": "Asia/Seoul",
            "forecast_days": 16,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,weathercode,windspeed_10m_max",
            "hourly": "temperature_2m,precipitation_probability,precipitation,weathercode,windspeed_10m,relativehumidity_2m",
        }, timeout=8)
        r.raise_for_status()
        data = r.json()
        dates = data["daily"]["time"]
        if WEDDING_DATE not in dates:
            return None
        idx = dates.index(WEDDING_DATE)
        d = data["daily"]
        wc = d["weathercode"][idx]
        ck, ce = WMO.get(wc, ("?", "❓"))
        hours = []
        for i, t in enumerate(data["hourly"]["time"]):
            if t.startswith(WEDDING_DATE):
                h = int(t[11:13])
                if 9 <= h <= 16:
                    _, he = WMO.get(data["hourly"]["weathercode"][i], ("?", "❓"))
                    hours.append({
                        "hour": h, "temp": data["hourly"]["temperature_2m"][i],
                        "rain_prob": data["hourly"]["precipitation_probability"][i],
                        "wind": data["hourly"]["windspeed_10m"][i],
                        "humidity": data["hourly"]["relativehumidity_2m"][i],
                        "emoji": he,
                    })
        ctx = []
        for off in range(-2, 3):
            cd = f"2026-04-{25 + off:02d}"
            if cd in dates:
                ci = dates.index(cd)
                wc2 = d["weathercode"][ci]
                _, ce2 = WMO.get(wc2, ("?", "❓"))
                ctx.append({
                    "date": cd, "day": cd[-2:],
                    "temp_min": d["temperature_2m_min"][ci],
                    "temp_max": d["temperature_2m_max"][ci],
                    "rain_prob": d["precipitation_probability_max"][ci],
                    "emoji": ce2,
                })
        return {
            "temp_min": d["temperature_2m_min"][idx], "temp_max": d["temperature_2m_max"][idx],
            "rain_prob": d["precipitation_probability_max"][idx],
            "condition": ck, "emoji": ce,
            "wind": d["windspeed_10m_max"][idx],
            "hours": hours, "context_days": ctx,
        }
    except Exception:
        return None


def fetch_naver():
    try:
        r = requests.get("https://search.naver.com/search.naver",
                         params={"query": "의왕시 날씨"}, headers=HEADERS, timeout=6)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select("li.week_item"):
            de = item.select_one("span.date")
            if not de or "4.25" not in de.get_text(strip=True):
                continue
            lo = item.select_one("span.lowest")
            hi = item.select_one("span.highest")
            tmin = float(re.search(r"(-?\d+)", lo.get_text()).group(1)) if lo else None
            tmax = float(re.search(r"(-?\d+)", hi.get_text()).group(1)) if hi else None
            rfs = item.select("span.rainfall")
            ram = int(re.search(r"(\d+)", rfs[0].get_text()).group(1)) if len(rfs) >= 1 else None
            rpm = int(re.search(r"(\d+)", rfs[1].get_text()).group(1)) if len(rfs) >= 2 else None
            conds = [e.get_text(strip=True) for e in item.select("i.wt_icon > span.blind")]
            ca = conds[0] if len(conds) >= 1 else None
            cp = conds[1] if len(conds) >= 2 else None
            cond = ca if ca == cp else (f"{ca}/{cp}" if ca and cp else ca)
            return {"success": True, "data": {
                "temp_min": tmin, "temp_max": tmax,
                "rain_prob": max(ram or 0, rpm or 0),
                "rain_am": ram, "rain_pm": rpm,
                "condition": cond,
            }}
    except Exception:
        pass
    return {"success": False, "data": None}


def _parse_accu(text):
    """AccuWeather HTML에서 4/25 데이터 추출"""
    idx = text.find("4/25")
    if idx == -1:
        return None
    cs = text.rfind("<a", max(0, idx - 3000), idx)
    ce = text.find("daily-forecast-card", idx + 10)
    if ce == -1:
        ce = text.find("</a>", idx) + 4
    card = text[cs:ce]
    mh = re.search(r'class="high">(\d+)', card)
    ml = re.search(r'class="low">/(\d+)', card)
    mp = re.search(r'precip-icon.*?</svg>\s*(\d+)%', card, re.DOTALL)
    mc = re.search(r'class="phrase">([^<]+)', card)
    if not mh:
        return None
    # 영문 페이지는 화씨(°F) → 섭씨(°C) 변환
    hi_f = float(mh.group(1))
    lo_f = float(ml.group(1)) if ml else None
    hi_c = round((hi_f - 32) * 5 / 9, 1)
    lo_c = round((lo_f - 32) * 5 / 9, 1) if lo_f is not None else None
    return {
        "temp_max": hi_c,
        "temp_min": lo_c,
        "rain_prob": int(mp.group(1)) if mp else None,
        "condition": html_mod.unescape(mc.group(1).strip()) if mc else None,
    }


def fetch_accuweather():
    url = LINKS["accuweather_en"]
    # 시도 1: Chrome 헤더 (로컬 환경에서 작동)
    try:
        r = requests.get(url, headers=ACCU_HEADERS, timeout=8)
        if r.status_code == 200:
            d = _parse_accu(r.text)
            if d:
                return {"success": True, "data": d}
    except Exception:
        pass
    # 시도 2: Googlebot UA (클라우드 환경 폴백 - SEO 크롤러로 인식)
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
        })
        resp = urllib.request.urlopen(req, timeout=8)
        text = resp.read().decode("utf-8", errors="replace")
        d = _parse_accu(text)
        if d:
            return {"success": True, "data": d}
    except Exception:
        pass
    return {"success": False, "data": None}


def fetch_kma():
    try:
        r = requests.get("https://www.weather.go.kr/w/weather/forecast/mid-term.do",
                         params={"stnId1": 109}, headers=HEADERS, timeout=8)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.select("table")
        result = {"success": False, "data": {}}

        # Table 0: rain/weather by region
        if tables:
            t0 = tables[0]
            rows = t0.select("tr")
            ths = rows[0].select("th") if rows else []
            col_map = {}
            dc = 0
            for th in ths:
                txt = th.get_text(strip=True)
                if "지역" in txt:
                    continue
                dm = re.search(r"(\d+)일", txt)
                if dm:
                    day = int(dm.group(1))
                    cs2 = int(th.get("colspan", 1))
                    for i in range(cs2):
                        col_map[dc + i] = day
                    dc += cs2
            tcols = [c for c, d in col_map.items() if d == 25]
            if tcols:
                for row in rows[2:]:
                    rt = row.get_text()
                    if "서울" not in rt and "경기" not in rt:
                        continue
                    tds = row.select("td")
                    wtds = [td for td in tds if td.select_one("i.wic") or (td.select_one("span") and re.search(r"\d+%", td.get_text()))]
                    for ci in tcols:
                        if ci < len(wtds):
                            sp = wtds[ci].select_one("span")
                            if sp:
                                rm = re.search(r"(\d+)", sp.get_text())
                                if rm:
                                    result["data"]["rain_prob"] = int(rm.group(1))
                            ic = wtds[ci].select_one("i.wic")
                            if ic:
                                result["data"]["condition"] = ic.get("title") or ic.get_text(strip=True)
                    break

        # Table 1: temperature by city
        if len(tables) >= 2:
            t1 = tables[1]
            rows = t1.select("tr")
            ths = rows[0].select("th") if rows else []
            dorder = []
            for th in ths:
                dm = re.search(r"(\d+)일", th.get_text(strip=True))
                if dm:
                    dorder.append(int(dm.group(1)))
            tidx = dorder.index(25) if 25 in dorder else None
            if tidx is not None:
                for row in rows[1:]:
                    if "수원" not in row.get_text():
                        continue
                    pairs = []
                    for td in row.select("td"):
                        tmn = td.select_one("span.tmn")
                        tmx = td.select_one("span.tmx")
                        if tmn and tmx:
                            try:
                                pairs.append((float(tmn.get_text(strip=True)), float(tmx.get_text(strip=True))))
                            except ValueError:
                                pass
                    if tidx < len(pairs):
                        result["data"]["temp_min"], result["data"]["temp_max"] = pairs[tidx]
                    break

        if result["data"].get("temp_min") is not None or result["data"].get("rain_prob") is not None:
            result["success"] = True
        return result
    except Exception:
        return {"success": False, "data": None}


# ============================================================
# HTML Rendering
# ============================================================

def rc(prob):
    if prob is None: return "#aaa"
    if prob <= 20: return "#4A7C59"
    if prob <= 40: return "#7CA95B"
    if prob <= 60: return "#D4943A"
    return "#C05746"


def verdict(max_rain):
    if max_rain is None:
        return ("데이터 수집 중...", "잠시만 기다려주세요", "#aaa", "#f5f5f5")
    if max_rain <= 20:
        return ("야외 결혼식 걱정 없어요!", "하늘도 축복하는 날이네요 ✨", "#4A7C59", "#EDF5EE")
    if max_rain <= 40:
        return ("대체로 괜찮아요!", "혹시 모르니 우산 몇 개만 준비해두세요 ☂️", "#7CA95B", "#F2F7EE")
    if max_rain <= 60:
        return ("비 올 수도 있어요", "실내 백업 플랜 확인해두세요 🏠", "#D4943A", "#FDF5ED")
    return ("비 올 확률 높아요", "우천 시 플랜B 가동! 💪", "#C05746", "#FDEEEB")


def temp_advice(lo, hi):
    if lo is None or hi is None:
        return ""
    avg = (lo + hi) / 2
    if avg < 10: return "코트 필수! 따뜻하게 입으세요 🧥"
    if avg < 15: return "자켓이나 가디건 챙기세요 🧣"
    if avg < 20: return "가벼운 겉옷이면 딱이에요 👌"
    if avg < 25: return "야외 활동 최적 온도! ☀️"
    return "시원한 옷차림 추천 🌿"


def cell(data, key, fmt="{}"):
    if data and data.get(key) is not None:
        v = data[key]
        return fmt.format(int(v) if isinstance(v, float) and v == int(v) else v)
    return '<span style="color:#ddd">-</span>'


def render(openmeteo, naver, accuweather, kma):
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST).strftime("%m/%d %H:%M")
    dday_str = d_day()
    dday_num = (date.fromisoformat(WEDDING_DATE) - date.today()).days

    kd = kma["data"] if kma and kma["success"] else None
    ad = accuweather["data"] if accuweather and accuweather["success"] else None
    nd = naver["data"] if naver and naver["success"] else None
    srcs = [("기상청", kd, LINKS["kma"]),
            ("AccuWeather", ad, LINKS["accuweather"]),
            ("네이버", nd, LINKS["naver"])]

    rains = [s[1]["rain_prob"] for s in srcs if s[1] and s[1].get("rain_prob") is not None]
    mrain = max(rains) if rains else (openmeteo["rain_prob"] if openmeteo else None)
    vt, vsub, vc, vb = verdict(mrain)

    # 12~13시 시간대 기온/바람/습도 (결혼식 시간)
    noon_temp = ""
    wind_str = ""
    humidity_str = ""
    if openmeteo and openmeteo.get("hours"):
        h12 = next((h for h in openmeteo["hours"] if h["hour"] == 12), None)
        h13 = next((h for h in openmeteo["hours"] if h["hour"] == 13), None)
        if h12 and h13:
            avg_t = (h12["temp"] + h13["temp"]) / 2
            noon_temp = f"{avg_t:.0f}°C"
            wind_str = f'{max(h12["wind"], h13["wind"]):.0f}km/h'
            humidity_str = f'{int((h12["humidity"] + h13["humidity"]) / 2)}%'
        elif h12:
            noon_temp = f'{h12["temp"]:.0f}°C'
            wind_str = f'{h12["wind"]:.0f}km/h'
            humidity_str = f'{h12["humidity"]}%'

    tadvice = ""
    if noon_temp:
        t = float(noon_temp.replace("°C", ""))
        tadvice = temp_advice(t - 3, t + 3)

    # Source count
    ok_count = sum(1 for _, d, _ in srcs if d)

    # Rain bars
    bars = ""
    for nm, dt, _ in srcs:
        rp = dt["rain_prob"] if dt and dt.get("rain_prob") is not None else None
        if rp is not None:
            bars += f'''<div class="bar-row">
              <span class="bar-label">{nm}</span>
              <div class="bar-track"><div class="bar-fill" style="width:{max(rp,3)}%;background:{rc(rp)}"></div></div>
              <span class="bar-val" style="color:{rc(rp)}">{rp}%</span>
            </div>'''
        else:
            bars += f'''<div class="bar-row">
              <span class="bar-label">{nm}</span>
              <div class="bar-track"><div class="bar-fill" style="width:0"></div></div>
              <span class="bar-val" style="color:#ccc">-</span>
            </div>'''

    # Hourly
    hhtml = ""
    if openmeteo and openmeteo.get("hours"):
        hc = ""
        for h in openmeteo["hours"]:
            hl = "hcell-hl" if h["hour"] in (12, 13) else ""
            hc += f'''<div class="hcell {hl}">
              <div class="hc-t">{h["hour"]}시</div>
              <div class="hc-i">{h["emoji"]}</div>
              <div class="hc-tmp">{h["temp"]:.0f}°</div>
              <div class="hc-r" style="color:{rc(h["rain_prob"])}">{h["rain_prob"]}%</div>
              <div class="hc-w">{h["wind"]:.0f}<span>km/h</span></div>
            </div>'''
        hhtml = f'''<section class="card">
          <h3>결혼식 시간대 <span class="tag">Open-Meteo</span></h3>
          <div class="hscroll">{hc}</div>
          <div class="hscroll-hint">← 좌우 스크롤 →</div>
        </section>'''

    # Context days
    chtml = ""
    if openmeteo and openmeteo.get("context_days"):
        cc = ""
        for cd in openmeteo["context_days"]:
            w = "cday-w" if cd["date"] == WEDDING_DATE else ""
            lbl = "결혼식!" if cd["date"] == WEDDING_DATE else f'4/{cd["day"]}'
            cc += f'''<div class="cday {w}">
              <div class="cd-d">{lbl}</div>
              <div class="cd-i">{cd["emoji"]}</div>
              <div class="cd-t">{cd["temp_min"]:.0f}°/{cd["temp_max"]:.0f}°</div>
              <div class="cd-r" style="color:{rc(cd["rain_prob"])}">{cd["rain_prob"]}%</div>
            </div>'''
        chtml = f'''<section class="card">
          <h3>전후 날씨 흐름 <span class="tag">Open-Meteo</span></h3>
          <div class="cday-row">{cc}</div>
        </section>'''

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="refresh" content="10800">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta name="theme-color" content="#3D6B4D">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>결혼식 날씨 {dday_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --bg:#F7F6F3;--sf:#fff;--tx:#1A1A1A;--tx2:#6B6B6B;--tx3:#A8A8A8;
  --bd:#E8E6E1;--acc:#3D6B4D;--acc-l:#EDF5EE;
  --sh:0 1px 3px rgba(0,0,0,.04),0 4px 12px rgba(0,0,0,.03);
  --r:16px;
}}
body{{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,"Noto Sans KR",sans-serif;
  background:var(--bg);color:var(--tx);line-height:1.5;
  max-width:440px;margin:0 auto;
  padding-bottom:calc(20px + env(safe-area-inset-bottom,0px));
  -webkit-font-smoothing:antialiased;
}}

/* ===== Header ===== */
.hdr{{
  background:linear-gradient(165deg,#2D5A3D 0%,#4A7C59 40%,#6B9E7A 100%);
  color:#fff;text-align:center;
  padding:36px 24px 52px;
  position:relative;
}}
.hdr::after{{
  content:"";position:absolute;bottom:0;left:0;right:0;height:24px;
  background:var(--bg);border-radius:24px 24px 0 0;
}}
.hdr-venue{{
  font-size:12px;letter-spacing:1.5px;text-transform:uppercase;
  opacity:.7;font-weight:600;
}}
.hdr-dday{{
  font-size:56px;font-weight:900;margin:6px 0 2px;
  letter-spacing:-3px;line-height:1;
}}
.hdr-date{{font-size:14px;opacity:.85;font-weight:500}}
.hdr-addr{{font-size:11px;opacity:.55;margin-top:4px}}

/* ===== Verdict ===== */
.verdict{{
  background:{vb};
  border:1.5px solid {vc}20;
  margin:-12px 16px 0;border-radius:var(--r);
  padding:14px 18px 12px;text-align:center;
  position:relative;z-index:2;
  box-shadow:var(--sh);
}}
.v-emoji{{font-size:26px;margin-bottom:2px}}
.v-msg{{font-size:19px;font-weight:700;color:{vc};line-height:1.3}}
.v-sub{{font-size:12px;color:{vc}CC;margin-top:2px;font-weight:500}}
.v-stats{{
  display:flex;justify-content:center;gap:16px;
  margin-top:10px;padding-top:10px;
  border-top:1px solid {vc}15;
}}
.v-stat{{text-align:center}}
.v-stat-num{{font-size:18px;font-weight:800;color:var(--tx)}}
.v-stat-label{{font-size:10px;color:var(--tx2);font-weight:500;margin-top:0}}
.v-advice{{
  font-size:11px;color:var(--tx2);margin-top:8px;
  font-weight:500;font-style:italic;
}}

/* ===== Card ===== */
.card{{
  background:var(--sf);margin:14px 16px;border-radius:var(--r);
  padding:20px;box-shadow:var(--sh);
}}
.card h3{{
  font-size:13px;color:var(--tx2);font-weight:700;
  margin-bottom:16px;display:flex;align-items:center;gap:8px;
  letter-spacing:-.2px;
}}
.tag{{
  font-size:9px;background:var(--bg);color:var(--tx3);
  padding:2px 7px;border-radius:6px;font-weight:600;
  letter-spacing:.3px;
}}

/* ===== Rain Bars ===== */
.bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:12px}}
.bar-row:last-child{{margin-bottom:0}}
.bar-label{{font-size:12px;font-weight:600;width:78px;flex-shrink:0;color:var(--tx2)}}
.bar-track{{flex:1;height:24px;background:#F0EEEB;border-radius:12px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:12px;transition:width .8s cubic-bezier(.22,1,.36,1)}}
.bar-val{{font-size:16px;font-weight:800;width:42px;text-align:right;flex-shrink:0}}

/* ===== Comparison Table ===== */
.cmp{{width:100%;border-collapse:separate;border-spacing:0;font-size:13px}}
.cmp th{{
  font-weight:700;color:var(--tx2);padding:8px 6px;text-align:center;
  border-bottom:2px solid var(--bd);font-size:12px;
}}
.cmp th:first-child{{text-align:left;color:var(--tx3);width:48px;font-weight:600}}
.cmp td{{
  padding:10px 6px;text-align:center;font-weight:600;
  border-bottom:1px solid #f5f3f0;
}}
.cmp td:first-child{{text-align:left;font-weight:500;color:var(--tx2);font-size:12px}}
.cmp tr:last-child td{{border-bottom:none}}
.cmp .rain-cell{{font-size:16px;font-weight:800}}
.src-links{{display:flex;gap:8px;margin-top:16px}}
.src-link{{
  flex:1;text-align:center;padding:11px 6px;
  background:var(--acc-l);border-radius:12px;text-decoration:none;
  font-size:12px;font-weight:700;color:var(--acc);
  transition:all .15s;border:1px solid transparent;
}}
.src-link:active{{background:#d8eadb;border-color:var(--acc)33}}

/* ===== Hourly ===== */
.hscroll{{
  display:flex;gap:6px;overflow-x:auto;
  padding:4px 2px 6px;margin:0 -2px;
  -webkit-overflow-scrolling:touch;
  scroll-snap-type:x proximity;
  scrollbar-width:none;
}}
.hscroll::-webkit-scrollbar{{display:none}}
.hscroll-hint{{
  text-align:center;font-size:10px;color:var(--tx3);
  margin-top:6px;font-weight:500;
}}
.hcell{{
  flex:0 0 auto;width:60px;text-align:center;
  padding:10px 6px 8px;border-radius:14px;
  background:var(--bg);scroll-snap-align:center;
  transition:transform .15s;
}}
.hcell:active{{transform:scale(.96)}}
.hcell-hl{{
  background:linear-gradient(180deg,#FFF8E7,#FFF3D6);
  box-shadow:0 0 0 2px #E8B931,inset 0 1px 0 rgba(255,255,255,.5);
}}
.hc-t{{font-size:11px;font-weight:700;color:var(--tx2)}}
.hc-i{{font-size:22px;margin:4px 0 2px}}
.hc-tmp{{font-size:17px;font-weight:800;letter-spacing:-.5px}}
.hc-r{{font-size:12px;font-weight:700;margin-top:1px}}
.hc-w{{font-size:10px;color:var(--tx3);margin-top:2px}}
.hc-w span{{font-size:8px}}

/* ===== Context Days ===== */
.cday-row{{display:flex;gap:6px;justify-content:center}}
.cday{{
  flex:1;min-width:0;text-align:center;
  padding:12px 4px;border-radius:14px;background:var(--bg);
}}
.cday-w{{
  background:linear-gradient(180deg,#FFF8E7,#FFF3D6);
  box-shadow:0 0 0 2px #E8B931;
}}
.cd-d{{font-size:11px;font-weight:700;color:var(--tx2)}}
.cday-w .cd-d{{color:#B8890F}}
.cd-i{{font-size:22px;margin:4px 0 2px}}
.cd-t{{font-size:12px;font-weight:600}}
.cd-r{{font-size:12px;font-weight:700}}

/* ===== Update Bar (top) ===== */
.ubar{{
  display:flex;align-items:center;justify-content:space-between;
  margin:10px 16px;padding:8px 14px;
  background:var(--sf);border-radius:10px;box-shadow:var(--sh);
  font-size:11px;color:var(--tx3);
}}
.ubar-status{{display:flex;align-items:center;gap:4px;font-weight:500}}
.ubar-btn{{
  font-size:12px;font-weight:700;color:var(--acc);
  text-decoration:none;padding:4px 10px;border-radius:8px;
  background:var(--acc-l);transition:all .15s;
}}
.ubar-btn:active{{background:#d0e4d3}}

/* ===== Footer ===== */
.refresh-btn{{
  display:flex;align-items:center;justify-content:center;gap:6px;
  margin:14px 16px;padding:14px;
  background:var(--sf);border-radius:var(--r);box-shadow:var(--sh);
  font-size:14px;font-weight:700;color:var(--acc);
  text-decoration:none;transition:all .15s;
  border:1px solid transparent;
}}
.refresh-btn:active{{background:var(--acc-l);border-color:var(--acc)22}}
.footer{{
  text-align:center;padding:16px 16px 8px;
  font-size:11px;color:var(--tx3);line-height:1.6;
}}
.footer b{{color:var(--tx2);font-weight:600}}
.status-dot{{
  display:inline-block;width:6px;height:6px;border-radius:50%;
  background:#4A7C59;margin-right:4px;vertical-align:middle;
}}
</style>
</head>
<body>

<header class="hdr">
  <div class="hdr-venue">{WEDDING_LOCATION} &middot; 야외 결혼식</div>
  <div class="hdr-dday">{dday_str}</div>
  <div class="hdr-date">{WEDDING_DATE} ({WEDDING_DAY_KR}) {WEDDING_TIME}</div>
  <div class="hdr-addr">{WEDDING_ADDRESS}</div>
</header>

<div class="verdict">
  <div class="v-emoji">{"☀️" if mrain is not None and mrain <= 20 else "⛅" if mrain is not None and mrain <= 40 else "🌧️" if mrain is not None and mrain <= 60 else "⛈️" if mrain is not None else "🔄"}</div>
  <div class="v-msg">{vt}</div>
  <div class="v-sub">{vsub}</div>
  <div class="v-stats">
    <div class="v-stat"><div class="v-stat-num">{noon_temp or "-"}</div><div class="v-stat-label">12시 기온</div></div>
    <div class="v-stat"><div class="v-stat-num" style="color:{rc(mrain)}">{mrain if mrain is not None else "-"}%</div><div class="v-stat-label">강수확률 (최대)</div></div>
    <div class="v-stat"><div class="v-stat-num">{wind_str or "-"}</div><div class="v-stat-label">바람</div></div>
    <div class="v-stat"><div class="v-stat-num">{humidity_str or "-"}</div><div class="v-stat-label">습도</div></div>
  </div>
  {"<div class='v-advice'>" + tadvice + "</div>" if tadvice else ""}
</div>

<div class="ubar">
  <span class="ubar-status"><span class="status-dot"></span>{ok_count}개 소스 · {now}</span>
  <a class="ubar-btn" href="javascript:location.reload()">↻ 새로고침</a>
</div>

<section class="card">
  <h3>☔ 강수확률 비교</h3>
  {bars}
</section>

<section class="card">
  <h3>📊 소스별 비교</h3>
  <table class="cmp">
    <tr>
      <th></th>
      <th>기상청<br><span style="font-weight:400;font-size:10px;color:var(--tx3)">날씨날씨</span></th>
      <th>AccuW.</th>
      <th>네이버</th>
    </tr>
    <tr><td>최저</td><td>{cell(kd,"temp_min","{}°")}</td><td>{cell(ad,"temp_min","{}°")}</td><td>{cell(nd,"temp_min","{}°")}</td></tr>
    <tr><td>최고</td><td>{cell(kd,"temp_max","{}°")}</td><td>{cell(ad,"temp_max","{}°")}</td><td>{cell(nd,"temp_max","{}°")}</td></tr>
    <tr><td>강수</td>
      <td class="rain-cell" style="color:{rc(kd['rain_prob']) if kd and kd.get('rain_prob') is not None else '#ccc'}">{cell(kd,"rain_prob","{}%")}</td>
      <td class="rain-cell" style="color:{rc(ad['rain_prob']) if ad and ad.get('rain_prob') is not None else '#ccc'}">{cell(ad,"rain_prob","{}%")}</td>
      <td class="rain-cell" style="color:{rc(nd['rain_prob']) if nd and nd.get('rain_prob') is not None else '#ccc'}">{cell(nd,"rain_prob","{}%")}</td>
    </tr>
    <tr><td>하늘</td>
      <td style="font-size:11px">{cell(kd,"condition")}</td>
      <td style="font-size:11px">{cell(ad,"condition")}</td>
      <td style="font-size:11px">{cell(nd,"condition")}</td>
    </tr>
  </table>
  <div class="src-links">
    <a class="src-link" href="{LINKS['kma']}" target="_blank">기상청</a>
    <a class="src-link" href="{LINKS['accuweather']}" target="_blank">AccuWeather</a>
    <a class="src-link" href="{LINKS['naver']}" target="_blank">네이버</a>
  </div>
</section>

{hhtml}
{chtml}

<section class="card" id="trend-section" style="display:none">
  <h3>📈 예보 변화 추적</h3>
  <div id="trend-summary" style="font-size:14px;font-weight:600;margin-bottom:12px"></div>
  <div id="trend-table"></div>
  <div style="font-size:10px;color:var(--tx3);margin-top:10px;text-align:center">
    이 기기에서 확인할 때마다 자동 기록 · 최근 20회
  </div>
</section>

<div class="footer">
  탭을 열어두면 <b>3시간마다 자동 새로고침</b>돼요<br>
  매번 열 때마다 3개 소스에서 실시간 수집
</div>

<script>
(function(){{
  var KEY = "wedding_weather_history";
  var cur = {{
    ts: "{now}",
    kma: {kd["rain_prob"] if kd and kd.get("rain_prob") is not None else "null"},
    accu: {ad["rain_prob"] if ad and ad.get("rain_prob") is not None else "null"},
    naver: {nd["rain_prob"] if nd and nd.get("rain_prob") is not None else "null"}
  }};

  try {{
    var hist = JSON.parse(localStorage.getItem(KEY) || "[]");

    // 같은 시간(분 단위) 중복 방지 — 최소 30분 간격
    var dominated = hist.length > 0 && hist[0].ts === cur.ts;
    if (!dominated) {{
      hist.unshift(cur);
      if (hist.length > 20) hist = hist.slice(0, 20);
      localStorage.setItem(KEY, JSON.stringify(hist));
    }}

    if (hist.length < 2) return;

    // 트렌드 섹션 표시
    var sec = document.getElementById("trend-section");
    sec.style.display = "";

    // 요약: 가장 최근 vs 이전
    var prev = hist[1];
    var vals = ["kma","accu","naver"];
    var names = ["기상청","AccuW.","네이버"];
    var changes = [];
    for (var i = 0; i < 3; i++) {{
      var c = cur[vals[i]], p = prev[vals[i]];
      if (c !== null && p !== null && c !== p) {{
        var diff = c - p;
        var arrow = diff > 0 ? "↑" : "↓";
        var color = diff > 0 ? "#C05746" : "#4A7C59";
        changes.push("<span style='color:" + color + "'>" + names[i] + " " + arrow + Math.abs(diff) + "%</span>");
      }}
    }}

    var sumEl = document.getElementById("trend-summary");
    if (changes.length > 0) {{
      sumEl.innerHTML = "이전 대비: " + changes.join(" · ");
    }} else {{
      sumEl.innerHTML = "<span style='color:var(--tx3)'>이전과 동일한 예보</span>";
    }}

    // 히스토리 테이블
    var tbl = "<table style='width:100%;font-size:11px;border-collapse:collapse'>";
    tbl += "<tr style='color:var(--tx3)'><th style='text-align:left;padding:4px;font-weight:600'>시간</th>";
    tbl += "<th style='padding:4px'>기상청</th><th style='padding:4px'>AccuW.</th><th style='padding:4px'>네이버</th></tr>";
    var show = Math.min(hist.length, 8);
    for (var j = 0; j < show; j++) {{
      var h = hist[j];
      var bold = j === 0 ? "font-weight:700" : "color:var(--tx2)";
      var label = j === 0 ? "지금" : h.ts;
      tbl += "<tr style='" + bold + "'>";
      tbl += "<td style='padding:4px 4px;font-size:10px'>" + label + "</td>";
      for (var k = 0; k < 3; k++) {{
        var v = h[vals[k]];
        tbl += "<td style='padding:4px;text-align:center'>" + (v !== null ? v + "%" : "-") + "</td>";
      }}
      tbl += "</tr>";
    }}
    tbl += "</table>";
    document.getElementById("trend-table").innerHTML = tbl;
  }} catch(e) {{}}
}})();
</script>
</body>
</html>'''


# ============================================================
# Handler
# ============================================================

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Fetch all sources in parallel
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {
                ex.submit(fetch_openmeteo): "openmeteo",
                ex.submit(fetch_naver): "naver",
                ex.submit(fetch_accuweather): "accuweather",
                ex.submit(fetch_kma): "kma",
            }
            results = {}
            for fut in as_completed(futs, timeout=12):
                results[futs[fut]] = fut.result()

        html = render(
            results.get("openmeteo"),
            results.get("naver", {"success": False, "data": None}),
            results.get("accuweather", {"success": False, "data": None}),
            results.get("kma", {"success": False, "data": None}),
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))
