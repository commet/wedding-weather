#!/usr/bin/env python3
"""
Wedding Weather Dashboard
결혼식 날씨 대시보드

뜰안채 2 · 경기 의왕시 양지편로 39-18 야외정원
2026.04.25 (토) 12:30

사용법:
  python weather_check.py              # 한 번 실행
  python weather_check.py --schedule 3 # 3시간마다 자동 실행
  python weather_check.py --schedule 0 # 자동 실행 해제
"""

import argparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
import html as html_mod
import json
import os
import re
import subprocess
import sys
import webbrowser

# Windows 콘솔 UTF-8 출력
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ============================================================
# Configuration
# ============================================================
WEDDING_DATE = "2026-04-25"
WEDDING_TIME = "12:30"
WEDDING_DAY_KR = "토"
WEDDING_LOCATION = "뜰안채 2"
WEDDING_ADDRESS = "경기 의왕시 양지편로 39-18 야외정원"

UIWANG_LAT = 37.3448
UIWANG_LON = 126.9683

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "wedding_weather.html")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# AccuWeather는 Sec-* 헤더 필요, Referer 넣으면 403
ACCU_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
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

# WMO Weather interpretation codes -> Korean
WMO_CODES = {
    0: ("맑음", "☀️"), 1: ("대체로 맑음", "🌤️"), 2: ("부분 흐림", "⛅"),
    3: ("흐림", "☁️"), 45: ("안개", "🌫️"), 48: ("안개(상고대)", "🌫️"),
    51: ("가벼운 이슬비", "🌦️"), 53: ("이슬비", "🌦️"), 55: ("강한 이슬비", "🌧️"),
    56: ("약한 진눈깨비", "🌧️"), 57: ("강한 진눈깨비", "🌧️"),
    61: ("약한 비", "🌧️"), 63: ("비", "🌧️"), 65: ("강한 비", "🌧️"),
    66: ("약한 어는비", "🌧️"), 67: ("강한 어는비", "🌧️"),
    71: ("약한 눈", "🌨️"), 73: ("눈", "❄️"), 75: ("강한 눈", "❄️"),
    77: ("싸락눈", "🌨️"),
    80: ("약한 소나기", "🌦️"), 81: ("소나기", "🌧️"), 82: ("강한 소나기", "⛈️"),
    85: ("약한 눈소나기", "🌨️"), 86: ("강한 눈소나기", "❄️"),
    95: ("뇌우", "⛈️"), 96: ("뇌우+약한 우박", "⛈️"), 99: ("뇌우+강한 우박", "⛈️"),
}

LINKS = {
    "kma": "https://www.weather.go.kr/w/weather/forecast/mid-term.do?stnId1=109",
    "accuweather": "https://www.accuweather.com/ko/kr/uiwang/223635/daily-weather-forecast/223635",
    "accuweather_en": "https://www.accuweather.com/en/kr/uiwang/223635/daily-weather-forecast/223635",
    "naver": "https://search.naver.com/search.naver?query=의왕시+날씨",
}


# ============================================================
# Data Fetching
# ============================================================

def d_day():
    """D-day 계산"""
    today = date.today()
    wedding = date.fromisoformat(WEDDING_DATE)
    delta = (wedding - today).days
    if delta > 0:
        return f"D-{delta}"
    elif delta == 0:
        return "D-DAY!"
    else:
        return f"D+{abs(delta)}"


def wmo_to_korean(code):
    """WMO 코드를 한국어로 변환"""
    return WMO_CODES.get(code, ("알 수 없음", "❓"))


def fetch_openmeteo():
    """Open-Meteo API - 무료, 안정적, CORS 지원"""
    print("  [1/4] Open-Meteo API...")
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": UIWANG_LAT,
        "longitude": UIWANG_LON,
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min",
            "precipitation_probability_max", "precipitation_sum",
            "weathercode", "windspeed_10m_max",
        ]),
        "hourly": ",".join([
            "temperature_2m", "precipitation_probability",
            "precipitation", "weathercode",
            "windspeed_10m", "relativehumidity_2m",
        ]),
        "timezone": "Asia/Seoul",
        "forecast_days": 16,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        dates = data["daily"]["time"]
        if WEDDING_DATE not in dates:
            print("        4/25 범위 밖")
            return None

        idx = dates.index(WEDDING_DATE)
        daily = data["daily"]

        # Hourly data for wedding day (09~16시)
        hourly_times = data["hourly"]["time"]
        hourly = data["hourly"]
        wedding_hours = []
        for i, t in enumerate(hourly_times):
            if t.startswith(WEDDING_DATE):
                h = int(t[11:13])
                if 9 <= h <= 16:
                    wc = hourly["weathercode"][i]
                    _, emoji = wmo_to_korean(wc)
                    wedding_hours.append({
                        "hour": h,
                        "temp": hourly["temperature_2m"][i],
                        "rain_prob": hourly["precipitation_probability"][i],
                        "rain_mm": hourly["precipitation"][i],
                        "wind": hourly["windspeed_10m"][i],
                        "humidity": hourly["relativehumidity_2m"][i],
                        "emoji": emoji,
                    })

        wcode = daily["weathercode"][idx]
        cond_kr, cond_emoji = wmo_to_korean(wcode)

        # Multi-day context (4/23 ~ 4/27)
        context_days = []
        for d_offset in range(-2, 3):
            ctx_date = f"2026-04-{25 + d_offset:02d}"
            if ctx_date in dates:
                ci = dates.index(ctx_date)
                wc = daily["weathercode"][ci]
                ck, ce = wmo_to_korean(wc)
                context_days.append({
                    "date": ctx_date,
                    "day": ctx_date[-2:],
                    "temp_min": daily["temperature_2m_min"][ci],
                    "temp_max": daily["temperature_2m_max"][ci],
                    "rain_prob": daily["precipitation_probability_max"][ci],
                    "condition": ck,
                    "emoji": ce,
                })

        result = {
            "temp_min": daily["temperature_2m_min"][idx],
            "temp_max": daily["temperature_2m_max"][idx],
            "rain_prob": daily["precipitation_probability_max"][idx],
            "rain_mm": daily["precipitation_sum"][idx],
            "condition": cond_kr,
            "emoji": cond_emoji,
            "wind": daily["windspeed_10m_max"][idx],
            "hours": wedding_hours,
            "context_days": context_days,
        }
        print(f"        {result['temp_min']}~{result['temp_max']}C, "
              f"rain {result['rain_prob']}%, {result['condition']}")
        return result

    except Exception as e:
        print(f"        FAIL: {e}")
        return None


def fetch_naver():
    """네이버 날씨 스크래핑 (주간 예보 10일)"""
    print("  [2/4] Naver Weather...")
    url = "https://search.naver.com/search.naver"
    params = {"query": "의왕시 날씨"}

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        result = {"success": False, "data": None}

        # 네이버 주간 예보: li.week_item 안에 구조화된 데이터
        week_items = soup.select("li.week_item")
        if not week_items:
            print("        weekly forecast not found")
            return result

        for item in week_items:
            # 날짜 확인: span.date 에 "4.25." 형식
            date_el = item.select_one("span.date")
            if not date_el:
                continue
            date_text = date_el.get_text(strip=True)
            if "4.25" not in date_text:
                continue

            # 기온: span.lowest / span.highest (안에 span.blind "최저기온" 숨김 텍스트 포함)
            temp_min = temp_max = None
            lowest = item.select_one("span.lowest")
            highest = item.select_one("span.highest")
            if lowest:
                m = re.search(r"(-?\d+)", lowest.get_text())
                if m:
                    temp_min = float(m.group(1))
            if highest:
                m = re.search(r"(-?\d+)", highest.get_text())
                if m:
                    temp_max = float(m.group(1))

            # 강수확률: span.rainfall (2개 - 오전/오후)
            rainfalls = item.select("span.rainfall")
            rain_am = rain_pm = None
            if len(rainfalls) >= 1:
                m = re.search(r"(\d+)", rainfalls[0].get_text())
                if m:
                    rain_am = int(m.group(1))
            if len(rainfalls) >= 2:
                m = re.search(r"(\d+)", rainfalls[1].get_text())
                if m:
                    rain_pm = int(m.group(1))
            rain_prob = max(rain_am or 0, rain_pm or 0)

            # 날씨 상태: i.wt_icon > span.blind (2개 - 오전/오후)
            conditions = [
                el.get_text(strip=True)
                for el in item.select("i.wt_icon > span.blind")
            ]
            condition_am = conditions[0] if len(conditions) >= 1 else None
            condition_pm = conditions[1] if len(conditions) >= 2 else None

            if condition_am and condition_pm and condition_am != condition_pm:
                condition = f"오전 {condition_am} / 오후 {condition_pm}"
            else:
                condition = condition_am

            result["data"] = {
                "temp_min": temp_min,
                "temp_max": temp_max,
                "rain_prob": rain_prob,
                "rain_am": rain_am,
                "rain_pm": rain_pm,
                "condition": condition,
                "condition_am": condition_am,
                "condition_pm": condition_pm,
            }
            result["success"] = True
            break

        if result["success"]:
            d = result["data"]
            print(f"        {d['temp_min']}~{d['temp_max']}C, "
                  f"rain AM:{d['rain_am']}% PM:{d['rain_pm']}%, {d['condition']}")
        else:
            print("        4/25 not found in 10-day forecast")

        return result

    except Exception as e:
        print(f"        FAIL: {e}")
        return {"success": False, "data": None}


def fetch_accuweather():
    """AccuWeather 스크래핑 (영문 페이지, Sec-* 헤더 필수)"""
    print("  [3/4] AccuWeather...")
    # 영문 페이지가 파싱 안정적, Referer 헤더 넣으면 403
    url = LINKS["accuweather_en"]

    try:
        resp = requests.get(url, headers=ACCU_HEADERS, timeout=20)
        resp.raise_for_status()
        text = resp.text

        result = {"success": False, "data": None}

        # "4/25" 텍스트로 해당 카드 영역 찾기
        idx = text.find("4/25")
        if idx == -1:
            print("        4/25 not found in page")
            return result

        # 카드 시작점: "4/25" 앞의 가장 가까운 <a 태그
        card_start = text.rfind("<a", max(0, idx - 3000), idx)
        # 카드 끝점: 다음 daily-forecast-card 또는 </a> 태그
        card_end = text.find("daily-forecast-card", idx + 10)
        if card_end == -1:
            card_end = text.find("</a>", idx) + 4
        card = text[card_start:card_end]

        # 최고/최저 기온
        temp_max = temp_min = None
        m_high = re.search(r'class="high">(\d+)', card)
        m_low = re.search(r'class="low">/(\d+)', card)
        if m_high:
            temp_max = float(m_high.group(1))
        if m_low:
            temp_min = float(m_low.group(1))

        # 강수확률
        rain_prob = None
        m_precip = re.search(r'precip-icon.*?</svg>\s*(\d+)%', card, re.DOTALL)
        if m_precip:
            rain_prob = int(m_precip.group(1))

        # 날씨 상태
        condition = None
        m_phrase = re.search(r'class="phrase">([^<]+)', card)
        if m_phrase:
            condition = html_mod.unescape(m_phrase.group(1).strip())

        # RealFeel, Wind 등 추가 정보
        extras = {}
        for m in re.finditer(
            r'class="panel-item">([^<]+)<span class="value">([^<]+)', card
        ):
            label = html_mod.unescape(m.group(1).strip())
            value = html_mod.unescape(m.group(2).strip())
            extras[label] = value

        if temp_max is not None:
            result["data"] = {
                "temp_min": temp_min,
                "temp_max": temp_max,
                "rain_prob": rain_prob,
                "condition": condition,
                "extras": extras,
            }
            result["success"] = True

        if result["success"]:
            d = result["data"]
            print(f"        {d.get('temp_min')}~{d['temp_max']}C, "
                  f"rain {d.get('rain_prob')}%, {d.get('condition')}")
        else:
            print("        parsing failed")

        return result

    except Exception as e:
        print(f"        FAIL: {e}")
        return {"success": False, "data": None}


def fetch_kma():
    """기상청 중기예보 스크래핑 (2개 테이블: 강수+날씨, 기온)"""
    print("  [4/4] KMA (weather.go.kr)...")
    url = "https://www.weather.go.kr/w/weather/forecast/mid-term.do"
    params = {"stnId1": 109}

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        result = {"success": False, "data": {}}
        tables = soup.select("table")

        # === Table 0: 강수확률 & 날씨 (지역별) ===
        # 헤더: 지역 | 날짜들 (앞 3일 AM/PM colspan=2, 뒤 3일 단일)
        # 데이터: [지역명 td] + [9개 날씨 td]
        # 각 데이터 td: <i class="wic" title="맑음">맑음</i><span>10%</span>
        if tables:
            table0 = tables[0]
            rows = table0.select("tr")

            # 헤더 파싱: colspan을 고려한 컬럼-날짜 매핑
            header_ths = rows[0].select("th") if rows else []
            col_to_day = {}
            data_col = 0
            for th in header_ths:
                text = th.get_text(strip=True)
                if "지역" in text:
                    continue
                dm = re.search(r"(\d+)일", text)
                if dm:
                    day = int(dm.group(1))
                    colspan = int(th.get("colspan", 1))
                    for i in range(colspan):
                        col_to_day[data_col + i] = day
                    data_col += colspan

            # 25일 컬럼 인덱스 찾기
            target_cols = [c for c, d in col_to_day.items() if d == 25]

            if target_cols:
                for row in rows[2:]:  # 헤더 2줄 건너뛰기
                    row_text = row.get_text()
                    if "서울" not in row_text and "경기" not in row_text:
                        continue

                    tds = row.select("td")
                    # 첫 번째 td = 지역명, 나머지 = 날씨 데이터
                    weather_tds = []
                    for td in tds:
                        if td.select_one("i.wic") or (
                            td.select_one("span")
                            and re.search(r"\d+%", td.get_text())
                        ):
                            weather_tds.append(td)

                    for col_idx in target_cols:
                        if col_idx < len(weather_tds):
                            cell = weather_tds[col_idx]
                            # 강수확률
                            span = cell.select_one("span")
                            if span:
                                rm = re.search(r"(\d+)", span.get_text())
                                if rm:
                                    result["data"]["rain_prob"] = int(rm.group(1))
                            # 날씨 상태
                            icon = cell.select_one("i.wic")
                            if icon:
                                cond = icon.get("title") or icon.get_text(strip=True)
                                if cond:
                                    result["data"]["condition"] = cond
                    break

        # === Table 1: 기온 (도시별) ===
        # 헤더: 지역(colspan=2) | 날짜들 | 기온범위
        # 수원 행: span.tmn (최저), span.tmx (최고)
        if len(tables) >= 2:
            table1 = tables[1]
            rows = table1.select("tr")

            # 헤더에서 날짜 순서 파악
            header_ths = rows[0].select("th") if rows else []
            date_order = []
            for th in header_ths:
                dm = re.search(r"(\d+)일", th.get_text(strip=True))
                if dm:
                    date_order.append(int(dm.group(1)))

            target_temp_idx = None
            if 25 in date_order:
                target_temp_idx = date_order.index(25)

            if target_temp_idx is not None:
                for row in rows[1:]:
                    if "수원" not in row.get_text():
                        continue
                    # tmn/tmx 쌍이 있는 셀들만 수집
                    temp_pairs = []
                    for td in row.select("td"):
                        tmn = td.select_one("span.tmn")
                        tmx = td.select_one("span.tmx")
                        if tmn and tmx:
                            try:
                                temp_pairs.append((
                                    float(tmn.get_text(strip=True)),
                                    float(tmx.get_text(strip=True)),
                                ))
                            except ValueError:
                                pass
                    if target_temp_idx < len(temp_pairs):
                        mn, mx = temp_pairs[target_temp_idx]
                        result["data"]["temp_min"] = mn
                        result["data"]["temp_max"] = mx
                    break

        if result["data"].get("temp_min") is not None or result["data"].get("rain_prob") is not None:
            result["success"] = True

        if result["success"]:
            d = result["data"]
            print(f"        {d.get('temp_min')}~{d.get('temp_max')}C, "
                  f"rain {d.get('rain_prob')}%, {d.get('condition')}")
        else:
            print("        parsing failed (link provided)")

        return result

    except Exception as e:
        print(f"        FAIL: {e}")
        return {"success": False, "data": None}


# ============================================================
# Utilities
# ============================================================

def rain_color(prob):
    if prob is None:
        return "#aaa"
    if prob <= 20:
        return "#4A7C59"
    if prob <= 40:
        return "#7CA95B"
    if prob <= 60:
        return "#D4943A"
    return "#C05746"


def rain_label(prob):
    if prob is None:
        return "-"
    if prob <= 20:
        return "매우 낮음"
    if prob <= 40:
        return "낮음"
    if prob <= 60:
        return "보통"
    if prob <= 80:
        return "높음"
    return "매우 높음"


def verdict(max_rain):
    """강수확률 기반 종합 판정"""
    if max_rain is None:
        return ("데이터 없음", "#aaa", "#f5f5f5")
    if max_rain <= 20:
        return ("야외 결혼식 걱정 없어요!", "#4A7C59", "#EDF5EE")
    if max_rain <= 40:
        return ("대체로 괜찮지만 우산 준비", "#7CA95B", "#F2F7EE")
    if max_rain <= 60:
        return ("비 올 수 있어요, 대비 필요", "#D4943A", "#FDF5ED")
    return ("비 올 확률 높아요!", "#C05746", "#FDEEEB")


CONFIG_FILE = os.path.join(OUTPUT_DIR, "weather_config.json")


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"interval_hours": 3}


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ============================================================
# HTML Generation
# ============================================================

def generate_html(openmeteo, naver, accuweather, kma):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    dday = d_day()
    cfg = load_config()
    interval = cfg.get("interval_hours", 3)

    # --- 3개 주요 소스 데이터 ---
    kma_d = kma["data"] if kma and kma["success"] else None
    accu_d = accuweather["data"] if accuweather and accuweather["success"] else None
    naver_d = naver["data"] if naver and naver["success"] else None
    sources = [
        ("기상청", "날씨날씨", kma_d, LINKS["kma"]),
        ("AccuWeather", "의왕시", accu_d, LINKS["accuweather"]),
        ("네이버", "의왕시", naver_d, LINKS["naver"]),
    ]

    # 종합 수치
    rains = [s[2]["rain_prob"] for s in sources if s[2] and s[2].get("rain_prob") is not None]
    temps_lo = [s[2]["temp_min"] for s in sources if s[2] and s[2].get("temp_min") is not None]
    temps_hi = [s[2]["temp_max"] for s in sources if s[2] and s[2].get("temp_max") is not None]
    max_rain = max(rains) if rains else (openmeteo["rain_prob"] if openmeteo else None)
    vtext, vcolor, vbg = verdict(max_rain)

    temp_range = ""
    if temps_lo and temps_hi:
        temp_range = f"{min(temps_lo):.0f}° ~ {max(temps_hi):.0f}°C"
    elif openmeteo:
        temp_range = f"{openmeteo['temp_min']:.0f}° ~ {openmeteo['temp_max']:.0f}°C"

    # 강수확률 바 HTML
    rain_bars = ""
    for name, sub, data, link in sources:
        rp = data["rain_prob"] if data and data.get("rain_prob") is not None else None
        if rp is not None:
            pct = min(rp, 100)
            rc = rain_color(rp)
            rain_bars += f'''
            <div class="bar-row">
              <span class="bar-label">{name}</span>
              <div class="bar-track"><div class="bar-fill" style="width:{max(pct, 2)}%;background:{rc}"></div></div>
              <span class="bar-value" style="color:{rc}">{rp}%</span>
            </div>'''
        else:
            rain_bars += f'''
            <div class="bar-row">
              <span class="bar-label">{name}</span>
              <div class="bar-track"><div class="bar-fill" style="width:0"></div></div>
              <span class="bar-value" style="color:#aaa">-</span>
            </div>'''

    # 소스 비교 테이블 행
    def cell(data, key, fmt="{}"):
        if data and data.get(key) is not None:
            v = data[key]
            return fmt.format(int(v) if isinstance(v, float) and v == int(v) else v)
        return '<span style="color:#ccc">-</span>'

    # 시간별 예보
    hourly_html = ""
    if openmeteo and openmeteo.get("hours"):
        cells = ""
        for h in openmeteo["hours"]:
            hl = "hour-hl" if h["hour"] in (12, 13) else ""
            rc = rain_color(h["rain_prob"])
            cells += f'''<div class="hcell {hl}">
              <div class="h-time">{h["hour"]}시</div>
              <div class="h-icon">{h["emoji"]}</div>
              <div class="h-temp">{h["temp"]:.0f}°</div>
              <div class="h-rain" style="color:{rc}">{h["rain_prob"]}%</div>
              <div class="h-extra">{h["wind"]:.0f}km/h</div>
              <div class="h-extra">{h["humidity"]}%</div>
            </div>'''
        hourly_html = f'<section class="card"><h3>결혼식 시간대 <span class="badge">Open-Meteo</span></h3><div class="hscroll">{cells}</div></section>'

    # 전후 날씨
    ctx_html = ""
    if openmeteo and openmeteo.get("context_days"):
        cells = ""
        for cd in openmeteo["context_days"]:
            w = "ctx-w" if cd["date"] == WEDDING_DATE else ""
            rc = rain_color(cd["rain_prob"])
            cells += f'''<div class="ctx {w}">
              <div class="ctx-d">4/{cd["day"]}{"(토)" if cd["date"] == WEDDING_DATE else ""}</div>
              <div class="ctx-i">{cd["emoji"]}</div>
              <div class="ctx-t">{cd["temp_min"]:.0f}°/{cd["temp_max"]:.0f}°</div>
              <div class="ctx-r" style="color:{rc}">{cd["rain_prob"]}%</div>
            </div>'''
        ctx_html = f'<section class="card"><h3>전후 날씨 흐름 <span class="badge">Open-Meteo</span></h3><div class="ctx-row">{cells}</div></section>'

    # 풍속/습도 (Open-Meteo 12시 기준)
    wind_str = ""
    if openmeteo and openmeteo.get("hours"):
        h12 = next((h for h in openmeteo["hours"] if h["hour"] == 12), None)
        if h12:
            wind_str = f'{h12["wind"]:.0f}km/h'

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>결혼식 날씨 {dday}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --bg:#FAF9F6;--sf:#fff;--tx:#2C2C2C;--tx2:#888;--tx3:#bbb;
  --bd:#EDEBE8;--acc:#4A7C59;--acc2:#3D6B4D;--sh:0 1px 4px rgba(0,0,0,.05);
  --r:14px;
}}
body{{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",sans-serif;
  background:var(--bg);color:var(--tx);line-height:1.5;
  max-width:430px;margin:0 auto;padding-bottom:env(safe-area-inset-bottom,20px);
  -webkit-font-smoothing:antialiased;
}}

/* Header */
.hdr{{
  background:linear-gradient(160deg,#3D6B4D 0%,#5B8E6A 50%,#8AB89A 100%);
  color:#fff;text-align:center;padding:28px 20px 24px;
  position:relative;overflow:hidden;
}}
.hdr::after{{
  content:"";position:absolute;bottom:-30px;left:-20px;right:-20px;height:60px;
  background:var(--bg);border-radius:50% 50% 0 0;
}}
.hdr-d{{font-size:14px;opacity:.8;letter-spacing:.5px}}
.hdr-dday{{font-size:42px;font-weight:800;margin:4px 0;letter-spacing:-2px}}
.hdr-info{{font-size:13px;opacity:.75}}

/* Verdict */
.verdict{{
  background:{vbg};border:1px solid {vcolor}22;
  margin:0 16px;border-radius:var(--r);padding:24px 20px;
  text-align:center;position:relative;z-index:1;margin-top:-16px;
  box-shadow:var(--sh);
}}
.v-msg{{font-size:20px;font-weight:700;color:{vcolor};margin-bottom:8px}}
.v-detail{{display:flex;justify-content:center;gap:20px;font-size:15px;color:var(--tx)}}
.v-detail span{{display:flex;align-items:center;gap:4px}}
.v-detail .v-num{{font-weight:700}}

/* Rain bars */
.card{{
  background:var(--sf);margin:12px 16px;border-radius:var(--r);
  padding:18px;box-shadow:var(--sh);
}}
.card h3{{
  font-size:13px;color:var(--tx2);font-weight:600;margin-bottom:14px;
  display:flex;align-items:center;gap:6px;
}}
.badge{{
  font-size:10px;background:var(--bg);color:var(--tx3);
  padding:2px 6px;border-radius:4px;font-weight:500;
}}
.bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
.bar-row:last-child{{margin-bottom:0}}
.bar-label{{font-size:13px;font-weight:600;width:72px;flex-shrink:0}}
.bar-track{{flex:1;height:20px;background:#F0EEEB;border-radius:10px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:10px;transition:width .6s ease}}
.bar-value{{font-size:15px;font-weight:700;width:40px;text-align:right;flex-shrink:0}}

/* Comparison table */
.cmp{{width:100%;border-collapse:collapse;font-size:13px}}
.cmp th{{
  font-weight:600;color:var(--tx2);padding:6px 4px;text-align:center;
  border-bottom:1px solid var(--bd);font-size:12px;
}}
.cmp th:first-child{{text-align:left;color:var(--tx3);width:52px}}
.cmp td{{padding:8px 4px;text-align:center;font-weight:600}}
.cmp td:first-child{{text-align:left;font-weight:500;color:var(--tx2);font-size:12px}}
.cmp tr:last-child td{{border-bottom:none}}
.cmp .rain-cell{{font-size:15px}}

/* Source links */
.src-links{{display:flex;gap:6px;margin-top:14px}}
.src-link{{
  flex:1;text-align:center;padding:10px 4px;
  background:var(--bg);border-radius:10px;text-decoration:none;
  font-size:12px;font-weight:600;color:var(--acc2);
  transition:background .2s;
}}
.src-link:active{{background:#e0e0d8}}

/* Hourly scroll */
.hscroll{{
  display:flex;gap:3px;overflow-x:auto;padding-bottom:4px;
  -webkit-overflow-scrolling:touch;scroll-snap-type:x mandatory;
}}
.hcell{{
  flex:0 0 auto;width:56px;text-align:center;padding:8px 4px;
  border-radius:10px;background:var(--bg);scroll-snap-align:center;
}}
.hour-hl{{background:#FFF9EB;outline:2px solid #E8B931}}
.h-time{{font-size:11px;font-weight:600;color:var(--tx2)}}
.h-icon{{font-size:18px;margin:3px 0}}
.h-temp{{font-size:15px;font-weight:700}}
.h-rain{{font-size:12px;font-weight:600}}
.h-extra{{font-size:10px;color:var(--tx3)}}

/* Context days */
.ctx-row{{display:flex;gap:4px;justify-content:center}}
.ctx{{
  flex:0 0 auto;min-width:60px;text-align:center;
  padding:10px 6px;border-radius:10px;background:var(--bg);
}}
.ctx-w{{background:#FFF9EB;outline:2px solid #E8B931;font-weight:600}}
.ctx-d{{font-size:12px;font-weight:600}}
.ctx-i{{font-size:20px;margin:3px 0}}
.ctx-t{{font-size:12px}}
.ctx-r{{font-size:12px;font-weight:600}}

/* Settings */
.settings{{
  margin:12px 16px;padding:16px 18px;
  background:var(--sf);border-radius:var(--r);box-shadow:var(--sh);
}}
.settings h3{{font-size:13px;color:var(--tx2);font-weight:600;margin-bottom:10px}}
.interval-row{{display:flex;gap:6px;flex-wrap:wrap}}
.intv{{
  padding:8px 14px;border-radius:8px;border:1px solid var(--bd);
  background:var(--sf);font-size:13px;color:var(--tx);cursor:pointer;
  font-weight:500;transition:all .15s;
}}
.intv.active{{background:var(--acc);color:#fff;border-color:var(--acc)}}
.intv:active{{transform:scale(.96)}}

.footer{{
  text-align:center;padding:20px 16px 8px;font-size:11px;color:var(--tx3);
}}
.footer b{{color:var(--tx2);font-weight:600}}
</style>
</head>
<body>

<header class="hdr">
  <div class="hdr-d">{WEDDING_LOCATION} &middot; 야외 결혼식</div>
  <div class="hdr-dday">{dday}</div>
  <div class="hdr-info">{WEDDING_DATE} ({WEDDING_DAY_KR}) {WEDDING_TIME} &middot; {WEDDING_ADDRESS}</div>
</header>

<div class="verdict">
  <div class="v-msg">{vtext}</div>
  <div class="v-detail">
    <span>&#x1F321;&#xFE0F; <span class="v-num">{temp_range}</span></span>
    <span>&#x2614; <span class="v-num">{max_rain if max_rain is not None else "-"}%</span></span>
    {"<span>&#x1F4A8; <span class='v-num'>" + wind_str + "</span></span>" if wind_str else ""}
  </div>
</div>

<section class="card">
  <h3>강수확률 비교</h3>
  {rain_bars}
</section>

<section class="card">
  <h3>소스별 비교</h3>
  <table class="cmp">
    <tr>
      <th></th>
      <th>기상청<br><span style="font-weight:400;font-size:10px">날씨날씨</span></th>
      <th>AccuW.</th>
      <th>네이버</th>
    </tr>
    <tr>
      <td>최저</td>
      <td>{cell(kma_d, "temp_min", "{}°")}</td>
      <td>{cell(accu_d, "temp_min", "{}°")}</td>
      <td>{cell(naver_d, "temp_min", "{}°")}</td>
    </tr>
    <tr>
      <td>최고</td>
      <td>{cell(kma_d, "temp_max", "{}°")}</td>
      <td>{cell(accu_d, "temp_max", "{}°")}</td>
      <td>{cell(naver_d, "temp_max", "{}°")}</td>
    </tr>
    <tr>
      <td>강수</td>
      <td class="rain-cell" style="color:{rain_color(kma_d['rain_prob']) if kma_d and kma_d.get('rain_prob') is not None else '#aaa'}">{cell(kma_d, "rain_prob", "{}%")}</td>
      <td class="rain-cell" style="color:{rain_color(accu_d['rain_prob']) if accu_d and accu_d.get('rain_prob') is not None else '#aaa'}">{cell(accu_d, "rain_prob", "{}%")}</td>
      <td class="rain-cell" style="color:{rain_color(naver_d['rain_prob']) if naver_d and naver_d.get('rain_prob') is not None else '#aaa'}">{cell(naver_d, "rain_prob", "{}%")}</td>
    </tr>
    <tr>
      <td>하늘</td>
      <td style="font-size:11px">{cell(kma_d, "condition")}</td>
      <td style="font-size:11px">{cell(accu_d, "condition")}</td>
      <td style="font-size:11px">{cell(naver_d, "condition")}</td>
    </tr>
  </table>
  <div class="src-links">
    <a class="src-link" href="{LINKS['kma']}" target="_blank">기상청 &rarr;</a>
    <a class="src-link" href="{LINKS['accuweather']}" target="_blank">AccuWeather &rarr;</a>
    <a class="src-link" href="{LINKS['naver']}" target="_blank">네이버 &rarr;</a>
  </div>
</section>

{hourly_html}
{ctx_html}

<div class="settings">
  <h3>자동 업데이트 간격</h3>
  <div class="interval-row">
    {"".join(f'<div class="intv {"active" if interval == h else ""}" onclick="setInterval({h})">{h}시간</div>' for h in [1,2,3,4,5,6])}
  </div>
</div>

<div class="footer">
  마지막 업데이트 <b>{now}</b><br>
  python weather_check.py --schedule N 으로 자동 실행 설정
</div>

<script>
function setInterval(h) {{
  document.querySelectorAll('.intv').forEach(el => el.classList.remove('active'));
  event.target.classList.add('active');
  // Save selection hint for next run
  try {{ localStorage.setItem('wedding_weather_interval', h); }} catch(e) {{}}
  alert(h + '시간 간격으로 설정하려면:\\npython weather_check.py --schedule ' + h);
}}
</script>
</body>
</html>'''
    return html


# ============================================================
# Scheduling (Windows Task Scheduler)
# ============================================================

TASK_NAME = "WeddingWeatherUpdate"


def setup_schedule(hours):
    """자동 업데이트 스케줄 설정"""
    script_path = os.path.abspath(__file__)
    python_path = sys.executable
    minutes = hours * 60

    # Windows schtasks
    cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", f'"{python_path}" "{script_path}"',
        "/sc", "MINUTE",
        "/mo", str(minutes),
        "/f",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        cfg = load_config()
        cfg["interval_hours"] = hours
        save_config(cfg)
        print(f"  OK: {hours}h interval ({TASK_NAME})")
    else:
        print(f"  FAIL: {result.stderr.strip()}")
        # Fallback hint
        print(f"  Manual: schtasks /create /tn {TASK_NAME} "
              f'/tr "\\"{python_path}\\" \\"{script_path}\\"" '
              f"/sc MINUTE /mo {minutes} /f")


def remove_schedule():
    """자동 업데이트 스케줄 제거"""
    cmd = ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  Schedule removed ({TASK_NAME})")
    else:
        print(f"  No active schedule found")


# ============================================================
# Console Summary
# ============================================================

def print_summary(openmeteo, naver, accuweather, kma):
    print("\n" + "=" * 50)
    print(f"  {WEDDING_DATE} ({WEDDING_DAY_KR}) {WEDDING_TIME} | {d_day()}")
    print("=" * 50)

    sources = [
        ("KMA     ", kma["data"] if kma and kma["success"] else None),
        ("AccuW.  ", accuweather["data"] if accuweather and accuweather["success"] else None),
        ("Naver   ", naver["data"] if naver and naver["success"] else None),
    ]

    # Rain comparison
    print("\n  Rain probability:")
    for name, data in sources:
        rp = data["rain_prob"] if data and data.get("rain_prob") is not None else None
        if rp is not None:
            bar = "#" * (rp // 5) + "." * (20 - rp // 5)
            print(f"    {name} [{bar}] {rp}%")
        else:
            print(f"    {name} [....................] -")

    # Temperature
    print("\n  Temperature:")
    for name, data in sources:
        if data and data.get("temp_min") is not None:
            print(f"    {name} {data['temp_min']:.0f} ~ {data['temp_max']:.0f} C")

    # Verdict
    rains = [d["rain_prob"] for _, d in sources if d and d.get("rain_prob") is not None]
    if rains:
        vtext, _, _ = verdict(max(rains))
        print(f"\n  >> {vtext}")

    print("\n" + "-" * 50)


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Wedding Weather Dashboard")
    parser.add_argument(
        "--schedule", type=int, metavar="HOURS",
        help="Set auto-update interval (1-6 hours, 0=off)",
    )
    args = parser.parse_args()

    # Handle scheduling
    if args.schedule is not None:
        if args.schedule == 0:
            remove_schedule()
        elif 1 <= args.schedule <= 6:
            setup_schedule(args.schedule)
        else:
            print("  interval: 1~6 (hours), 0=off")
        return

    # Normal run
    print()
    print(f"  Wedding Weather | {d_day()}")
    print()

    openmeteo = fetch_openmeteo()
    naver = fetch_naver()
    accuweather = fetch_accuweather()
    kma = fetch_kma()

    print_summary(openmeteo, naver, accuweather, kma)

    html = generate_html(openmeteo, naver, accuweather, kma)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n  HTML: {OUTPUT_FILE}")

    try:
        webbrowser.open(f"file:///{OUTPUT_FILE.replace(os.sep, '/')}")
    except Exception:
        pass

    print()


if __name__ == "__main__":
    main()
