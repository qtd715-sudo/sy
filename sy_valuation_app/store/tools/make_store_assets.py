"""Play 스토어 등록 이미지 일괄 생성 스크립트.

사전 조건
  1) 로컬 서버 실행:  python -m sy_valuation.run --host 127.0.0.1 --port 8765
     (회사망에서 Windows 프록시가 막혀 있으면 앞에
      HTTP_PROXY=http://127.0.0.1:1 HTTPS_PROXY=http://127.0.0.1:1 NO_PROXY=* 를 붙여 직접 연결)
  2) Google Chrome + Node 18+ (cdp_shot.mjs 가 DevTools Protocol 로 정확한 디바이스 크기로 캡처)
  3) Pillow:  pip install pillow

사용
  python make_store_assets.py            # 전체 (아이콘 + 그래픽 이미지 + 스크린샷 12장)
  python make_store_assets.py icon       # 아이콘/그래픽 이미지만
  python make_store_assets.py phone_01_dashboard tab10_03_news   # 특정 스크린샷만

출력: ../icon-512.png, ../feature-graphic-1024x500.png, ../screenshots/{phone,tablet-7,tablet-10}/*.png
중간 산출물(raw/, html/)은 git 에 포함하지 않는다.
"""
from __future__ import annotations

import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from cdp import shot  # noqa: E402
from PIL import Image  # noqa: E402

STORE = TOOLS.parent
APP = STORE.parent
RAW = TOOLS / "raw"
HTML = TOOLS / "html"
BASE = "http://127.0.0.1:8765/"
LOGO_SVG = APP / "assets" / "logo.svg"

# name: (route, css_w, css_h, dpr)
SHOTS = {
    # 휴대전화 (360x780 css @3 → 1080x2340, 갤럭시 계열 기준)
    "phone_01_dashboard":      ("#/dashboard",          360, 780, 3),
    "phone_02_sy":             ("#/sy?q=005930",        360, 780, 3),
    "phone_03_sy_screener":    ("#/sy?tab=screener",    360, 780, 3),
    "phone_04_multi":          ("#/multi?q=005930",     360, 780, 3),
    "phone_05_analysis":       ("#/analysis?q=005930",  360, 780, 3),
    "phone_06_news":           ("#/news",               360, 780, 3),
    # 7인치 태블릿 세로 (600x960 css @2 → 1200x1920)
    "tab7_01_dashboard":       ("#/dashboard",          600, 960, 2),
    "tab7_02_sy":              ("#/sy?q=005930",        600, 960, 2),
    "tab7_03_multi_screener":  ("#/multi?tab=screener", 600, 960, 2),
    # 10인치 태블릿 가로 (1280x800 css @2 → 2560x1600)
    "tab10_01_dashboard":      ("#/dashboard",          1280, 800, 2),
    "tab10_02_analysis":       ("#/analysis?q=005930",  1280, 800, 2),
    "tab10_03_news":           ("#/news",               1280, 800, 2),
}

# 최종 캔버스 (Play Console: 가로/세로 비 2:1 이내, 휴대전화 최소 320 / 10인치 최소 1080)
CANVAS = {"phone": (1080, 1920), "tab7": (1200, 1920), "tab10": (2560, 1600)}

# name -> (headline, sub)
CAPTIONS = {
    "phone_01_dashboard":     ("시장을 한 화면에",            "지수 · 환율 · 원자재 · 가상자산 · 시장 뉴스 · 저평가 Top 5"),
    "phone_02_sy":            ("SY 평가법으로 적정주가 산출",   "수익가치 + 자산가치 + 상대가치 3접근법 → 기업가치 min / mid / max"),
    "phone_03_sy_screener":   ("전종목 저평가 스크리너",        "KOSPI · KOSDAQ 전종목 · DART 정식 재무 기반 · 매일 자동 갱신"),
    "phone_04_multi":         ("9개 모델 적정주가를 한 번에",   "DCF · RIM · PER · PBR · PSR · EV/EBITDA · Graham · Lynch 가중평균"),
    "phone_05_analysis":      ("종합 분석과 투자 판단",         "SY 평가 + 다중모델 + 단기 · 장기 추천 (매수 · 매도 · 손절가)"),
    "phone_06_news":          ("토픽별 시장 뉴스",             "코스피 · 미장 · 환율 · 반도체 · 2차전지 · AI 자동 분류 + 감성 분석"),
    "tab7_01_dashboard":      ("시장을 한 화면에",            "지수 · 환율 · 원자재 · 가상자산 · 시장 뉴스 · 저평가 Top 5"),
    "tab7_02_sy":             ("SY 평가법으로 적정주가 산출",   "수익가치 + 자산가치 + 상대가치 3접근법 → 기업가치 min / mid / max"),
    "tab7_03_multi_screener": ("9개 모델 저평가 Top 10",       "DCF · RIM · PER · PBR · PSR · EV/EBITDA · Graham · Lynch 가중평균 기준"),
    "tab10_01_dashboard":     ("시장을 한 화면에",            "지수 · 환율 · 원자재 · 가상자산 · 시장 뉴스 · 저평가 Top 5 — 태블릿 와이드 레이아웃"),
    "tab10_02_analysis":      ("종합 분석과 투자 판단",         "SY 평가 + 9개 모델 + 단기 · 장기 추천을 한 화면에"),
    "tab10_03_news":          ("토픽별 시장 뉴스",             "코스피 · 미장 · 환율 · 반도체 · 2차전지 · AI 자동 분류 + 감성 분석"),
}

MARK = """<svg viewBox="240 280 544 490" width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">
  <line x1="272" y1="312" x2="752" y2="312" stroke="#22c55e" stroke-width="44" stroke-linecap="round"/>
  <rect x="300" y="548" width="112" height="196" rx="26" fill="#fafaf9"/>
  <rect x="456" y="464" width="112" height="280" rx="26" fill="#fafaf9"/>
  <rect x="612" y="380" width="112" height="364" rx="26" fill="#fafaf9"/>
</svg>"""


def _html(raw_png: pathlib.Path, W: int, H: int, headline: str, sub: str, landscape: bool) -> str:
    if landscape:
        frame_w = int(W * 0.78)
        glow, brand_top, brand_fs, mark_w = int(W * 0.9), int(H * 0.05), int(H * 0.026), int(H * 0.05)
        head_lr, head_top, h1_fs, p_fs, p_mt = int(W * 0.1), int(H * 0.11), int(H * 0.062), int(H * 0.028), int(H * 0.018)
        frame_top, radius, border = int(H * 0.30), int(frame_w * 0.03), int(frame_w * 0.006)
        glow_top = "-55%"
    else:
        frame_w = int(W * 0.80)
        glow, brand_top, brand_fs, mark_w = int(W * 1.3), int(H * 0.045), int(W * 0.026), int(W * 0.052)
        head_lr, head_top, h1_fs, p_fs, p_mt = int(W * 0.07), int(H * 0.10), int(W * 0.068), int(W * 0.029), int(W * 0.02)
        frame_top, radius, border = int(H * 0.255), int(frame_w * 0.075), int(frame_w * 0.012)
        glow_top = "-30%"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;background:#0a0a0a;color:#fafaf9;
  font-family:"Malgun Gothic","Segoe UI",sans-serif;}}
.glow{{position:absolute;left:50%;top:{glow_top};width:{glow}px;height:{glow}px;transform:translateX(-50%);border-radius:50%;
  background:radial-gradient(circle,rgba(34,197,94,.20) 0%,rgba(34,197,94,0) 65%);}}
.brand{{position:absolute;left:0;right:0;top:{brand_top}px;display:flex;align-items:center;justify-content:center;gap:16px;
  font-family:Consolas,monospace;font-size:{brand_fs}px;letter-spacing:6px;color:#a3a3a3;}}
.brand svg{{width:{mark_w}px;height:auto;}}
.head{{position:absolute;left:{head_lr}px;right:{head_lr}px;top:{head_top}px;text-align:center;}}
.head h1{{margin:0;font-size:{h1_fs}px;font-weight:700;letter-spacing:-1.5px;line-height:1.18;}}
.head p{{margin:{p_mt}px 0 0;font-size:{p_fs}px;line-height:1.45;color:#d6d3d1;}}
.frame{{position:absolute;left:50%;transform:translateX(-50%);top:{frame_top}px;width:{frame_w}px;
  border-radius:{radius}px;border:{border}px solid #27272a;background:#111;overflow:hidden;
  box-shadow:0 40px 90px rgba(0,0,0,.7);}}
.frame img{{display:block;width:100%;height:auto;}}
</style></head><body>
<div class="glow"></div>
<div class="brand">{MARK.format(w=mark_w, h=int(mark_w * 0.9))}<span>SY VALUATION</span></div>
<div class="head"><h1>{headline}</h1><p>{sub}</p></div>
<div class="frame"><img src="{raw_png.as_uri()}"></div>
</body></html>"""


def capture(names=None):
    RAW.mkdir(parents=True, exist_ok=True)
    for name, (route, w, h, dpr) in SHOTS.items():
        if names and name not in names:
            continue
        out = RAW / f"{name}.png"
        m = shot(BASE + route, w, h, dpr, str(out), wait_ms=2500, mobile=True, max_ms=90000)
        flag = "" if m["scrollWidth"] <= m["clientWidth"] else f"  !! 가로 오버플로 scrollWidth={m['scrollWidth']}"
        print(f"raw {name}: {w * dpr}x{h * dpr} ({m['elapsedMs']}ms){flag}")


def compose(names=None):
    HTML.mkdir(parents=True, exist_ok=True)
    sub_dir = {"phone": "screenshots/phone", "tab7": "screenshots/tablet-7", "tab10": "screenshots/tablet-10"}
    for name, (headline, sub) in CAPTIONS.items():
        if names and name not in names:
            continue
        kind, idx, *rest = name.split("_")
        W, H = CANVAS[kind]
        raw = RAW / f"{name}.png"
        if not raw.exists():
            print("raw 없음 (먼저 capture):", raw)
            continue
        hp = HTML / f"{name}.html"
        hp.write_text(_html(raw, W, H, headline, sub, landscape=(kind == "tab10")), encoding="utf-8")
        out = STORE / sub_dir[kind] / f"{idx}_{'_'.join(rest)}.png"
        shot(str(hp), W, H, 1, str(out), wait_ms=800, mobile=False, max_ms=60000)
        im = Image.open(out)
        assert im.size == (W, H), (name, im.size)
        im.convert("RGB").save(out)  # Play Console: 24-bit PNG (알파 없음)
        print(f"store {out.relative_to(STORE)} {W}x{H}")


def icon_and_feature():
    HTML.mkdir(parents=True, exist_ok=True)
    icon_html = HTML / "icon512.html"
    icon_html.write_text(
        '<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#0a0a0a}'
        f'img{{display:block;width:512px;height:512px}}</style></head><body><img src="{LOGO_SVG.as_uri()}"></body></html>',
        encoding="utf-8")
    out = STORE / "icon-512.png"
    shot(str(icon_html), 512, 512, 1, str(out), wait_ms=600, mobile=False)
    Image.open(out).convert("RGB").save(out)
    print("store icon-512.png 512x512")

    out = STORE / "feature-graphic-1024x500.png"
    shot(str(TOOLS / "feature_graphic.html"), 1024, 500, 1, str(out), wait_ms=800, mobile=False)
    im = Image.open(out)
    assert im.size == (1024, 500), im.size
    im.convert("RGB").save(out)
    print("store feature-graphic-1024x500.png 1024x500")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or "icon" in args:
        icon_and_feature()
    names = [a for a in args if a != "icon"]
    if not args or names:
        capture(names or None)
        compose(names or None)
