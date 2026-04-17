import { ImageResponse } from '@vercel/og';

export const config = { runtime: 'edge' };

export default function handler() {
  const today = new Date();
  const wedding = new Date('2026-04-25T00:00:00+09:00');
  const diff = Math.ceil((wedding - today) / (1000 * 60 * 60 * 24));
  const dday = diff > 0 ? `D-${diff}` : diff === 0 ? 'D-DAY!' : `D+${Math.abs(diff)}`;

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(160deg, #2D5A3D 0%, #4A7C59 40%, #6B9E7A 100%)',
          color: 'white',
          fontFamily: 'sans-serif',
        }}
      >
        <div style={{ fontSize: 28, opacity: 0.7, letterSpacing: 3, marginBottom: 12 }}>
          뜰안채 2 · 야외 결혼식
        </div>
        <div style={{ fontSize: 140, fontWeight: 900, letterSpacing: -5, lineHeight: 1 }}>
          {dday}
        </div>
        <div style={{ fontSize: 32, opacity: 0.85, marginTop: 12 }}>
          2026.04.25 (토) 12:30
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            marginTop: 32,
            padding: '14px 36px',
            background: 'rgba(255,255,255,0.15)',
            borderRadius: 30,
            fontSize: 24,
            fontWeight: 600,
          }}
        >
          ☀️ 3개 소스 실시간 날씨 비교
        </div>
        <div style={{ fontSize: 20, opacity: 0.5, marginTop: 24 }}>
          경기 의왕시 양지편로 39-18 야외정원
        </div>
      </div>
    ),
    { width: 1200, height: 630 }
  );
}
