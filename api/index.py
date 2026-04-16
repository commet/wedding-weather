"""Vercel Serverless Function — Wedding Weather Dashboard"""

from http.server import BaseHTTPRequestHandler
from datetime import datetime, date
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
    today = date.today()
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


def fetch_accuweather():
    try:
        r = requests.get(LINKS["accuweather_en"], headers=ACCU_HEADERS, timeout=8)
        r.raise_for_status()
        text = r.text
        idx = text.find("4/25")
        if idx == -1:
            return {"success": False, "data": None}
        cs = text.rfind("<a", max(0, idx - 3000), idx)
        ce = text.find("daily-forecast-card", idx + 10)
        if ce == -1:
            ce = text.find("</a>", idx) + 4
        card = text[cs:ce]
        mh = re.search(r'class="high">(\d+)', card)
        ml = re.search(r'class="low">/(\d+)', card)
        mp = re.search(r'precip-icon.*?</svg>\s*(\d+)%', card, re.DOTALL)
        mc = re.search(r'class="phrase">([^<]+)', card)
        return {"success": True, "data": {
            "temp_max": float(mh.group(1)) if mh else None,
            "temp_min": float(ml.group(1)) if ml else None,
            "rain_prob": int(mp.group(1)) if mp else None,
            "condition": html_mod.unescape(mc.group(1).strip()) if mc else None,
        }}
    except Exception:
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
    if max_rain is None: return ("데이터 수집 중...", "#aaa", "#f5f5f5")
    if max_rain <= 20: return ("야외 결혼식 걱정 없어요!", "#4A7C59", "#EDF5EE")
    if max_rain <= 40: return ("대체로 괜찮지만 우산 준비", "#7CA95B", "#F2F7EE")
    if max_rain <= 60: return ("비 올 수 있어요, 대비 필요", "#D4943A", "#FDF5ED")
    return ("비 올 확률 높아요!", "#C05746", "#FDEEEB")


def cell(data, key, fmt="{}"):
    if data and data.get(key) is not None:
        v = data[key]
        return fmt.format(int(v) if isinstance(v, float) and v == int(v) else v)
    return '<span style="color:#ccc">-</span>'


def render(openmeteo, naver, accuweather, kma):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    dday_str = d_day()

    kd = kma["data"] if kma and kma["success"] else None
    ad = accuweather["data"] if accuweather and accuweather["success"] else None
    nd = naver["data"] if naver and naver["success"] else None
    srcs = [("기상청", "날씨날씨", kd, LINKS["kma"]),
            ("AccuWeather", "의왕시", ad, LINKS["accuweather"]),
            ("네이버", "의왕시", nd, LINKS["naver"])]

    rains = [s[2]["rain_prob"] for s in srcs if s[2] and s[2].get("rain_prob") is not None]
    tlo = [s[2]["temp_min"] for s in srcs if s[2] and s[2].get("temp_min") is not None]
    thi = [s[2]["temp_max"] for s in srcs if s[2] and s[2].get("temp_max") is not None]
    mrain = max(rains) if rains else (openmeteo["rain_prob"] if openmeteo else None)
    vt, vc, vb = verdict(mrain)
    tr = f"{min(tlo):.0f}° ~ {max(thi):.0f}°C" if tlo and thi else ("-" if not openmeteo else f"{openmeteo['temp_min']:.0f}° ~ {openmeteo['temp_max']:.0f}°C")

    wind_str = ""
    if openmeteo and openmeteo.get("hours"):
        h12 = next((h for h in openmeteo["hours"] if h["hour"] == 12), None)
        if h12:
            wind_str = f'{h12["wind"]:.0f}km/h'

    # Rain bars
    bars = ""
    for nm, _, dt, _ in srcs:
        rp = dt["rain_prob"] if dt and dt.get("rain_prob") is not None else None
        if rp is not None:
            bars += f'<div class="bar-row"><span class="bar-label">{nm}</span><div class="bar-track"><div class="bar-fill" style="width:{max(rp,2)}%;background:{rc(rp)}"></div></div><span class="bar-value" style="color:{rc(rp)}">{rp}%</span></div>'
        else:
            bars += f'<div class="bar-row"><span class="bar-label">{nm}</span><div class="bar-track"></div><span class="bar-value" style="color:#aaa">-</span></div>'

    # Hourly
    hhtml = ""
    if openmeteo and openmeteo.get("hours"):
        hc = ""
        for h in openmeteo["hours"]:
            hl = "hour-hl" if h["hour"] in (12, 13) else ""
            hc += f'<div class="hcell {hl}"><div class="h-time">{h["hour"]}시</div><div class="h-icon">{h["emoji"]}</div><div class="h-temp">{h["temp"]:.0f}°</div><div class="h-rain" style="color:{rc(h["rain_prob"])}">{h["rain_prob"]}%</div><div class="h-extra">{h["wind"]:.0f}km/h</div><div class="h-extra">{h["humidity"]}%</div></div>'
        hhtml = f'<section class="card"><h3>결혼식 시간대 <span class="badge">Open-Meteo</span></h3><div class="hscroll">{hc}</div></section>'

    # Context days
    chtml = ""
    if openmeteo and openmeteo.get("context_days"):
        cc = ""
        for cd in openmeteo["context_days"]:
            w = "ctx-w" if cd["date"] == WEDDING_DATE else ""
            cc += f'<div class="ctx {w}"><div class="ctx-d">4/{cd["day"]}{"(토)" if cd["date"] == WEDDING_DATE else ""}</div><div class="ctx-i">{cd["emoji"]}</div><div class="ctx-t">{cd["temp_min"]:.0f}°/{cd["temp_max"]:.0f}°</div><div class="ctx-r" style="color:{rc(cd["rain_prob"])}">{cd["rain_prob"]}%</div></div>'
        chtml = f'<section class="card"><h3>전후 날씨 흐름 <span class="badge">Open-Meteo</span></h3><div class="ctx-row">{cc}</div></section>'

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<meta http-equiv="refresh" content="10800">
<title>결혼식 날씨 {dday_str}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#FAF9F6;--sf:#fff;--tx:#2C2C2C;--tx2:#888;--tx3:#bbb;--bd:#EDEBE8;--acc:#4A7C59;--sh:0 1px 4px rgba(0,0,0,.05);--r:14px}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",sans-serif;background:var(--bg);color:var(--tx);line-height:1.5;max-width:430px;margin:0 auto;padding-bottom:env(safe-area-inset-bottom,20px);-webkit-font-smoothing:antialiased}}
.hdr{{background:linear-gradient(160deg,#3D6B4D,#5B8E6A 50%,#8AB89A);color:#fff;text-align:center;padding:28px 20px 24px;position:relative;overflow:hidden}}
.hdr::after{{content:"";position:absolute;bottom:-30px;left:-20px;right:-20px;height:60px;background:var(--bg);border-radius:50% 50% 0 0}}
.hdr-d{{font-size:14px;opacity:.8;letter-spacing:.5px}}
.hdr-dday{{font-size:42px;font-weight:800;margin:4px 0;letter-spacing:-2px}}
.hdr-info{{font-size:13px;opacity:.75}}
.verdict{{background:{vb};border:1px solid {vc}22;margin:0 16px;border-radius:var(--r);padding:24px 20px;text-align:center;position:relative;z-index:1;margin-top:-16px;box-shadow:var(--sh)}}
.v-msg{{font-size:20px;font-weight:700;color:{vc};margin-bottom:8px}}
.v-detail{{display:flex;justify-content:center;gap:20px;font-size:15px;color:var(--tx)}}
.v-detail span{{display:flex;align-items:center;gap:4px}}
.v-detail .v-num{{font-weight:700}}
.card{{background:var(--sf);margin:12px 16px;border-radius:var(--r);padding:18px;box-shadow:var(--sh)}}
.card h3{{font-size:13px;color:var(--tx2);font-weight:600;margin-bottom:14px;display:flex;align-items:center;gap:6px}}
.badge{{font-size:10px;background:var(--bg);color:var(--tx3);padding:2px 6px;border-radius:4px;font-weight:500}}
.bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
.bar-row:last-child{{margin-bottom:0}}
.bar-label{{font-size:13px;font-weight:600;width:72px;flex-shrink:0}}
.bar-track{{flex:1;height:20px;background:#F0EEEB;border-radius:10px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:10px;transition:width .6s ease}}
.bar-value{{font-size:15px;font-weight:700;width:40px;text-align:right;flex-shrink:0}}
.cmp{{width:100%;border-collapse:collapse;font-size:13px}}
.cmp th{{font-weight:600;color:var(--tx2);padding:6px 4px;text-align:center;border-bottom:1px solid var(--bd);font-size:12px}}
.cmp th:first-child{{text-align:left;color:var(--tx3);width:52px}}
.cmp td{{padding:8px 4px;text-align:center;font-weight:600}}
.cmp td:first-child{{text-align:left;font-weight:500;color:var(--tx2);font-size:12px}}
.cmp .rain-cell{{font-size:15px}}
.src-links{{display:flex;gap:6px;margin-top:14px}}
.src-link{{flex:1;text-align:center;padding:10px 4px;background:var(--bg);border-radius:10px;text-decoration:none;font-size:12px;font-weight:600;color:#3D6B4D;transition:background .2s}}
.src-link:active{{background:#e0e0d8}}
.hscroll{{display:flex;gap:3px;overflow-x:auto;padding-bottom:4px;-webkit-overflow-scrolling:touch;scroll-snap-type:x mandatory}}
.hcell{{flex:0 0 auto;width:56px;text-align:center;padding:8px 4px;border-radius:10px;background:var(--bg);scroll-snap-align:center}}
.hour-hl{{background:#FFF9EB;outline:2px solid #E8B931}}
.h-time{{font-size:11px;font-weight:600;color:var(--tx2)}}
.h-icon{{font-size:18px;margin:3px 0}}
.h-temp{{font-size:15px;font-weight:700}}
.h-rain{{font-size:12px;font-weight:600}}
.h-extra{{font-size:10px;color:var(--tx3)}}
.ctx-row{{display:flex;gap:4px;justify-content:center}}
.ctx{{flex:0 0 auto;min-width:60px;text-align:center;padding:10px 6px;border-radius:10px;background:var(--bg)}}
.ctx-w{{background:#FFF9EB;outline:2px solid #E8B931;font-weight:600}}
.ctx-d{{font-size:12px;font-weight:600}}
.ctx-i{{font-size:20px;margin:3px 0}}
.ctx-t{{font-size:12px}}
.ctx-r{{font-size:12px;font-weight:600}}
.footer{{text-align:center;padding:20px 16px 8px;font-size:11px;color:var(--tx3)}}
.footer b{{color:var(--tx2);font-weight:600}}
.refresh-btn{{display:block;margin:12px 16px;padding:14px;text-align:center;background:var(--sf);border-radius:var(--r);box-shadow:var(--sh);font-size:14px;font-weight:600;color:var(--acc);text-decoration:none;transition:background .2s}}
.refresh-btn:active{{background:#f0f0ec}}
</style>
</head>
<body>
<header class="hdr">
  <div class="hdr-d">{WEDDING_LOCATION} · 야외 결혼식</div>
  <div class="hdr-dday">{dday_str}</div>
  <div class="hdr-info">{WEDDING_DATE} ({WEDDING_DAY_KR}) {WEDDING_TIME} · {WEDDING_ADDRESS}</div>
</header>

<div class="verdict">
  <div class="v-msg">{vt}</div>
  <div class="v-detail">
    <span>&#x1F321;&#xFE0F; <span class="v-num">{tr}</span></span>
    <span>&#x2614; <span class="v-num">{mrain if mrain is not None else "-"}%</span></span>
    {"<span>&#x1F4A8; <span class='v-num'>" + wind_str + "</span></span>" if wind_str else ""}
  </div>
</div>

<section class="card">
  <h3>강수확률 비교</h3>
  {bars}
</section>

<section class="card">
  <h3>소스별 비교</h3>
  <table class="cmp">
    <tr><th></th><th>기상청<br><span style="font-weight:400;font-size:10px">날씨날씨</span></th><th>AccuW.</th><th>네이버</th></tr>
    <tr><td>최저</td><td>{cell(kd,"temp_min","{}°")}</td><td>{cell(ad,"temp_min","{}°")}</td><td>{cell(nd,"temp_min","{}°")}</td></tr>
    <tr><td>최고</td><td>{cell(kd,"temp_max","{}°")}</td><td>{cell(ad,"temp_max","{}°")}</td><td>{cell(nd,"temp_max","{}°")}</td></tr>
    <tr><td>강수</td>
      <td class="rain-cell" style="color:{rc(kd['rain_prob']) if kd and kd.get('rain_prob') is not None else '#aaa'}">{cell(kd,"rain_prob","{}%")}</td>
      <td class="rain-cell" style="color:{rc(ad['rain_prob']) if ad and ad.get('rain_prob') is not None else '#aaa'}">{cell(ad,"rain_prob","{}%")}</td>
      <td class="rain-cell" style="color:{rc(nd['rain_prob']) if nd and nd.get('rain_prob') is not None else '#aaa'}">{cell(nd,"rain_prob","{}%")}</td>
    </tr>
    <tr><td>하늘</td><td style="font-size:11px">{cell(kd,"condition")}</td><td style="font-size:11px">{cell(ad,"condition")}</td><td style="font-size:11px">{cell(nd,"condition")}</td></tr>
  </table>
  <div class="src-links">
    <a class="src-link" href="{LINKS['kma']}" target="_blank">기상청 &rarr;</a>
    <a class="src-link" href="{LINKS['accuweather']}" target="_blank">AccuWeather &rarr;</a>
    <a class="src-link" href="{LINKS['naver']}" target="_blank">네이버 &rarr;</a>
  </div>
</section>

{hhtml}
{chtml}

<a class="refresh-btn" href="javascript:location.reload()">&#x1F504; 지금 새로고침</a>

<div class="footer">
  마지막 업데이트 <b>{now} KST</b><br>
  3시간마다 자동 새로고침 · 새로고침 시 최신 데이터 수집
</div>
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
        self.send_header("Cache-Control", "public, max-age=1800")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))
