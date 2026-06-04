// SY Valuation — vanilla JS SPA
// Routes (재구성 후 5개 페이지):
//   #/dashboard          — 01 DASHBOARD
//   #/sy?q=<>&tab=<>     — 02 기업가치평가(SY)  (tab: single | screener)
//   #/multi?q=<>&tab=<>  — 03 다중모델 평가     (tab: single | screener)
//   #/analysis?q=<>      — 04 종합 분석 (SY + 다중모델 + 추천)
//   #/news               — 05 토픽뉴스
//
// 레거시 라우트 (자동 redirect):
//   #/sy-analysis, #/sy-detail, #/sy-screener  → #/sy
//   #/search, #/undervalued                    → #/multi
//   #/recommend                                → #/analysis

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

const fmt = {
  krw(n) {
    if (n === null || n === undefined || isNaN(n) || n === 0) return "-";
    return new Intl.NumberFormat("ko-KR").format(Math.round(n)) + "원";
  },
  num(n, d = 2) {
    if (n === null || n === undefined || isNaN(n) || n === 0) return "-";
    return Number(n).toLocaleString("ko-KR", { minimumFractionDigits: 0, maximumFractionDigits: d });
  },
  pct(n, d = 2) {
    if (n === null || n === undefined || isNaN(n)) return "-";
    if (n === 0) return "0.00%";    // 0% 는 의미있는 값
    const v = (Number(n) * 100).toFixed(d);
    return (Number(n) >= 0 ? "+" : "") + v + "%";
  },
  bigKrw(n) {
    if (n === null || n === undefined || isNaN(n) || n === 0) return "-";
    const abs = Math.abs(n);
    if (abs >= 1e12) return (n / 1e12).toFixed(2) + "조원";
    if (abs >= 1e8) return (n / 1e8).toFixed(0) + "억원";
    return new Intl.NumberFormat("ko-KR").format(Math.round(n)) + "원";
  },
  // 글로벌 통화 자동 (USD 등) — current_price + currency 받아서
  price(n, currency) {
    if (n === null || n === undefined || isNaN(n) || n === 0) return "-";
    if (currency && currency !== "KRW") {
      return "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    }
    return fmt.krw(n);
  },
};

// 기본 타임아웃 5초. 외부 API 의존(평가/추천 등) 호출은 명시적으로 더 길게.
// 5초 안에 응답 없으면 AbortError → 친화적 메시지로 throw.
// 단, SW 캐시(SWR)가 있으면 거의 즉시 반환되므로 첫 콜드 방문에서만 발생.
async function api(path, opts = {}) {
  const timeoutMs = opts.timeout ?? 5000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const fetchOpts = {
    signal: controller.signal,
    ...(path.startsWith("/api/admin/") ? { credentials: "include" } : {}),
  };
  try {
    const res = await fetch(path, fetchOpts);
    if (res.status === 401) throw new Error("인증이 필요합니다. 새로고침해서 비밀번호 입력하세요.");
    if (!res.ok) throw new Error(await res.text());
    return await res.json();
  } catch (e) {
    if (e.name === "AbortError") {
      // 캐시에서라도 가져오기 시도 (SW가 가로채서 stale 응답 반환 가능)
      try {
        const r = await fetch(path, { cache: "force-cache" });
        if (r.ok) {
          const data = await r.json();
          data.__stale = true;
          return data;
        }
      } catch {}
      const sec = Math.round(timeoutMs / 1000);
      throw new Error(`응답이 ${sec}초를 넘었습니다. 백그라운드 갱신 중 — 잠시 후 새로고침해주세요.`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

// ---------- Routing ----------
function parseRoute() {
  const hash = location.hash || "#/dashboard";
  const [pathPart, queryPart] = hash.replace(/^#/, "").split("?");
  const params = {};
  if (queryPart) {
    queryPart.split("&").forEach(kv => {
      const [k, v] = kv.split("=");
      params[decodeURIComponent(k)] = decodeURIComponent(v || "");
    });
  }
  return { path: pathPart || "/dashboard", params };
}

function navigate(path, params = {}) {
  const q = Object.entries(params)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
  location.hash = "#" + path + (q ? "?" + q : "");
}

window.addEventListener("hashchange", render);
window.addEventListener("DOMContentLoaded", () => {
  initHeader();
  render();
  // 첫 페이지가 그려진 뒤 idle 시간에 다른 탭 데이터 prefetch — SW 캐시까지 들어가서
  // 사용자가 어떤 메뉴를 눌러도 즉시 화면이 뜸. 실패해도 무시.
  schedulePrefetch();
});

function schedulePrefetch() {
  const urls = [
    "/api/commodities",
    "/api/undervalued?n=10",
    "/api/sy/undervalued?n=10",
    "/api/news/market?n=4",
    "/api/news/topics?n=4",
    "/api/market-news?n=10",
  ];
  const run = () => urls.forEach(u => {
    fetch(u, { credentials: "same-origin" }).catch(() => {});
  });
  if ("requestIdleCallback" in window) {
    requestIdleCallback(run, { timeout: 3000 });
  } else {
    setTimeout(run, 1500);
  }
}

function initHeader() {
  const inp = $("#globalSearch");
  // 검색은 종합 분석 페이지로 (재구성 후 의사결정 종착지)
  attachAutocomplete(inp, (item) => navigate("/analysis", { q: item.ticker }));
  $("#globalSearchBtn").addEventListener("click", () => {
    const q = inp.value.trim();
    if (q) navigate("/analysis", { q });
  });
  inp.addEventListener("keydown", e => {
    if (e.key === "Enter" && !$(".ac-dropdown.active")) {
      const q = inp.value.trim();
      if (q) navigate("/analysis", { q });
    }
  });

  // 로고 클릭 → 01 대시보드
  const brand = $(".brand");
  if (brand) {
    brand.style.cursor = "pointer";
    brand.addEventListener("click", () => navigate("/dashboard"));
  }

  // 헤더 상태바 — 백엔드 응답 없을 때만 경고 표시 (정상 시 종목 수 등은 숨김)
  api("/api/health").then(() => {
    $("#status").textContent = "";
  }).catch(() => {
    $("#status").textContent = "백엔드 응답 없음";
    $("#status").style.color = "var(--neg)";
  });
}

function setActiveNav(route) {
  $$(".nav-item").forEach(el => el.classList.toggle("active", el.dataset.route === route));
  // 모바일 nav 도 동기화 (이미 위에서 다 처리됨)
  // 활성 항목을 좌측으로 자동 스크롤
  const active = $(".topnav .nav-item.active");
  if (active && active.scrollIntoView) {
    try { active.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" }); } catch {}
  }
}

// 레거시 → 신규 라우트 매핑 (북마크 / 외부 링크 호환)
const LEGACY_REDIRECT = {
  "/sy-analysis":  "/sy",
  "/sy-detail":    "/sy",
  "/sy-screener":  { path: "/sy",       extraParams: { tab: "screener" } },
  "/search":       "/multi",
  "/undervalued":  { path: "/multi",    extraParams: { tab: "screener" } },
  "/recommend":    "/analysis",
};

async function render() {
  const { path, params } = parseRoute();
  const root = $("#content");

  // 1) 레거시 라우트 → 신규로 redirect
  for (const [legacy, target] of Object.entries(LEGACY_REDIRECT)) {
    if (path.startsWith(legacy)) {
      const newPath = typeof target === "string" ? target : target.path;
      const newParams = typeof target === "string"
        ? params
        : { ...params, ...target.extraParams };
      return navigate(newPath, newParams);
    }
  }

  // 2) 신규 라우트
  if (path.startsWith("/dashboard")) { setActiveNav("dashboard"); return renderDashboard(root); }
  if (path.startsWith("/sy"))        { setActiveNav("sy");        return renderSyPage(root, params); }
  if (path.startsWith("/multi"))     { setActiveNav("multi");     return renderMultiPage(root, params); }
  if (path.startsWith("/analysis"))  { setActiveNav("analysis");  return renderAnalysisPage(root, params); }
  if (path.startsWith("/news"))      { setActiveNav("news");      return renderNews(root); }

  // 3) 관리자 페이지 (라우트 변경 없음)
  if (path.startsWith("/analytics")) { setActiveNav("analytics"); return renderAnalytics(root); }

  root.innerHTML = `<div class="error">알 수 없는 페이지: ${path}</div>`;
}

// ─── 새 페이지 컨테이너 (C2 stub — C3~C5 에서 탭/통합 본구현) ──────────

async function renderSyPage(root, params) {
  const tab = params.tab || "single";
  // 탭 헤더 + 콘텐츠 컨테이너
  root.innerHTML = `
    <div class="page-tabs">
      <button class="tab ${tab==='single'?'active':''}" data-tab="single">단일 종목</button>
      <button class="tab ${tab==='screener'?'active':''}" data-tab="screener">TOP10 스크리너</button>
    </div>
    <div id="syTabContent"></div>
  `;
  // 탭 클릭 시 URL 갱신 (tab 파라미터)
  $$('.page-tabs .tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.tab;
      const next = { ...params, tab: t };
      // single 일 땐 tab 파라미터 생략 (깔끔한 URL)
      if (t === 'single') delete next.tab;
      navigate('/sy', next);
    });
  });
  const content = $('#syTabContent');
  if (tab === 'screener') return renderSyScreener(content);
  return renderSyAnalysis(content, params);
}

async function renderMultiPage(root, params) {
  const tab = params.tab || "single";
  root.innerHTML = `
    <div class="page-tabs">
      <button class="tab ${tab==='single'?'active':''}" data-tab="single">단일 종목 (9-모델)</button>
      <button class="tab ${tab==='screener'?'active':''}" data-tab="screener">저평가 TOP10</button>
    </div>
    <div id="multiTabContent"></div>
  `;
  $$('.page-tabs .tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.tab;
      const next = { ...params, tab: t };
      if (t === 'single') delete next.tab;
      navigate('/multi', next);
    });
  });
  const content = $('#multiTabContent');
  if (tab === 'screener') return renderUndervalued(content);
  return renderSearch(content, params);
}

async function renderAnalysisPage(root, params) {
  // 04 종합 분석 — SY 평가법 + 다중모델 평가 + 뉴스 감성 + 의사결정
  // 3개 API 병렬 호출 (sy_evaluate + valuation + recommend)
  const q = params.q || "";
  root.innerHTML = `
    <h1 class="page-title">종합 분석<span class="muted">／ SY + MULTI-MODEL + DECISION</span></h1>
    ${metaStrip('§04·ANALYSIS', 'SY 평가법', '9-모델 비교', '뉴스 감성 + 의사결정')}
    <p class="page-sub">SY 평가법(3접근법) + 다중모델(9개) + 뉴스 감성 + 변동성 → 단기/장기 의사결정 한 화면.</p>

    <form id="anaForm" class="page-search">
      <input id="anaInp" type="text" value="${escapeHtml(q)}" placeholder="🔍 기업명 또는 종목코드 — 예: 삼성전자, 엠로, 005930" autocomplete="off">
      <button type="submit">분석</button>
    </form>

    <div id="anaResult"></div>
  `;
  const inp = $("#anaInp");
  attachAutocomplete(inp, (item) => navigate("/analysis", { q: item.ticker }));
  $("#anaForm").addEventListener("submit", e => {
    e.preventDefault();
    const v = inp.value.trim();
    if (v) navigate("/analysis", { q: v });
  });

  if (!q) return;

  const out = $("#anaResult");
  out.innerHTML = `<div class="loading">분석 중… (SY + 다중모델 + 뉴스 감성 병렬 호출)</div>`;

  try {
    // 3개 API 병렬 호출 — 어느 하나 실패해도 나머지 표시
    const [syRes, valRes, recRes] = await Promise.allSettled([
      api(`/api/sy/evaluate?q=${encodeURIComponent(q)}`, { timeout: 20000 }),
      api(`/api/valuation?q=${encodeURIComponent(q)}`, { timeout: 20000 }),
      api(`/api/recommend?q=${encodeURIComponent(q)}`, { timeout: 20000 }),
    ]);
    const sy  = syRes.status  === 'fulfilled' ? syRes.value  : null;
    const val = valRes.status === 'fulfilled' ? valRes.value : null;
    const rec = recRes.status === 'fulfilled' ? recRes.value : null;

    if (!sy && !val && !rec) {
      out.innerHTML = `<div class="error">3개 API 모두 응답 실패. 종목을 다시 확인해주세요.</div>`;
      return;
    }
    out.innerHTML = renderAnalysisContent({ sy, val, rec, q });
  } catch (e) {
    out.innerHTML = `<div class="error">${e.message}</div>`;
  }
}

function renderAnalysisContent({ sy, val, rec, q }) {
  // ─── 종목 헤더 ───────────────────────────────────────────────
  const name   = sy?.name   || val?.financials?.name   || q;
  const ticker = sy?.ticker || val?.financials?.ticker || q;
  const sector = sy?.sector || val?.financials?.sector || "—";
  const price  = sy?.current_price || val?.financials?.current_price || 0;
  const mcap   = sy?.market_cap || (val ? (val.financials?.current_price || 0) * (val.financials?.shares_outstanding || 0) : 0);
  const market = sy?.inputs?.market || "—";

  // ─── SY 결과 ────────────────────────────────────────────────
  const syBlock = sy ? `
    <div class="card analysis-block">
      <h3>SY 평가법 <span class="muted" style="font-size:11px">／ 3접근법 통합</span></h3>
      <table class="kpi-table">
        <tr><td>수익가치 (min/mid/max)</td>
            <td class="right">${fmt.bigKrw(sy.income_min)} / <b>${fmt.bigKrw(sy.income_mid)}</b> / ${fmt.bigKrw(sy.income_max)}</td></tr>
        <tr><td>자산가치 (min/mid/max)</td>
            <td class="right">${fmt.bigKrw(sy.asset_min)} / <b>${fmt.bigKrw(sy.asset_mid)}</b> / ${fmt.bigKrw(sy.asset_max)}</td></tr>
        <tr><td>상대가치 (min/mid/max)</td>
            <td class="right">${fmt.bigKrw(sy.market_min)} / <b>${fmt.bigKrw(sy.market_mid)}</b> / ${fmt.bigKrw(sy.market_max)}</td></tr>
        <tr class="separator"><td>기업가치 mid</td><td class="right"><b>${fmt.bigKrw(sy.enterprise_mid)}</b></td></tr>
        <tr><td>적정가 mid</td><td class="right"><b>${fmt.krw(sy.fair_price_mid)}</b></td></tr>
        <tr><td>상승률 mid</td><td class="right ${sy.upside_mid >= 0 ? 'pos' : 'neg'}"><b>${fmt.pct(sy.upside_mid)}</b></td></tr>
        <tr><td>등급</td><td class="right"><span class="rating-tag rating-${(sy.rating||'').toLowerCase()}">${sy.rating || '-'}</span></td></tr>
      </table>
    </div>
  ` : `<div class="card analysis-block muted">SY 평가법 응답 실패</div>`;

  // ─── 다중모델 결과 ────────────────────────────────────────
  let multiBlock;
  if (val && val.valuation) {
    const v = val.valuation;
    const byModel = v.by_model || {};
    const entries = Object.entries(byModel).filter(([_, vv]) => vv > 0);
    const median = entries.length ? medianOf(entries.map(([_, vv]) => vv)) : 0;
    multiBlock = `
      <div class="card analysis-block">
        <h3>다중모델 평가 <span class="muted" style="font-size:11px">／ 9개 모델 비교</span></h3>
        <table class="kpi-table">
          ${entries.map(([k, vv]) => `<tr><td>${modelLabel(k)}</td><td class="right">${fmt.bigKrw(vv)}</td></tr>`).join("")}
          <tr class="separator"><td>Median</td><td class="right"><b>${fmt.bigKrw(median)}</b></td></tr>
          <tr><td>적정주가 (가중평균)</td><td class="right"><b>${fmt.krw(v.fair_price)}</b></td></tr>
          <tr><td>상승여력</td><td class="right ${v.upside >= 0 ? 'pos' : 'neg'}"><b>${fmt.pct(v.upside)}</b></td></tr>
          <tr><td>등급</td><td class="right"><span class="rating-tag rating-${(v.rating||'').toLowerCase()}">${v.rating || '-'}</span></td></tr>
        </table>
      </div>
    `;
  } else {
    multiBlock = `<div class="card analysis-block muted">다중모델 평가 응답 실패</div>`;
  }

  // ─── 비교 분석 ─────────────────────────────────────────────
  let compareBlock = "";
  if (sy && val && val.valuation) {
    const syMid = sy.enterprise_mid || 0;
    const multiMidEntries = Object.values(val.valuation.by_model || {}).filter(v => v > 0);
    const multiMid = multiMidEntries.length ? medianOf(multiMidEntries) : 0;
    if (syMid > 0 && multiMid > 0) {
      const gap = (multiMid - syMid) / syMid;
      let interp;
      if (Math.abs(gap) < 0.20) interp = "두 모델 일치 — 신뢰도↑";
      else if (gap > 0.50)  interp = "다중모델이 더 낙관 — SY는 자산가치 보수";
      else if (gap < -0.50) interp = "SY가 더 낙관 — 다중모델은 수익성 보수";
      else interp = "두 모델 격차 보통 — 모델별 가정 차이";
      compareBlock = `
        <div class="card">
          <h3>📊 비교 분석</h3>
          <div class="muted" style="margin-bottom:6px">SY mid ${fmt.bigKrw(syMid)} vs 다중모델 median ${fmt.bigKrw(multiMid)}</div>
          <div style="font-size:13px">${escapeHtml(interp)}</div>
        </div>
      `;
    }
  }

  // ─── 뉴스 감성 / 변동성 ─────────────────────────────────────
  let sentBlock = "";
  if (rec && rec.recommendation) {
    const r = rec.recommendation;
    const sentScore = (r.news_sentiment || 0);
    const sentLabel = sentScore > 0.20 ? "긍정" : sentScore < -0.20 ? "부정" : "중립";
    const sentCls = sentScore > 0.20 ? "pos" : sentScore < -0.20 ? "neg" : "muted";
    sentBlock = `
      <div class="card">
        <h3>📰 시장 시그널</h3>
        <div class="grid-3">
          <div class="kpi"><div class="label">뉴스 감성</div>
            <div class="value ${sentCls}">${(sentScore * 100).toFixed(0)}</div>
            <div class="sub">${sentLabel} (-100 ~ +100)</div></div>
          <div class="kpi"><div class="label">변동성 (연환산)</div>
            <div class="value">${r.volatility_pct ? r.volatility_pct.toFixed(1) + '%' : '-'}</div>
            <div class="sub">일간 표준편차 × √252</div></div>
          <div class="kpi"><div class="label">호라이즌</div>
            <div class="value">${r.horizon || '-'}</div>
            <div class="sub">단기 / 장기 / 관망</div></div>
        </div>
      </div>
    `;
  }

  // ─── 의사결정 ───────────────────────────────────────────────
  let decBlock = "";
  if (rec && rec.recommendation) {
    const r = rec.recommendation;
    decBlock = `
      <div class="card">
        <h3>🎯 의사결정</h3>
        <div class="muted" style="margin-bottom:8px">호라이즌: <b>${escapeHtml(r.horizon || '-')}</b> · 액션: <b>${escapeHtml(r.action || '-')}</b> · 신뢰도: <b>${((r.confidence||0)*100).toFixed(0)}%</b></div>
        <table class="kpi-table">
          ${r.short_term_buy_zone   ? `<tr><td>매수 진입가</td><td class="right pos"><b>${fmt.krw(r.short_term_buy_zone)} 이하</b></td></tr>` : ""}
          ${r.short_term_sell_zone  ? `<tr><td>매도 목표가</td><td class="right"><b>${fmt.krw(r.short_term_sell_zone)}</b></td></tr>` : ""}
          ${r.stop_loss             ? `<tr><td>손절가</td><td class="right neg"><b>${fmt.krw(r.stop_loss)}</b></td></tr>` : ""}
        </table>
        ${r.long_term_thesis?.length ? `
          <h4 style="margin-top:14px">장기 투자 사유</h4>
          <ul class="thesis">${r.long_term_thesis.map(t => `<li>${escapeHtml(t)}</li>`).join("")}</ul>
        ` : ""}
        ${r.risks?.length ? `
          <h4 style="margin-top:14px">⚠ 리스크</h4>
          <ul class="risk-list">${r.risks.map(rk => `<li>${escapeHtml(rk)}</li>`).join("")}</ul>
        ` : ""}
      </div>
    `;
  }

  // ─── 헤더 KPI ───────────────────────────────────────────────
  const upside = sy?.upside_mid ?? val?.valuation?.upside ?? 0;
  const fairPrice = sy?.fair_price_mid ?? val?.valuation?.fair_price ?? 0;
  const rating = sy?.rating ?? val?.valuation?.rating ?? '-';

  return `
    <div class="grid-4">
      <div class="kpi"><div class="label">종목</div>
        <div class="value">${escapeHtml(name)}</div>
        <div class="sub">${escapeHtml(ticker)} · ${escapeHtml(sector)} · ${escapeHtml(market)}</div></div>
      <div class="kpi"><div class="label">현재가</div>
        <div class="value">${fmt.krw(price)}</div>
        <div class="sub">시총 ${fmt.bigKrw(mcap)}</div></div>
      <div class="kpi"><div class="label">적정가 (SY)</div>
        <div class="value">${fmt.krw(fairPrice)}</div>
        <div class="sub">3접근법 통합 mid</div></div>
      <div class="kpi"><div class="label">상승률</div>
        <div class="value ${upside>=0?'pos':'neg'}">${fmt.pct(upside)}</div>
        <div class="sub"><span class="rating-tag rating-${(rating||'').toLowerCase()}">${rating}</span></div></div>
    </div>

    <div class="grid-2">
      ${syBlock}
      ${multiBlock}
    </div>

    ${compareBlock}
    ${sentBlock}
    ${decBlock}
  `;
}

// 중앙값 (다중모델 비교용)
function medianOf(arr) {
  if (!arr || !arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m-1] + s[m]) / 2;
}

// ---------- Autocomplete ----------
function attachAutocomplete(input, onSelect) {
  if (!input || input.dataset.acAttached === "1") return;
  input.dataset.acAttached = "1";
  let dropdown = document.createElement("div");
  dropdown.className = "ac-dropdown";
  input.parentNode.style.position = "relative";
  input.parentNode.appendChild(dropdown);

  let timer = null;
  let activeIdx = -1;
  let items = [];

  const close = () => { dropdown.classList.remove("active"); activeIdx = -1; };
  const choose = (i) => {
    if (i < 0 || i >= items.length) return;
    const it = items[i];
    input.value = it.name;
    close();
    if (onSelect) onSelect(it);
  };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { close(); return; }
    timer = setTimeout(async () => {
      try {
        items = await api(`/api/search?q=${encodeURIComponent(q)}&limit=10`);
      } catch { items = []; }
      if (!items.length) { close(); return; }
      dropdown.innerHTML = items.map((it, i) => `
        <div class="ac-item" data-i="${i}">
          <div class="ac-name"><strong>${escapeHtml(it.name)}</strong></div>
          <div class="ac-meta">${escapeHtml(it.ticker)} · ${escapeHtml(it.exchange || '')} · ${escapeHtml(it.sector || '')}${it.asset === 'etf' ? ' · ETF' : ''}</div>
        </div>
      `).join("");
      dropdown.classList.add("active");
      activeIdx = -1;
      $$(".ac-item", dropdown).forEach(el => {
        el.addEventListener("mousedown", e => {
          e.preventDefault();
          choose(parseInt(el.dataset.i, 10));
        });
      });
    }, 150);
  });

  input.addEventListener("keydown", e => {
    if (!dropdown.classList.contains("active")) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, items.length - 1);
      $$(".ac-item", dropdown).forEach((el, i) => el.classList.toggle("active", i === activeIdx));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
      $$(".ac-item", dropdown).forEach((el, i) => el.classList.toggle("active", i === activeIdx));
    } else if (e.key === "Enter") {
      if (activeIdx >= 0) { e.preventDefault(); choose(activeIdx); }
    } else if (e.key === "Escape") {
      close();
    }
  });

  input.addEventListener("blur", () => setTimeout(close, 150));
}

// KST 변환은 UTC 밀리초에 +9h 더한 뒤 getUTC* 로 읽기만 하면 됨.
// (이전 버전은 KST 브라우저에서 getTimezoneOffset 을 한 번 더 빼는 바람에 +18h 가 적용되는 버그가 있었음.)
function _kst(dateOrTs) {
  const d = dateOrTs instanceof Date ? dateOrTs
    : (dateOrTs == null ? new Date() : new Date(typeof dateOrTs === "number" && dateOrTs < 1e12 ? dateOrTs * 1000 : dateOrTs));
  if (isNaN(d)) return null;
  return new Date(d.getTime() + 9 * 3600 * 1000);
}
function todayKST(dateOrTs) {
  const k = _kst(dateOrTs);
  if (!k) return "";
  const days = ["일", "월", "화", "수", "목", "금", "토"];
  return `${k.getUTCFullYear()}.${String(k.getUTCMonth()+1).padStart(2,'0')}.${String(k.getUTCDate()).padStart(2,'0')} (${days[k.getUTCDay()]})`;
}
function nowKST(dateOrTs) {
  const k = _kst(dateOrTs);
  if (!k) return "";
  return `${String(k.getUTCHours()).padStart(2,'0')}:${String(k.getUTCMinutes()).padStart(2,'0')} KST`;
}
function fmtDateKST(dateStr) {
  // RSS pubDate (예: "Thu, 07 May 2026 16:37:21 GMT") → "05.08 01:37 KST"
  const k = _kst(dateStr);
  if (!k) return dateStr || "";
  return `${String(k.getUTCMonth()+1).padStart(2,'0')}.${String(k.getUTCDate()).padStart(2,'0')} ${String(k.getUTCHours()).padStart(2,'0')}:${String(k.getUTCMinutes()).padStart(2,'0')} KST`;
}

// 데이터 조회 시점 뱃지 (카드/섹션 하단용)
function asOfLine(label, dateOrTs, extra) {
  const k = _kst(dateOrTs);
  const when = k ? `${todayKST(dateOrTs)} ${nowKST(dateOrTs)}` : "정적 샘플";
  return `<div class="as-of">📅 <strong>${label}</strong> ${when}${extra ? ` · ${extra}` : ""}</div>`;
}
// 여러 timestamp(초 또는 ms) 중 가장 최신 시각
function maxTimestamp(values) {
  let max = 0;
  for (const v of values) {
    if (!v) continue;
    const n = typeof v === "number" ? (v < 1e12 ? v * 1000 : v) : new Date(v).getTime();
    if (!isNaN(n) && n > max) max = n;
  }
  return max || null;
}

function metaStrip(...parts) {
  // 페이지 메타 — 오늘 일자만(시각 X). 데이터 조회시점은 각 카드 하단에 별도 표기.
  return `<div class="meta-strip"><span>${todayKST()}</span>${parts.length ? `<span class="dot">◆</span>${parts.map(p => `<span>${p}</span>`).join('<span class="dot">◆</span>')}` : ""}</div>`;
}

// ---------- DASHBOARD ----------
async function renderDashboard(root) {
  root.innerHTML = `
    <h1 class="page-title">시장을 한눈에<span class="muted">／ MARKET PULSE</span></h1>
    ${metaStrip('§01·DASHBOARD', '12 INDICATORS', 'NEWS · LIVE', 'TOP-5 SCREENER')}
    <p class="page-sub">주요 지수·환율·채권금리·원자재 시세 + 12개 시장 토픽 뉴스 + 저평가 Top5 미리보기. 5분 주기 자동 갱신.</p>

    <div id="commodGroups" class="loading">시세 불러오는 중…</div>

    <div class="card">
      <h3>저평가 Top 5 <a href="#/undervalued" style="float:right;font-size:12px">전체 보기 →</a></h3>
      <div id="under5" class="loading">불러오는 중…</div>
    </div>

    <h2 class="page-title" style="margin-top:24px">📊 시장 종합 뉴스</h2>
    <p class="page-sub">코스피 · 코스닥 · 미국/유럽/일본/중국 증시 · 환율 · 금리 · 채권 · 원유 · 원자재 · 농산물</p>
    <div id="marketNews" class="loading">불러오는 중…</div>
  `;

  api("/api/commodities").then(groups => {
    const html = Object.entries(groups).map(([name, list]) => {
      const latest = maxTimestamp(list.map(q => q.timestamp));
      return `
        <div class="card">
          <h3>${escapeHtml(name)} <span class="muted">(${list.length})</span></h3>
          ${renderQuoteTable(list)}
          ${asOfLine("시세", latest, "Yahoo Finance")}
        </div>
      `;
    }).join("");
    $("#commodGroups").innerHTML = html || `<div class="card error">시세 데이터를 불러오지 못했습니다 (네트워크/방화벽). 인터넷 연결된 환경에서 자동 채워집니다.</div>`;
  }).catch(e => {
    $("#commodGroups").innerHTML = `<div class="card error">${e.message}</div>`;
  });

  api("/api/undervalued?n=5").then(list => {
    if (!list.length) { $("#under5").innerHTML = `<div class="muted">조건을 만족하는 종목 없음</div>`; return; }
    const priceTs = maxTimestamp(list.map(r => r.price_as_of));
    $("#under5").innerHTML = renderScreenTable(list) + asOfLine("현재가", priceTs, "재무 DART 2025-12 결산 · 9모델 가중평균");
    bindRowClicks($("#under5"));
  }).catch(e => $("#under5").innerHTML = `<div class="error">${e.message}</div>`);

  // 시장 종합 뉴스 (12개 토픽). keepalive 워크플로우가 주기적으로 갱신하므로
  // 첫 사용자가 force refresh 트리거하지 않음 (콜드 시 외부 API 폭주 방지).
  api("/api/news/market?n=4").then(data => {
    const html = Object.entries(data).map(([topic, items]) => `
      <div class="card">
        <h3>${escapeHtml(topic)} <span class="muted" style="font-weight:400">(${items.length})</span></h3>
        ${items.length ? renderNewsList(items) : `<div class="muted">데이터 없음</div>`}
      </div>
    `).join("");
    $("#marketNews").innerHTML = html || `<div class="card error">시장 뉴스 로드 실패</div>`;
  }).catch(e => $("#marketNews").innerHTML = `<div class="card error">${e.message}</div>`);
}

function renderQuoteTable(list) {
  if (!list.length) return `<div class="muted">데이터 없음</div>`;
  return `<table>
    <thead><tr><th>종목</th><th>가격</th><th>등락</th></tr></thead>
    <tbody>${list.map(q => `
      <tr class="no-hover">
        <td>${escapeHtml(q.name)}</td>
        <td>${fmt.num(q.price, 2)} ${escapeHtml(q.currency || "")}</td>
        <td class="${q.change_pct >= 0 ? 'pos' : 'neg'}">${fmt.pct(q.change_pct/100)}</td>
      </tr>`).join("")}
    </tbody></table>`;
}

function renderNewsList(items) {
  if (!items || !items.length) return `<div class="muted">뉴스 없음 (네트워크 차단 가능성)</div>`;
  return `<ul class="news-list">${items.map(n => `
    <li>
      <div class="title"><a href="${n.link}" target="_blank" rel="noopener">${escapeHtml(n.title)}</a></div>
      <div class="meta">${escapeHtml(n.source || '')} · ${escapeHtml(fmtDateKST(n.published))}</div>
    </li>`).join("")}</ul>`;
}

// ---------- UNDERVALUED ----------
async function renderUndervalued(root) {
  root.innerHTML = `
    <h1 class="page-title">저평가 Top 10<span class="muted">／ 9-MODEL WEIGHTED FAIR PRICE</span></h1>
    ${metaStrip('§02·SCREENER', 'DCF · RIM · MULTIPLES', 'GRAHAM · LYNCH', 'QUANT FILTER')}
    <p class="page-sub">9개 모델 가중평균 적정주가 vs 현재가 디스카운트. 정량 필터(ROE ≥ 5% · 흑자 · 부채) 통과 + 상승여력(Upside) 높은 순 정렬.</p>
    <div class="card">
      <div style="display:flex;gap:12px;align-items:center;margin-bottom:12px">
        <span class="muted">KOSPI · KOSDAQ 보통주 전종목 기준 · 4시간마다 자동 갱신 (미리 계산된 결과를 즉시 표시).</span>
        <button onclick="reloadUnder()" style="margin-left:auto;padding:6px 12px;background:var(--bg-elev-2);color:var(--text);border:1px solid var(--line);border-radius:6px;cursor:pointer">새로고침</button>
      </div>
      <div id="undertable" class="loading">불러오는 중…</div>
    </div>
    <div class="card">
      <h3>스크리닝 기준</h3>
      <ul class="thesis">
        <li>적정주가 대비 상승여력 (Upside) > 0</li>
        <li>ROE ≥ 5% (자본효율성 확보)</li>
        <li>당기순이익 흑자</li>
        <li>순부채/EBITDA ≤ 4 (재무 건전성)</li>
        <li>정렬 = 상승여력(Upside) 높은 순 (점수 컬럼은 참고용)</li>
      </ul>
    </div>
  `;
  loadUnder();
}

window.reloadUnder = () => loadUnder();

async function loadUnder() {
  $("#undertable").innerHTML = `<div class="loading">불러오는 중…</div>`;
  try {
    const list = await api("/api/undervalued?n=10");
    if (!list.length) { $("#undertable").innerHTML = `<div class="muted">조건을 만족하는 종목 없음</div>`; return; }
    const priceTs = maxTimestamp(list.map(r => r.price_as_of));
    $("#undertable").innerHTML = renderScreenTable(list) + asOfLine("현재가", priceTs, "재무 DART 2025-12 결산 · 9모델 가중평균");
    bindRowClicks($("#undertable"));
  } catch (e) {
    $("#undertable").innerHTML = `<div class="error">${e.message}</div>`;
  }
}

function renderScreenTable(list) {
  return `<table>
    <thead><tr>
      <th>종목</th><th>섹터</th><th>현재가</th><th>적정가</th><th>상승여력</th>
      <th>ROE</th><th>PER</th><th>PBR</th><th>등급</th><th>점수</th>
    </tr></thead>
    <tbody>${list.map(r => {
      const v = r.valuation;
      const ratingCls = v.rating === "STRONG_BUY" ? "strong-buy" : v.rating === "BUY" ? "buy" : v.rating === "HOLD" ? "hold" : "sell";
      return `<tr data-q="${v.ticker}">
        <td><strong>${escapeHtml(v.name)}</strong> <span class="muted">${v.ticker}</span></td>
        <td class="muted">${escapeHtml(v.sector)}</td>
        <td>${fmt.krw(v.current_price)}</td>
        <td>${fmt.krw(v.fair_price)}</td>
        <td class="${v.upside >= 0 ? 'pos' : 'neg'}">${fmt.pct(v.upside)}</td>
        <td>${fmt.pct(r.roe || 0, 1)}</td>
        <td>${fmt.num(r.per_now, 1)}</td>
        <td>${fmt.num(r.pbr_now, 2)}</td>
        <td><span class="tag ${ratingCls}">${v.rating}</span></td>
        <td>${(r.score * 100).toFixed(1)}</td>
      </tr>`;
    }).join("")}</tbody></table>`;
}

function bindRowClicks(container) {
  container.querySelectorAll("tr[data-q]").forEach(tr => {
    tr.addEventListener("click", () => navigate("/search", { q: tr.dataset.q }));
  });
}

// ---------- SEARCH ----------
async function renderSearch(root, params) {
  const q = params.q || "";
  root.innerHTML = `
    <h1 class="page-title">기업 가치 평가<span class="muted">／ EQUITY VALUATION</span></h1>
    ${metaStrip('§03·VALUATION', 'KOSPI · KOSDAQ · US · ETF', 'AUTO-COMPLETE', '9 MODELS')}
    <p class="page-sub">국내/해외 주식 + ETF. 자동완성 검색 → 9개 모델 분포 + 가중평균 적정주가. 비샘플 종목은 Naver/Yahoo 실시간 데이터로 평가.</p>
    <form id="searchForm" class="page-search">
      <input id="qInp" type="text" value="${escapeHtml(q)}" placeholder="🔍 삼성전자, AAPL, QQQ, 005930 …" autocomplete="off">
      <button type="submit">평가</button>
    </form>
    <div id="searchResult"></div>
  `;
  const inp = $("#qInp");
  attachAutocomplete(inp, (item) => navigate("/search", { q: item.ticker }));
  $("#searchForm").addEventListener("submit", e => {
    e.preventDefault();
    const v = inp.value.trim();
    if (v) navigate("/search", { q: v });
  });
  if (q) loadSearch(q);
}

async function loadSearch(q) {
  const out = $("#searchResult");
  out.innerHTML = `<div class="loading">평가 중…</div>`;
  try {
    const data = await api(`/api/valuation?q=${encodeURIComponent(q)}`, { timeout: 15000 });
    if (data.error) {
      const sug = (data.suggestions || []).map(s => `
        <a href="#/search?q=${encodeURIComponent(s.ticker)}" class="suggest-pill">
          ${escapeHtml(s.name)} <span class="muted">${s.ticker}</span>
        </a>`).join(" ");
      out.innerHTML = `
        <div class="card error">${escapeHtml(data.error)}</div>
        ${sug ? `<div class="card"><div class="muted" style="margin-bottom:8px">유사 종목 추천:</div>${sug}</div>` : ""}
      `;
      return;
    }
    out.innerHTML = renderValuationDetail(data);
  } catch (e) {
    out.innerHTML = `<div class="error">${e.message}</div>`;
  }
}

function renderValuationDetail(data) {
  const f = data.financials;
  const v = data.valuation;
  const q = data.quote || null;
  const ratingCls = v.rating === "STRONG_BUY" ? "strong-buy" : v.rating === "BUY" ? "buy" : v.rating === "HOLD" ? "hold" : "sell";

  const liveBadge = data.live ? `<span class="tag" style="background:rgba(124,92,255,0.2);color:var(--accent-2);margin-left:8px">LIVE</span>` : "";
  const assetBadge = f.asset === "etf" ? `<span class="tag" style="background:rgba(245,166,35,0.2);color:var(--warn);margin-left:8px">ETF</span>` : "";
  const xchg = f.exchange ? `<span class="muted" style="margin-left:8px">${escapeHtml(f.exchange)}</span>` : "";

  let priceSubtext = "";
  if (q && q.traded_at) {
    const ts = new Date(q.traded_at);
    const timeStr = isNaN(ts) ? q.traded_at : ts.toLocaleString("ko-KR", { hour: "2-digit", minute: "2-digit", month: "numeric", day: "numeric" });
    const chgCls = q.change_pct >= 0 ? "pos" : "neg";
    const status = q.market_status === "OPEN" ? `<span class="pos">● 장중</span>` : (q.market_status === "CLOSE" ? "장마감" : (q.market_status || ""));
    priceSubtext = `<span class="${chgCls}">${q.change_pct >= 0 ? "+" : ""}${(q.change_pct||0).toFixed(2)}%</span> · ${timeStr} · ${status} · <span class="muted">${q.source || ""}</span>`;
  } else if (q === null || (q && !q.traded_at)) {
    priceSubtext = `<span class="muted">정적 샘플가 (실시간 fetch 실패)</span>`;
  }

  const allEntries = Object.entries(v.by_model || {}).map(([k, val]) => ({
    name: k, value: val, weight: (v.weights && v.weights[k]) || 0,
  }));
  const modelEntries = allEntries.filter(m => m.value > 0).sort((a, b) => b.weight - a.weight);
  const skippedCount = allEntries.length - modelEntries.length;
  const maxModelVal = Math.max(...modelEntries.map(m => m.value), 1);

  const priceFmt = f.exchange && !f.exchange.startsWith("KOS") ? (n) => "$" + fmt.num(n, 2) : fmt.krw;

  return `
    <div class="grid-4">
      <div class="kpi"><div class="label">종목</div><div class="value">${escapeHtml(f.name)} ${liveBadge}${assetBadge}</div><div class="sub">${f.ticker}${xchg} · ${escapeHtml(f.sector)}</div></div>
      <div class="kpi"><div class="label">현재가</div><div class="value">${priceFmt(f.current_price)}</div><div class="sub">${priceSubtext}</div></div>
      <div class="kpi"><div class="label">적정주가</div><div class="value">${priceFmt(v.fair_price)}</div><div class="sub">9개 모델 가중평균</div></div>
      <div class="kpi"><div class="label">상승여력</div><div class="value ${v.upside>=0?'pos':'neg'}">${fmt.pct(v.upside)}</div><div class="sub"><span class="tag ${ratingCls}">${v.rating}</span></div></div>
    </div>

    <div class="grid-2">
      <div class="card">
        <h3>모델별 적정주가 (weight 순)</h3>
        ${modelEntries.length ? modelEntries.map(m => `
          <div class="bar-h">
            <div class="name">${modelLabel(m.name)}</div>
            <div class="bar"><div class="fill" style="width:${(m.value / maxModelVal * 100).toFixed(1)}%"></div></div>
            <div class="val">${priceFmt(m.value)}</div>
            <div class="muted" style="width:50px;text-align:right">${(m.weight*100).toFixed(0)}%</div>
          </div>
        `).join("") : `<div class="muted">데이터 부족 — 산출 가능한 모델 없음</div>`}
        ${skippedCount > 0 ? `<div class="muted" style="margin-top:8px;font-size:11px">⚠ ${skippedCount}개 모델은 입력 데이터 부족으로 제외됨 (해외 종목 일부, 비샘플 종목)</div>` : ""}
        ${(v.notes || []).length ? `<div class="muted" style="margin-top:8px">${v.notes.join(" / ")}</div>` : ""}
      </div>

      <div class="card">
        <h3>핵심 재무 <span class="muted" style="font-size:11px;font-weight:400">("-" = 데이터 없음)</span></h3>
        <table>
          <tr class="no-hover"><td>EPS</td><td>${priceFmt(f.eps)}</td></tr>
          <tr class="no-hover"><td>BPS</td><td>${priceFmt(f.bps)}</td></tr>
          <tr class="no-hover"><td>ROE</td><td>${f.roe ? fmt.pct(f.roe, 2) : '-'}</td></tr>
          <tr class="no-hover"><td>EPS 성장률 추정</td><td>${f.growth_rate ? fmt.pct(f.growth_rate, 2) : '-'}</td></tr>
          <tr class="no-hover"><td>PER (현재)</td><td>${fmt.num(f.per_now)} <span class="muted">섹터 ${f.sector_per || '-'}</span></td></tr>
          <tr class="no-hover"><td>PBR (현재)</td><td>${fmt.num(f.pbr_now)} <span class="muted">섹터 ${f.sector_pbr || '-'}</span></td></tr>
          <tr class="no-hover"><td>EBITDA</td><td>${fmt.bigKrw(f.ebitda)}</td></tr>
          <tr class="no-hover"><td>FCF</td><td>${fmt.bigKrw(f.fcf)}</td></tr>
          <tr class="no-hover"><td>순부채</td><td>${f.net_debt ? fmt.bigKrw(f.net_debt) : '-'}</td></tr>
          <tr class="no-hover"><td>발행주식수</td><td>${f.shares_outstanding ? fmt.num(f.shares_outstanding, 0) + '주' : '-'}</td></tr>
        </table>
      </div>
    </div>

    <div class="card">
      <a href="#/recommend?q=${encodeURIComponent(f.ticker)}" style="display:inline-block;padding:10px 20px;background:var(--accent-2);color:#fff;border-radius:6px;font-weight:600">투자 추천 보기 →</a>
    </div>
  `;
}

function modelLabel(k) {
  const map = {
    dcf: "DCF", rim: "RIM", per: "PER 멀티플", pbr: "PBR 멀티플",
    psr: "PSR 멀티플", ev_ebitda: "EV/EBITDA", graham_number: "Graham#",
    graham_intrinsic: "Graham 본질가치", lynch: "Lynch (PEG=1)",
  };
  return map[k] || k;
}

// ---------- RECOMMEND ----------
async function renderRecommend(root, params) {
  const q = params.q || "";
  root.innerHTML = `
    <h1 class="page-title">투자 분석<span class="muted">／ INVESTMENT THESIS</span></h1>
    ${metaStrip('§04·ANALYSIS', 'SHORT-TERM · BUY/SELL/STOP', 'LONG-TERM · THESIS', 'NEWS SENTIMENT')}
    <p class="page-sub">가치평가 + 뉴스 감성 + 변동성 결합. 단기는 매수·매도·손절가, 장기는 정량 근거 + 리스크.</p>
    <div class="card">
      <form id="recForm" style="display:flex;gap:8px;position:relative">
        <input id="rqInp" type="text" value="${escapeHtml(q)}" placeholder="종목명, 코드, ETF 심볼 …" autocomplete="off"
          style="flex:1;padding:10px 12px;background:var(--bg-elev-2);border:1px solid var(--line);color:var(--text);border-radius:6px">
        <button type="submit" style="padding:10px 20px;background:var(--accent);color:#00322e;border:none;border-radius:6px;cursor:pointer;font-weight:600">분석</button>
      </form>
    </div>
    <div id="recResult"></div>
  `;
  const inp = $("#rqInp");
  attachAutocomplete(inp, (item) => navigate("/recommend", { q: item.ticker }));
  $("#recForm").addEventListener("submit", e => {
    e.preventDefault();
    const v = inp.value.trim();
    if (v) navigate("/recommend", { q: v });
  });
  if (q) loadRecommend(q);
}

async function loadRecommend(q) {
  const out = $("#recResult");
  out.innerHTML = `<div class="loading">분석 중… (가치평가 + 뉴스 감성 + 변동성)</div>`;
  try {
    const d = await api(`/api/recommend?q=${encodeURIComponent(q)}`, { timeout: 15000 });
    if (d.error) {
      const sug = (d.suggestions || []).map(s => `<a href="#/recommend?q=${encodeURIComponent(s.ticker)}" class="suggest-pill">${escapeHtml(s.name)} <span class="muted">${s.ticker}</span></a>`).join(" ");
      out.innerHTML = `<div class="card error">${escapeHtml(d.error)}</div>${sug?`<div class="card">${sug}</div>`:""}`;
      return;
    }
    out.innerHTML = renderRecommendation(d);
  } catch (e) {
    out.innerHTML = `<div class="error">${e.message}</div>`;
  }
}

function renderRecommendation(d) {
  const f = d.financials, v = d.valuation, r = d.recommendation;
  const ratingCls = r.action === "BUY" ? "buy" : r.action === "SELL" ? "sell" : "hold";
  const horizonColor = r.horizon.includes("장기") ? "var(--accent)" : r.horizon.includes("단기") ? "var(--accent-2)" : "var(--warn)";
  const news = (d.news || []).slice(0, 5);
  const priceFmt = f.exchange && !f.exchange.startsWith("KOS") ? (n) => "$" + fmt.num(n, 2) : fmt.krw;

  return `
    <div class="grid-4">
      <div class="kpi"><div class="label">종목</div><div class="value">${escapeHtml(f.name)}</div><div class="sub">${f.ticker} · ${escapeHtml(f.exchange||"")}</div></div>
      <div class="kpi"><div class="label">투자 호라이즌</div><div class="value" style="color:${horizonColor}">${escapeHtml(r.horizon)}</div><div class="sub">신뢰도 ${(r.confidence*100).toFixed(0)}%</div></div>
      <div class="kpi"><div class="label">행동</div><div class="value"><span class="tag ${ratingCls}">${r.action}</span></div></div>
      <div class="kpi"><div class="label">변동성 (연환산)</div><div class="value">${r.volatility_pct ? r.volatility_pct.toFixed(1) + '%' : '-'}</div><div class="sub">뉴스 감성 ${(r.news_sentiment*100).toFixed(0)}</div></div>
    </div>

    <div class="grid-2">
      <div class="card">
        <h3>📈 단기 매매 가격대</h3>
        <table>
          <tr class="no-hover"><td>현재가</td><td><strong>${priceFmt(f.current_price)}</strong></td></tr>
          <tr class="no-hover"><td>적정 매수 (Buy Zone)</td><td class="pos"><strong>≤ ${priceFmt(r.short_term_buy_zone)}</strong></td></tr>
          <tr class="no-hover"><td>적정 매도 (Sell Zone)</td><td class="warn"><strong>≥ ${priceFmt(r.short_term_sell_zone)}</strong></td></tr>
          <tr class="no-hover"><td>손절가 (Stop Loss)</td><td class="neg"><strong>${priceFmt(r.stop_loss)}</strong></td></tr>
        </table>
        <div class="muted" style="margin-top:8px">
          매수 = min(현재가, 적정가) × 0.95 / 매도 = 적정가 × 1.02 / 손절 = 매수 × 0.92
        </div>
      </div>

      <div class="card">
        <h3>🎯 장기 투자 사유</h3>
        <ul class="thesis">${r.long_term_thesis.map(t => `<li>${escapeHtml(t)}</li>`).join("")}</ul>
        ${r.risks.length ? `<h3 style="margin-top:14px">⚠ 리스크</h3><ul class="risk-list">${r.risks.map(rk => `<li>${escapeHtml(rk)}</li>`).join("")}</ul>` : ""}
      </div>
    </div>

    <div class="card">
      <h3>최근 뉴스 (감성분석 기반 입력)</h3>
      ${news.length ? renderNewsList(news) : `<div class="muted">뉴스 조회 실패 또는 결과 없음</div>`}
    </div>
  `;
}

// ---------- SY ANALYSIS (00 · 기업가치분석) ----------
// 단일 기업 — 검색 → 자동 데이터 수집(OpenDart + 네이버 + Yahoo) → CAPM/WACC/DCF/자산/상대 → 투자 등급.

const SY_RATING_TIERS = [
  { min:  0.30, code: "STRONG_BUY",  emoji: "🚀", label: "강력 매수" },
  { min:  0.15, code: "BUY",         emoji: "📈", label: "매수" },
  { min:  0.05, code: "ACCUMULATE",  emoji: "⬆️", label: "분할 매수" },
  { min: -0.05, code: "HOLD",        emoji: "➡️", label: "보유" },
  { min: -0.15, code: "REDUCE",      emoji: "⬇️", label: "비중 축소" },
  { min: -0.30, code: "SELL",        emoji: "📉", label: "매도" },
  { min: -Infinity, code: "STRONG_SELL", emoji: "💥", label: "강력 매도" },
];

function syRating(upside) {
  for (const t of SY_RATING_TIERS) {
    if (upside >= t.min) return t;
  }
  return SY_RATING_TIERS[SY_RATING_TIERS.length - 1];
}

async function renderSyAnalysis(root, params) {
  const q = params.q || "";
  root.innerHTML = `
    <h1 class="page-title">기업가치분석 (SY)<span class="muted">／ AUTO-DCF + ASSET + MARKET</span></h1>
    ${metaStrip('§00·SY-ANALYSIS', 'CAPM · WACC · DCF', 'OPENDART · NAVER · YAHOO', '7-TIER RATING')}
    <p class="page-sub">기업명 / 종목코드 입력 → OpenDart(재무) + 네이버 금융 + Yahoo Finance에서 자동 데이터 수집 → CAPM 자기자본비용 + WACC + DCF + 자산·상대가치 → 오늘 기준 투자 등급 산출.</p>

    <form id="syaForm" class="page-search">
      <input id="syaInp" type="text" value="${escapeHtml(q)}" placeholder="🔍 기업명 또는 종목코드 — 예: 삼성전자, 엠로, 005930" autocomplete="off">
      <button type="submit">평가</button>
    </form>
    <div class="muted" style="margin:-8px 0 16px;font-size:12px">
      사용자 입력 → 재무·주가·베타 자동 수집 → CAPM/WACC/DCF/자산/상대가치 자동 계산 → 오늘 기준 투자 판단 출력
    </div>

    <div id="syaResult"></div>
  `;
  const inp = $("#syaInp");
  attachAutocomplete(inp, (item) => navigate("/sy-analysis", { q: item.ticker }));
  $("#syaForm").addEventListener("submit", e => {
    e.preventDefault();
    const v = inp.value.trim();
    if (v) navigate("/sy-analysis", { q: v });
  });
  if (q) loadSyAnalysis(q);
}

async function loadSyAnalysis(q) {
  const out = $("#syaResult");
  out.innerHTML = `
    <div class="card loading">
      📥 데이터 수집 중…<br>
      <span class="muted" style="font-size:12px">OpenDart 재무제표 · 네이버/Yahoo 주가·베타 · 거시지표 (Rf · MRP · 세율)</span>
    </div>`;
  try {
    const d = await api(`/api/sy/evaluate?q=${encodeURIComponent(q)}`, { timeout: 15000 });
    if (d.error) {
      const sug = (d.suggestions || []).map(s =>
        `<a href="#/sy-analysis?q=${encodeURIComponent(s.ticker)}" class="suggest-pill">${escapeHtml(s.name)} <span class="muted">${s.ticker}</span></a>`
      ).join(" ");
      out.innerHTML = `
        <div class="card error">${escapeHtml(d.error)}</div>
        ${d.hint ? `<div class="card muted">${escapeHtml(d.hint)}</div>` : ""}
        ${sug ? `<div class="card">${sug}</div>` : ""}
      `;
      return;
    }
    out.innerHTML = renderSyAnalysisContent(d) +
      asOfLine("평가 기준일", d.price_as_of || Date.now(), "재무 DART 2025-12 · 자동 피어 멀티플");
    attachAccordionToggles(out);
  } catch (e) {
    out.innerHTML = `<div class="card error">${e.message}</div>`;
  }
}

function renderSyAnalysisContent(d) {
  const inp = d.inputs || {};
  const upside = d.upside_per_share || 0;
  const tier = syRating(upside);
  const ratingCls = tier.code === "STRONG_BUY" ? "strong-buy"
                  : tier.code === "BUY" || tier.code === "ACCUMULATE" ? "buy"
                  : tier.code === "HOLD" ? "hold"
                  : "sell";

  const dcfRows = (d.dcf_rows || []);   // 서버가 내려주면 표시, 없으면 생략
  const peers = inp.peers || [];

  // CAPM 분해 (서버에서 안 줄 경우 추정치 사용)
  const rf = (inp.risk_free_rate ?? 0.025);
  const mr = (inp.market_return ?? 0.0725);
  const mrp = mr - rf;
  const beta = inp.beta ?? (peers.length ? (peers.reduce((a,p)=>a+(p.beta_52w||1),0)/peers.length) : 1.0);
  const re = (inp.cost_of_equity ?? (rf + beta * mrp));
  const rd = (inp.cost_of_debt ?? 0);

  return `
    <div class="grid-4">
      <div class="kpi">
        <div class="label">종목</div>
        <div class="value">${escapeHtml(d.name)}</div>
        <div class="sub">${d.ticker} · ${escapeHtml(d.sector || "")}</div>
      </div>
      <div class="kpi">
        <div class="label">현재 주가</div>
        <div class="value">${fmt.krw(d.current_price)}</div>
        <div class="sub">시총 ${bigKrwAuto(d.market_cap)}</div>
      </div>
      <div class="kpi">
        <div class="label">⭐ 목표가 (적정주가)</div>
        <div class="value" style="color:var(--accent)">${fmt.krw(d.fair_price_mid)}</div>
        <div class="sub">${fmt.krw(d.fair_price_min)} ~ ${fmt.krw(d.fair_price_max)}</div>
      </div>
      <div class="kpi">
        <div class="label">상승률</div>
        <div class="value ${upside>=0?'pos':'neg'}">${fmt.pct(upside)}</div>
        <div class="sub"><span class="tag ${ratingCls}">${tier.emoji} ${tier.code}</span></div>
      </div>
    </div>

    <div class="card" style="background:rgba(79,209,197,0.06);border-color:rgba(79,209,197,0.3)">
      <h3>🎯 투자 등급 — ${tier.emoji} <strong>${tier.code}</strong> <span class="muted">(${tier.label})</span></h3>
      <table>
        <tr class="no-hover"><td>현재 주가</td><td><strong>${fmt.krw(d.current_price)}</strong></td></tr>
        <tr class="no-hover"><td>⭐ 목표가 (mid)</td><td><strong style="color:var(--accent)">${fmt.krw(d.fair_price_mid)}</strong></td></tr>
        <tr class="no-hover"><td>상승률</td><td class="${upside>=0?'pos':'neg'}"><strong>${fmt.pct(upside)}</strong></td></tr>
        <tr class="no-hover"><td>평가 기준일</td><td>${new Date().toLocaleString("ko-KR", {hour12:false})}</td></tr>
      </table>
      <div class="muted" style="margin-top:8px;font-size:12px">
        7-tier 등급 기준: STRONG_BUY ≥+30% · BUY ≥+15% · ACCUMULATE ≥+5% · HOLD ±5% · REDUCE ≥-15% · SELL ≥-30% · STRONG_SELL &lt;-30%
      </div>
    </div>

    <div class="grid-2">
      <div class="card">
        <h3>✅ 평가 지표 (CAPM · WACC)</h3>
        <table>
          <tr class="no-hover"><td>Rf (무위험수익률)</td><td>${(rf*100).toFixed(2)}%</td></tr>
          <tr class="no-hover"><td>MRP (시장위험프리미엄)</td><td>${(mrp*100).toFixed(2)}%</td></tr>
          <tr class="no-hover"><td>β (베타)</td><td>${beta.toFixed(2)}</td></tr>
          <tr class="no-hover"><td><strong>Re (자기자본비용)</strong></td><td><strong>${(re*100).toFixed(2)}%</strong></td></tr>
          <tr class="no-hover"><td>Rd (타인자본비용, 세후)</td><td>${rd>0?(rd*100).toFixed(2)+"%":"—"}</td></tr>
          <tr class="no-hover" style="background:var(--bg-elev-2);border-top:2px solid var(--accent)">
            <td><strong>WACC</strong></td>
            <td><strong style="color:var(--accent)">${(inp.wacc*100).toFixed(2)}%</strong></td>
          </tr>
          <tr class="no-hover"><td>기초 FCFF</td><td>${bigKrwAuto(inp.fcf)}</td></tr>
          <tr class="no-hover"><td>예측기간</td><td>${inp.forecast_years || 10}년 + 영구가치</td></tr>
          <tr class="no-hover"><td>단기/장기/영구 성장률</td><td>${(inp.growth_rate_short*100).toFixed(1)}% / ${(inp.growth_rate_long*100).toFixed(1)}% / ${(inp.terminal_growth*100).toFixed(1)}%</td></tr>
        </table>
      </div>

      <div class="card">
        <h3>💰 3접근법 기업가치</h3>
        <table>
          <thead><tr><th>접근법</th><th>중간값 <span class="muted" style="font-weight:400">／ 주당</span></th><th>vs 시총</th></tr></thead>
          <tbody>
            <tr class="no-hover">
              <td><strong>수익가치 (DCF)</strong><div class="muted">FCFF 10y + 영구가치</div></td>
              <td><strong>${bigKrwAuto(d.income_mid)}</strong><div class="muted" style="font-size:11px">주당 ${perShareKrw(d.income_mid, d.shares_outstanding)}</div></td>
              <td class="${d.income_mid > d.market_cap ? 'pos' : 'neg'}">${d.market_cap ? fmt.pct((d.income_mid - d.market_cap)/d.market_cap) : '-'}</td>
            </tr>
            <tr class="no-hover">
              <td><strong>자산가치</strong><div class="muted">순자산 · 청산가치 · 조정NAV</div></td>
              <td><strong>${bigKrwAuto(d.asset_book)}</strong><div class="muted" style="font-size:11px">주당 ${perShareKrw(d.asset_book, d.shares_outstanding)}</div></td>
              <td class="${d.asset_book > d.market_cap ? 'pos' : 'neg'}">${d.market_cap ? fmt.pct((d.asset_book - d.market_cap)/d.market_cap) : '-'}</td>
            </tr>
            <tr class="no-hover">
              <td><strong>상대가치</strong><div class="muted">PER · PBR · PSR · EV/EBITDA</div></td>
              <td><strong>${bigKrwAuto(d.market_mid)}</strong><div class="muted" style="font-size:11px">주당 ${perShareKrw(d.market_mid, d.shares_outstanding)}</div></td>
              <td class="${d.market_mid > d.market_cap ? 'pos' : 'neg'}">${d.market_cap ? fmt.pct((d.market_mid - d.market_cap)/d.market_cap) : '-'}</td>
            </tr>
            <tr class="no-hover" style="background:var(--bg-elev-2);border-top:2px solid var(--accent)">
              <td><strong>★ 종합 기업가치</strong></td>
              <td><strong style="color:var(--accent)">${bigKrwAuto(d.enterprise_mid)}</strong><div class="muted" style="font-size:11px">주당 ${perShareKrw(d.enterprise_mid, d.shares_outstanding)}</div></td>
              <td class="${d.upside_mid>=0?'pos':'neg'}"><strong>${fmt.pct(d.upside_mid)}</strong></td>
            </tr>
          </tbody>
        </table>
        <div style="margin-top:12px">
          <button class="accordion-toggle" data-target="#syDetailExpand">▼ 상세 모델별 산출 내역 + 피어 비교군 보기</button>
        </div>
      </div>
    </div>

    <div id="syDetailExpand" class="accordion-body" style="display:none">
      ${renderSyDetailSections(d)}
    </div>

    <div class="card">
      <h3>📥 자동 수집 데이터 (OpenDart + 네이버 + Yahoo)</h3>
      <div class="grid-2">
        <div>
          <h4 style="margin-bottom:6px">손익 (연간)</h4>
          <table>
            <tr class="no-hover"><td>매출액</td><td>${bigKrwAuto(inp.revenue)}</td></tr>
            <tr class="no-hover"><td>영업이익</td><td>${bigKrwAuto(inp.operating_income)}</td></tr>
            <tr class="no-hover"><td>당기순이익</td><td>${bigKrwAuto(inp.net_income)}</td></tr>
            <tr class="no-hover"><td>EBITDA</td><td>${bigKrwAuto(inp.ebitda)}</td></tr>
            <tr class="no-hover"><td>FCFF</td><td>${bigKrwAuto(inp.fcf)}</td></tr>
          </table>
        </div>
        <div>
          <h4 style="margin-bottom:6px">재무상태 · 시장</h4>
          <table>
            <tr class="no-hover"><td>자산총계</td><td>${bigKrwAuto(inp.total_assets)}</td></tr>
            <tr class="no-hover"><td>부채총계</td><td>${bigKrwAuto(inp.total_liabilities)}</td></tr>
            <tr class="no-hover"><td>자본총계 (순자산)</td><td>${bigKrwAuto(inp.total_equity)}</td></tr>
            <tr class="no-hover"><td>순부채</td><td>${bigKrwAuto(inp.net_debt)}</td></tr>
            <tr class="no-hover"><td>발행주식수</td><td>${fmt.num(d.shares_outstanding, 0)} 주</td></tr>
          </table>
        </div>
      </div>
    </div>
  `;
}

// ---------- SY ANALYSIS — 상세 펼침 영역 (02 단일 탭 accordion) ----------
// renderSyAnalysisContent 의 "▼ 상세 모델별 산출 내역" 버튼을 누르면 펼쳐지는 영역.
// 모델별 산출 + 피어 비교군 — renderSyDetailContent 에서 가져옴 (KPI/요약은 위에 이미 있어 생략).
function renderSyDetailSections(d) {
  const inp = d.inputs || {};
  const peers = inp.peers || [];
  return `
    <div class="grid-2">
      <div class="card">
        <h3>모델별 산출 내역</h3>
        <table>
          <thead><tr><th>접근법</th><th>방법</th><th class="text-right">기업가치</th></tr></thead>
          <tbody>
          ${(d.detail_rows || []).map(r => `
            <tr class="no-hover">
              <td class="muted">${escapeHtml(r.approach)}</td>
              <td>${escapeHtml(r.method)}</td>
              <td><strong>${bigKrwAuto(r.value)}</strong></td>
            </tr>`).join("")}
          </tbody>
        </table>
        ${(d.notes || []).length ? `<div class="muted" style="margin-top:8px">${d.notes.join(" / ")}</div>` : ""}
      </div>

      <div class="card">
        <h3>피어 비교군 (상대가치 산출 기준)</h3>
        <table>
          <thead><tr><th>피어</th><th>섹터</th><th>PER</th><th>PBR</th></tr></thead>
          <tbody>
          ${peers.length ? peers.map(p => `
            <tr class="no-hover">
              <td>${escapeHtml(p.name || '')}</td>
              <td class="muted">${escapeHtml(p.sector || '-')}</td>
              <td>${p.per ?? '-'}</td>
              <td>${p.pbr ?? '-'}</td>
            </tr>
          `).join("") : `<tr class="no-hover"><td colspan="4" class="muted">개별 피어 정보 없음 — 섹터 평균 멀티플 사용</td></tr>`}
            <tr class="no-hover" style="background:var(--bg-elev-2)">
              <td><strong>피어 평균 (사용값)</strong></td>
              <td class="muted">—</td>
              <td><strong>${inp.peer_per_avg?.toFixed(2) || '-'}</strong></td>
              <td><strong>${inp.peer_pbr_avg?.toFixed(2) || '-'}</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card" style="background:var(--bg-elev-2);font-size:12px">
      <h3 style="font-size:13px;margin-bottom:8px">투자 등급 기준</h3>
      <p class="muted" style="margin:0">
        STRONG_BUY ≥ +30% · BUY +15~30% · ACCUMULATE +5~15% · HOLD ±5% ·
        REDUCE -15~-5% · SELL -30~-15% · STRONG_SELL ≤ -30%
      </p>
    </div>
  `;
}

// 페이지 어디서든 .accordion-toggle 클릭 시 data-target 요소 펼침/접힘.
function attachAccordionToggles(scope) {
  (scope || document).querySelectorAll(".accordion-toggle").forEach(btn => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => {
      const sel = btn.dataset.target;
      const tgt = sel && document.querySelector(sel);
      if (!tgt) return;
      const open = tgt.style.display !== "none";
      tgt.style.display = open ? "none" : "block";
      btn.textContent = (open ? "▼ " : "▲ ") + btn.textContent.replace(/^[▼▲]\s*/, "");
    });
  });
}

// ---------- SY SCREENER ----------
function bigKrwAuto(n) {
  if (n === null || n === undefined) return "-";
  const abs = Math.abs(n);
  if (abs >= 1e12) return (n / 1e12).toFixed(2) + "조";
  if (abs >= 1e8)  return (n / 1e8).toFixed(0) + "억";
  return new Intl.NumberFormat("ko-KR").format(Math.round(n)) + "원";
}

// 기업가치(원) ÷ 발행주식수 = 주당 적정가. 값/주식수 없으면 '-'.
function perShareKrw(value, shares) {
  if (!value || !shares || shares <= 0) return "-";
  return fmt.krw(value / shares);
}

async function renderSyScreener(root) {
  root.innerHTML = `
    <h1 class="page-title">SY 평가법 저평가<span class="muted">／ 3-APPROACH SCREENER</span></h1>
    ${metaStrip('§05·SY-METHOD', 'INCOME · ASSET · MARKET', 'AUTO PEER GROUP', 'MIN / MID / MAX')}
    <p class="page-sub">수익가치 + 자산가치 + 상대가치 3접근법으로 기업가치 범위(min/mid/max) 산출 후 시총 비교. 자동 피어 그룹(같은 섹터+매출 비슷)으로 멀티플 계산. <strong>KOSPI·KOSDAQ 보통주 전종목 기준 · 4시간마다 자동 갱신.</strong></p>
    <div class="card" style="background:rgba(124,92,255,0.08);border-color:rgba(124,92,255,0.3)">
      <h3>저평가 Top10 과 무엇이 다른가?</h3>
      <table>
        <tr class="no-hover"><td><strong>Top 10</strong></td><td>주당 적정주가 (9 모델 가중평균) vs 현재가</td></tr>
        <tr class="no-hover"><td><strong>SY 평가법</strong></td><td>총 기업가치 범위 (3 접근법) vs 시가총액 — 자산가치 비중↑, 멀티플 비중↑</td></tr>
      </table>
    </div>
    <div class="card">
      <div class="muted" style="margin-bottom:8px">상승여력 = (종합 기업가치 평균값 − 시총) / 시총. 종합값 = 계산 가능한 접근법만 평균(2개면 ÷2).</div>
      <div id="sytable" class="loading">불러오는 중…</div>
    </div>
    <div class="card">
      <h3>SY 평가법 산출 식</h3>
      <ul class="thesis">
        <li><strong>수익가치</strong>: ① DCF (FCFF 10년 + 영구가치) ② EBITDA × 동종 EV/EBITDA ③ 영업이익 × 10배</li>
        <li><strong>자산가치</strong>: 자산총계 − 부채총계 (= 순자산), 청산가치 = 순자산 × 0.7</li>
        <li><strong>상대가치</strong>: ① PER × 순이익 ② PBR × 순자산 ③ PSR × 매출 ④ EV/EBITDA × EBITDA − 순부채</li>
        <li><strong>종합</strong>: 계산된 접근법만 평균(2개면 ÷2) → mid, 범위는 min / max → 시총 비교</li>
      </ul>
    </div>
  `;
  try {
    const list = await api("/api/sy/undervalued?n=20");
    if (!list.length) { $("#sytable").innerHTML = `<div class="muted">조건을 만족하는 종목 없음</div>`; return; }
    const priceTs = maxTimestamp(list.map(r => r.price_as_of));
    $("#sytable").innerHTML = renderSyScreenTable(list) + asOfLine("현재가", priceTs, "재무 DART 2025-12 결산 · 자동 피어그룹 멀티플");
    bindSyRowClicks($("#sytable"));
  } catch (e) {
    $("#sytable").innerHTML = `<div class="error">${e.message}</div>`;
  }
}

function renderSyScreenTable(list) {
  return `<table>
    <thead><tr>
      <th>종목</th><th>섹터</th><th>현재가</th>
      <th>⭐ SY 주당적정가</th><th>주당 상승여력</th>
      <th>시총</th><th>종합 기업가치</th>
      <th>등급</th>
    </tr></thead>
    <tbody>${list.map(r => {
      const ratingCls = r.rating === "STRONG_BUY" ? "strong-buy" : r.rating === "BUY" || r.rating === "ACCUMULATE" ? "buy" : r.rating === "HOLD" ? "hold" : "sell";
      return `<tr data-q="${r.ticker}">
        <td><strong>${escapeHtml(r.name)}</strong> <span class="muted">${r.ticker}</span></td>
        <td class="muted">${escapeHtml(r.sector)}</td>
        <td>${fmt.krw(r.current_price)}</td>
        <td><strong style="color:var(--accent)">${fmt.krw(r.fair_price_mid)}</strong></td>
        <td class="${r.upside_per_share >= 0 ? 'pos' : 'neg'}"><strong>${fmt.pct(r.upside_per_share)}</strong></td>
        <td>${bigKrwAuto(r.market_cap)}</td>
        <td>${bigKrwAuto(r.enterprise_mid)}</td>
        <td><span class="tag ${ratingCls}">${r.rating}</span></td>
      </tr>`;
    }).join("")}</tbody></table>`;
}

function bindSyRowClicks(container) {
  container.querySelectorAll("tr[data-q]").forEach(tr => {
    tr.addEventListener("click", () => navigate("/sy-detail", { q: tr.dataset.q }));
  });
}

// ---------- SY DETAIL ----------
async function renderSyDetail(root, params) {
  const q = params.q || "";
  root.innerHTML = `
    <h1 class="page-title">SY 평가법 가치평가<span class="muted">／ DETAILED ANALYSIS</span></h1>
    ${metaStrip('§06·SY-DETAIL', '3 APPROACHES', 'PEER GROUP', 'PER SHARE FAIR PRICE')}
    <p class="page-sub">한 기업을 수익·자산·상대 3접근법으로 종합 평가. 종합 기업가치 ÷ 발행주식수 = <strong>SY 주당적정가</strong> (03 가치평가의 9모델 가중평균 적정가와는 다른 산식).</p>
    <div class="card">
      <form id="syForm" style="display:flex;gap:8px;position:relative">
        <input id="syInp" type="text" value="${escapeHtml(q)}" placeholder="삼성전자, 엠로, 005930 …" autocomplete="off"
          style="flex:1;padding:10px 12px;background:var(--bg-elev-2);border:1px solid var(--line);color:var(--text);border-radius:6px;font-size:14px">
        <button type="submit" style="padding:10px 20px;background:var(--accent);color:#00322e;border:none;border-radius:6px;cursor:pointer;font-weight:600">분석</button>
      </form>
    </div>
    <div id="syResult"></div>
  `;
  const inp = $("#syInp");
  attachAutocomplete(inp, (item) => navigate("/sy-detail", { q: item.ticker }));
  $("#syForm").addEventListener("submit", e => {
    e.preventDefault();
    const v = inp.value.trim();
    if (v) navigate("/sy-detail", { q: v });
  });
  if (q) loadSyDetail(q);
}

async function loadSyDetail(q) {
  const out = $("#syResult");
  out.innerHTML = `<div class="loading">SY 평가법으로 분석 중…</div>`;
  try {
    const d = await api(`/api/sy/evaluate?q=${encodeURIComponent(q)}`, { timeout: 15000 });
    if (d.error) {
      const sug = (d.suggestions || []).map(s => `<a href="#/sy-detail?q=${encodeURIComponent(s.ticker)}" class="suggest-pill">${escapeHtml(s.name)} <span class="muted">${s.ticker}</span></a>`).join(" ");
      out.innerHTML = `
        <div class="card error">${escapeHtml(d.error)}</div>
        ${d.hint ? `<div class="card muted">${escapeHtml(d.hint)}</div>` : ""}
        ${sug ? `<div class="card">${sug}</div>` : ""}
      `;
      return;
    }
    out.innerHTML = renderSyDetailContent(d) + asOfLine("현재가", d.price_as_of, "재무 DART 2025-12 결산 · 피어 멀티플 sample 고정");
  } catch (e) {
    out.innerHTML = `<div class="error">${e.message}</div>`;
  }
}

function renderSyDetailContent(d) {
  const ratingCls = d.rating === "STRONG_BUY" ? "strong-buy" : d.rating === "BUY" || d.rating === "ACCUMULATE" ? "buy" : d.rating === "HOLD" ? "hold" : "sell";
  const inp = d.inputs || {};
  const peers = inp.peers || [];

  return `
    <div class="grid-4">
      <div class="kpi"><div class="label">종목</div><div class="value">${escapeHtml(d.name)}</div><div class="sub">${d.ticker} · ${escapeHtml(d.sector)}</div></div>
      <div class="kpi"><div class="label">현재가</div><div class="value">${fmt.krw(d.current_price)}</div><div class="sub">시총 ${bigKrwAuto(d.market_cap)}</div></div>
      <div class="kpi"><div class="label">⭐ SY 주당적정가 (mid)</div><div class="value" style="color:var(--accent)">${fmt.krw(d.fair_price_mid)}</div><div class="sub">${fmt.krw(d.fair_price_min)} ~ ${fmt.krw(d.fair_price_max)}</div></div>
      <div class="kpi"><div class="label">상승여력</div><div class="value ${d.upside_per_share>=0?'pos':'neg'}">${fmt.pct(d.upside_per_share)}</div><div class="sub"><span class="tag ${ratingCls}">${d.rating}</span></div></div>
    </div>

    <div class="card" style="background:rgba(79,209,197,0.06)">
      <h3>⭐ SY 주당적정가 = 종합 기업가치 ÷ 발행주식수</h3>
      <table>
        <tr class="no-hover"><td>종합 기업가치 (mid)</td><td><strong>${bigKrwAuto(d.enterprise_mid)}</strong></td></tr>
        <tr class="no-hover"><td>÷ 발행주식수</td><td>${fmt.num(d.shares_outstanding, 0)} 주</td></tr>
        <tr class="no-hover" style="background:var(--bg-elev-2)"><td><strong>= SY 주당적정가</strong></td><td><strong style="color:var(--accent)">${fmt.krw(d.fair_price_mid)}</strong></td></tr>
        <tr class="no-hover"><td>현재가</td><td>${fmt.krw(d.current_price)}</td></tr>
        <tr class="no-hover"><td>주당 상승여력</td><td class="${d.upside_per_share>=0?'pos':'neg'}"><strong>${fmt.pct(d.upside_per_share)}</strong></td></tr>
      </table>
    </div>

    <div class="card">
      <h3>3접근법 결과</h3>
      <table>
        <thead><tr><th>접근법</th><th>min</th><th>중간</th><th>max</th><th>vs 시총</th></tr></thead>
        <tbody>
          <tr class="no-hover">
            <td><strong>수익가치접근법</strong></td>
            <td>${bigKrwAuto(d.income_min)}</td>
            <td><strong>${bigKrwAuto(d.income_mid)}</strong><div class="muted" style="font-size:10px">주당 ${perShareKrw(d.income_mid, d.shares_outstanding)}</div></td>
            <td>${bigKrwAuto(d.income_max)}</td>
            <td class="${d.income_mid > d.market_cap ? 'pos' : 'neg'}">${d.market_cap ? fmt.pct((d.income_mid - d.market_cap)/d.market_cap) : '-'}</td>
          </tr>
          <tr class="no-hover">
            <td><strong>자산가치접근법</strong></td>
            <td>${bigKrwAuto(d.asset_liquidation)}</td>
            <td><strong>${bigKrwAuto(d.asset_book)}</strong><div class="muted" style="font-size:10px">주당 ${perShareKrw(d.asset_book, d.shares_outstanding)}</div></td>
            <td>${bigKrwAuto(d.asset_book)}</td>
            <td class="${d.asset_book > d.market_cap ? 'pos' : 'neg'}">${d.market_cap ? fmt.pct((d.asset_book - d.market_cap)/d.market_cap) : '-'}</td>
          </tr>
          <tr class="no-hover">
            <td><strong>상대가치접근법</strong></td>
            <td>${bigKrwAuto(d.market_min)}</td>
            <td><strong>${bigKrwAuto(d.market_mid)}</strong><div class="muted" style="font-size:10px">주당 ${perShareKrw(d.market_mid, d.shares_outstanding)}</div></td>
            <td>${bigKrwAuto(d.market_max)}</td>
            <td class="${d.market_mid > d.market_cap ? 'pos' : 'neg'}">${d.market_cap ? fmt.pct((d.market_mid - d.market_cap)/d.market_cap) : '-'}</td>
          </tr>
          <tr class="no-hover" style="border-top:2px solid var(--accent);background:var(--bg-elev-2)">
            <td><strong>★ 종합 기업가치</strong></td>
            <td>${bigKrwAuto(d.enterprise_min)}</td>
            <td><strong style="color:var(--accent)">${bigKrwAuto(d.enterprise_mid)}</strong><div class="muted" style="font-size:10px">주당 ${perShareKrw(d.enterprise_mid, d.shares_outstanding)}</div></td>
            <td>${bigKrwAuto(d.enterprise_max)}</td>
            <td class="${d.upside_mid>=0?'pos':'neg'}"><strong>${fmt.pct(d.upside_mid)}</strong></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="grid-2">
      <div class="card">
        <h3>모델별 산출 내역</h3>
        <table>
          <thead><tr><th>접근법</th><th>방법</th><th class="text-right">기업가치</th></tr></thead>
          <tbody>
          ${d.detail_rows.map(r => `
            <tr class="no-hover">
              <td class="muted">${escapeHtml(r.approach)}</td>
              <td>${escapeHtml(r.method)}</td>
              <td><strong>${bigKrwAuto(r.value)}</strong></td>
            </tr>`).join("")}
          </tbody>
        </table>
        ${(d.notes || []).length ? `<div class="muted" style="margin-top:8px">${d.notes.join(" / ")}</div>` : ""}
      </div>

      <div class="card">
        <h3>입력값 요약</h3>
        <table>
          <tr class="no-hover"><td>매출</td><td>${bigKrwAuto(inp.revenue)}</td></tr>
          <tr class="no-hover"><td>영업이익</td><td>${bigKrwAuto(inp.operating_income)}</td></tr>
          <tr class="no-hover"><td>당기순이익</td><td>${bigKrwAuto(inp.net_income)}</td></tr>
          <tr class="no-hover"><td>EBITDA</td><td>${bigKrwAuto(inp.ebitda)}</td></tr>
          <tr class="no-hover"><td>FCFF</td><td>${bigKrwAuto(inp.fcf)}</td></tr>
          <tr class="no-hover"><td>자산총계</td><td>${bigKrwAuto(inp.total_assets)}</td></tr>
          <tr class="no-hover"><td>부채총계</td><td>${bigKrwAuto(inp.total_liabilities)}</td></tr>
          <tr class="no-hover"><td>순자산</td><td>${bigKrwAuto(inp.total_equity)}</td></tr>
          <tr class="no-hover"><td>순부채</td><td>${bigKrwAuto(inp.net_debt)}</td></tr>
          <tr class="no-hover"><td>WACC</td><td><strong>${(inp.wacc*100).toFixed(2)}%</strong> <span class="muted" style="font-size:11px">(Rf ${(inp.risk_free_rate*100).toFixed(2)}% + β ${inp.beta?.toFixed(2)} × MRP ${(inp.market_risk_premium*100).toFixed(2)}%)</span></td></tr>
          <tr class="no-hover"><td>실효세율 (Tc)</td><td>${(inp.tax_rate*100).toFixed(1)}%</td></tr>
          <tr class="no-hover"><td>단기 성장률 (1~5y)</td><td>${(inp.growth_rate_short*100).toFixed(1)}% <span class="muted" style="font-size:11px">= ROE × (1 - 배당성향 ${(inp.dividend_payout_ratio*100).toFixed(0)}%)</span></td></tr>
          <tr class="no-hover"><td>장기 성장률 (6~10y)</td><td>${(inp.growth_rate_long*100).toFixed(1)}%</td></tr>
          <tr class="no-hover"><td>영구 성장률</td><td>${(inp.terminal_growth*100).toFixed(1)}%</td></tr>
          <tr class="no-hover"><td>예측기간</td><td>${inp.forecast_years}년</td></tr>
        </table>
      </div>
    </div>

    <div class="card">
      <h3>피어 비교군 (상대가치 산출 기준)</h3>
      <table>
        <thead><tr><th>피어</th><th>PER</th><th>PBR</th><th>52W β</th></tr></thead>
        <tbody>
        ${peers.length ? peers.map(p => `
          <tr class="no-hover">
            <td>${escapeHtml(p.name || '')}</td>
            <td>${p.per ?? '-'}</td>
            <td>${p.pbr ?? '-'}</td>
            <td>${p.beta_52w ?? '-'}</td>
          </tr>
        `).join("") : `<tr class="no-hover"><td colspan="4" class="muted">개별 피어 정보 없음 — 섹터 평균 멀티플 사용</td></tr>`}
          <tr class="no-hover" style="background:var(--bg-elev-2)">
            <td><strong>피어 평균 (사용값)</strong></td>
            <td><strong>${inp.peer_per_avg?.toFixed(2)}</strong></td>
            <td><strong>${inp.peer_pbr_avg?.toFixed(2)}</strong></td>
            <td>—</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card" style="background:var(--bg-elev-2);font-size:12px">
      <h3 style="font-size:13px;margin-bottom:8px">투자 등급 기준 <span class="muted" style="font-weight:400">／ RATING THRESHOLDS</span></h3>
      <p class="muted" style="margin:0 0 8px">주당 상승여력 = (SY 주당적정가 − 현재가) ÷ 현재가. 아래 구간별 등급 부여.</p>
      <table style="font-size:12px">
        <thead><tr><th style="width:18%">등급</th><th style="width:22%">기준 (상승여력)</th><th>해석</th></tr></thead>
        <tbody>
          <tr class="no-hover"><td><span class="tag strong-buy">STRONG_BUY</span></td><td><strong>≥ +30%</strong></td><td>강한 저평가 — 적극 매수 권고</td></tr>
          <tr class="no-hover"><td><span class="tag buy">BUY</span></td><td>+15% ~ +30%</td><td>저평가 — 매수 권고</td></tr>
          <tr class="no-hover"><td><span class="tag buy">ACCUMULATE</span></td><td>+5% ~ +15%</td><td>소폭 저평가 — 분할 매수</td></tr>
          <tr class="no-hover"><td><span class="tag hold">HOLD</span></td><td>−5% ~ +5%</td><td>적정가 — 보유</td></tr>
          <tr class="no-hover"><td><span class="tag sell">REDUCE</span></td><td>−15% ~ −5%</td><td>소폭 고평가 — 비중 축소</td></tr>
          <tr class="no-hover"><td><span class="tag sell">SELL</span></td><td>−30% ~ −15%</td><td>고평가 — 매도 권고</td></tr>
          <tr class="no-hover"><td><span class="tag sell">STRONG_SELL</span></td><td>&lt; −30%</td><td>강한 고평가 — 즉시 매도</td></tr>
        </tbody>
      </table>
      <p class="muted" style="margin:8px 0 0;font-size:11px">※ 이 등급은 SY 평가법(3접근법 종합) 기반 알고리즘 산출값입니다. 시장 변동성·이슈·뉴스 등은 별도 고려 필요.</p>
    </div>
  `;
}

// ---------- NEWS (topical) ----------
async function renderNews(root) {
  root.innerHTML = `
    <h1 class="page-title">토픽 뉴스<span class="muted">／ 22 TOPICS</span></h1>
    ${metaStrip('§08·NEWS', 'POLICY · FINANCE', 'INDUSTRY · TECH', 'BING NEWS RSS · 1H CACHE')}
    <p class="page-sub">금융 · 부동산 · 정부/경제/청년/주택정책 · 청약 / 반도체 · 2차전지 · AI · 바이오 · 자동차 · 조선·방산 · IT · 글로벌 / 가상자산 · 세제 · 노동 · 복지.</p>
    <div id="topics" class="loading">불러오는 중…</div>
  `;
  try {
    const data = await api("/api/news/topics?n=5");
    const html = Object.entries(data).map(([topic, items]) => `
      <div class="card">
        <h3>📰 ${escapeHtml(topic)} <span class="muted" style="font-weight:400">(${items.length})</span></h3>
        ${renderNewsList(items)}
      </div>
    `).join("");
    $("#topics").innerHTML = html || `<div class="card error">뉴스를 불러오지 못했습니다 (네트워크 차단 가능).</div>`;
  } catch (e) {
    $("#topics").innerHTML = `<div class="card error">${e.message}</div>`;
  }
}

// ---------- ANALYTICS ----------
async function renderAnalytics(root) {
  root.innerHTML = `
    <h1 class="page-title">Admin Console<span class="muted">／ OPERATIONS</span></h1>
    ${typeof metaStrip === 'function' ? metaStrip('OWNER ONLY', 'PRIVATE', 'INTERNAL') : ''}
    <p class="page-sub">운영자 전용 화면 (인증 필요).</p>

    <div class="card" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <span class="muted" style="font-family:var(--mono);font-size:11px;letter-spacing:0.05em">PERIOD:</span>
      <button data-hr="1"   onclick="loadAnalytics(1)"   class="aprd-btn">1H</button>
      <button data-hr="24"  onclick="loadAnalytics(24)"  class="aprd-btn active">24H</button>
      <button data-hr="168" onclick="loadAnalytics(168)" class="aprd-btn">7D</button>
      <button data-hr="720" onclick="loadAnalytics(720)" class="aprd-btn">30D</button>
      <button data-hr="8760" onclick="loadAnalytics(8760)" class="aprd-btn">ALL</button>
      <a href="#/analytics" onclick="loadAnalytics(24);return false" style="margin-left:auto;font-family:var(--mono);font-size:11px;letter-spacing:0.05em;text-transform:uppercase">↻ Refresh</a>
    </div>

    <div id="anaKpis"></div>
    <div id="anaCharts"></div>
    <div id="anaRecent"></div>
  `;
  // 버튼 스타일 동적 추가
  if (!document.getElementById('aprd-style')) {
    const s = document.createElement('style');
    s.id = 'aprd-style';
    s.textContent = `
      .aprd-btn { padding:6px 14px; background:var(--bg); color:var(--text); border:1px solid var(--line); font-family:var(--mono); font-size:11px; letter-spacing:0.05em; cursor:pointer; }
      .aprd-btn.active { background:var(--text); color:var(--bg); border-color:var(--text); }
      .aprd-btn:hover { background:var(--bg-elev-2); }
    `;
    document.head.appendChild(s);
  }
  loadAnalytics(24);
}
window.loadAnalytics = loadAnalytics;

async function loadAnalytics(hours) {
  document.querySelectorAll('.aprd-btn').forEach(b => b.classList.toggle('active', String(b.dataset.hr) === String(hours)));
  const kpiBox = $("#anaKpis");
  const chartBox = $("#anaCharts");
  const recentBox = $("#anaRecent");
  if (kpiBox) kpiBox.innerHTML = `<div class="loading">불러오는 중…</div>`;
  if (chartBox) chartBox.innerHTML = "";
  if (recentBox) recentBox.innerHTML = "";

  try {
    const [s, recent] = await Promise.all([
      api(`/api/admin/analytics/summary?hours=${hours}`),
      api(`/api/admin/analytics/recent?n=100`),
    ]);

    // KPIs
    kpiBox.innerHTML = `
      <div class="grid-4">
        <div class="kpi"><div class="label">Total requests (${hours}h)</div><div class="value">${fmt.num(s.total, 0)}</div></div>
        <div class="kpi"><div class="label">Unique IPs</div><div class="value">${fmt.num(s.unique_ips, 0)}</div></div>
        <div class="kpi"><div class="label">Unique paths</div><div class="value">${fmt.num(s.unique_paths, 0)}</div></div>
        <div class="kpi"><div class="label">Req per IP</div><div class="value">${s.unique_ips ? (s.total/s.unique_ips).toFixed(1) : '-'}</div></div>
      </div>
    `;

    // Charts
    chartBox.innerHTML = `
      <div class="grid-2">
        <div class="card">
          <h3>Hourly traffic (KST)</h3>
          ${renderHourlyChart(s.hourly_kst || [])}
        </div>
        <div class="card">
          <h3>Daily traffic (last 7d)</h3>
          ${renderDailyChart(s.daily || [])}
        </div>
      </div>
      <div class="grid-2">
        <div class="card">
          <h3>Top paths</h3>
          ${renderRankBars(s.top_paths || [], 'path')}
        </div>
        <div class="card">
          <h3>Top IPs</h3>
          ${renderRankBars(s.top_ips || [], 'ip')}
        </div>
      </div>
      <div class="grid-3">
        <div class="card">
          <h3>디바이스</h3>
          ${renderPieList(s.devices || {})}
        </div>
        <div class="card">
          <h3>운영체제</h3>
          ${renderPieList(s.os || {})}
        </div>
        <div class="card">
          <h3>브라우저</h3>
          ${renderPieList(s.browsers || {})}
        </div>
      </div>
    `;

    // Recent log
    recentBox.innerHTML = `
      <div class="card">
        <h3>Recent requests (${recent.length})</h3>
        <div style="max-height:500px;overflow-y:auto">
          <table>
            <thead><tr><th>시각</th><th>페이지</th><th>IP</th><th>디바이스</th><th>OS</th><th>브라우저</th><th>상태</th></tr></thead>
            <tbody>${recent.map(r => `
              <tr class="no-hover">
                <td><code style="font-size:11px">${escapeHtml(r.ts)}</code></td>
                <td><code style="font-size:11px">${escapeHtml(r.path)}</code></td>
                <td><code style="font-size:11px">${escapeHtml(r.ip || '-')}</code></td>
                <td>${escapeHtml(r.device || '-')}</td>
                <td>${escapeHtml(r.os || '-')}</td>
                <td>${escapeHtml(r.browser || '-')}</td>
                <td class="${r.status >= 400 ? 'neg' : ''}">${r.status}</td>
              </tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  } catch (e) {
    kpiBox.innerHTML = `<div class="card error">${e.message}</div>`;
  }
}

function renderHourlyChart(rows) {
  if (!rows.length) return `<div class="muted">데이터 없음</div>`;
  const map = new Map(rows.map(r => [r.hour, r.count]));
  const max = Math.max(...rows.map(r => r.count), 1);
  // 0~23시 전체 표시
  let html = `<div style="display:flex;align-items:flex-end;gap:2px;height:140px;padding:8px 0;border-bottom:1px solid var(--line)">`;
  for (let h = 0; h < 24; h++) {
    const c = map.get(h) || 0;
    const pct = (c / max * 100).toFixed(1);
    html += `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px" title="${h}시: ${c}">
      <div style="width:100%;height:${pct}%;background:var(--text);min-height:${c?'2px':'0'}"></div>
    </div>`;
  }
  html += `</div>`;
  html += `<div style="display:flex;justify-content:space-between;font-family:var(--mono);font-size:10px;color:var(--text-dim);margin-top:4px">
    <span>0시</span><span>6시</span><span>12시</span><span>18시</span><span>23시</span>
  </div>`;
  return html;
}

function renderDailyChart(rows) {
  if (!rows.length) return `<div class="muted">데이터 없음</div>`;
  const max = Math.max(...rows.map(r => r.count), 1);
  return `<table>
    <thead><tr><th>Date</th><th>Req</th><th>Unique</th><th></th></tr></thead>
    <tbody>${rows.map(r => `
      <tr class="no-hover">
        <td><code style="font-size:11px">${escapeHtml(r.date)}</code></td>
        <td>${r.count}</td>
        <td class="muted">${r.unique}</td>
        <td style="width:50%"><div style="height:6px;background:var(--bg-elev-2);position:relative"><div style="height:100%;background:var(--text);width:${(r.count/max*100).toFixed(1)}%"></div></div></td>
      </tr>`).join("")}
    </tbody>
  </table>`;
}

function renderRankBars(rows, keyField) {
  if (!rows.length) return `<div class="muted">데이터 없음</div>`;
  const max = Math.max(...rows.map(r => r.count), 1);
  return `<table>
    <tbody>${rows.map(r => `
      <tr class="no-hover">
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><code style="font-size:11px">${escapeHtml(r[keyField])}</code></td>
        <td style="width:60px;text-align:right">${r.count}</td>
        <td style="width:50%"><div style="height:6px;background:var(--bg-elev-2)"><div style="height:100%;background:var(--text);width:${(r.count/max*100).toFixed(1)}%"></div></div></td>
      </tr>`).join("")}
    </tbody>
  </table>`;
}

function renderPieList(obj) {
  const entries = Object.entries(obj).sort(([,a],[,b]) => b-a);
  if (!entries.length) return `<div class="muted">데이터 없음</div>`;
  const total = entries.reduce((s, [, c]) => s + c, 0);
  return entries.map(([k, c]) => `
    <div style="display:flex;align-items:center;gap:8px;margin:4px 0">
      <div style="flex:1;font-size:12px">${escapeHtml(k)}</div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--text-dim);width:50px;text-align:right">${(c/total*100).toFixed(0)}%</div>
      <div style="width:80px"><div style="height:6px;background:var(--bg-elev-2)"><div style="height:100%;background:var(--text);width:${(c/total*100).toFixed(1)}%"></div></div></div>
      <div style="font-family:var(--mono);font-size:11px;width:30px;text-align:right">${c}</div>
    </div>
  `).join("");
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, c => (
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]
  ));
}
