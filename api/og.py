"""OG Image generator — dynamic SVG-based social preview"""

from http.server import BaseHTTPRequestHandler
from datetime import datetime, date, timezone, timedelta

WEDDING_DATE = "2026-04-25"

KST = timezone(timedelta(hours=9))


def d_day():
    today = datetime.now(KST).date()
    w = date.fromisoformat(WEDDING_DATE)
    d = (w - today).days
    return f"D-{d}" if d > 0 else ("D-DAY!" if d == 0 else f"D+{abs(d)}")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        dday = d_day()

        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#2D5A3D"/>
      <stop offset="50%" style="stop-color:#4A7C59"/>
      <stop offset="100%" style="stop-color:#6B9E7A"/>
    </linearGradient>
  </defs>

  <rect width="1200" height="630" fill="url(#bg)"/>

  <!-- Decorative circles -->
  <circle cx="1050" cy="120" r="180" fill="white" opacity="0.04"/>
  <circle cx="150" cy="530" r="120" fill="white" opacity="0.04"/>

  <!-- Venue -->
  <text x="600" y="160" text-anchor="middle"
    font-family="sans-serif" font-size="28" font-weight="600"
    fill="white" opacity="0.7" letter-spacing="3">
    뜰안채 2 · 야외 결혼식
  </text>

  <!-- D-day -->
  <text x="600" y="290" text-anchor="middle"
    font-family="sans-serif" font-size="140" font-weight="900"
    fill="white" letter-spacing="-5">
    {dday}
  </text>

  <!-- Date -->
  <text x="600" y="360" text-anchor="middle"
    font-family="sans-serif" font-size="32" font-weight="500"
    fill="white" opacity="0.85">
    2026.04.25 (토) 12:30
  </text>

  <!-- Subtitle -->
  <rect x="380" y="410" width="440" height="52" rx="26" fill="white" opacity="0.15"/>
  <text x="600" y="445" text-anchor="middle"
    font-family="sans-serif" font-size="24" font-weight="600"
    fill="white">
    ☀️  3개 소스 실시간 날씨 비교
  </text>

  <!-- Address -->
  <text x="600" y="540" text-anchor="middle"
    font-family="sans-serif" font-size="20" font-weight="400"
    fill="white" opacity="0.5">
    경기 의왕시 양지편로 39-18 야외정원
  </text>
</svg>'''

        # Convert SVG to PNG-like response via SVG
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(svg.encode("utf-8"))
