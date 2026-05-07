// SY Valuation — vanilla JS SPA
// Routes:
//   #/dashboard
//   #/undervalued
//   #/search?q=<query>
//   #/recommend?q=<query>
//   #/news

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

const fmt = {
  krw(n) {
    if (n === null || n === undefined || isNaN(n)) return "-";
    return new Intl.NumberFormat("ko-KR").format(Math.round(n)) + "원";
  },
  num(n, d = 2) {
    if (n === null || n === undefined || isNaN(n)) return "-";
    return Number(n).toLocaleString("ko-KR", { minimumFractionDigits: 0, maximumFractionDigits: d });
  },
  pct(n, d = 2) {
    if (n === null || n === undefined || isNaN(n)) return "-";
    const v = (Number(n) * 100).toFixed(d);
    return (Number(n) >= 0 ? "+" : "") + v + "%";
  },
  bigKrw(n) {
    if (!n) return "-";
    const abs = Math.abs(n);
    if (abs >= 1e12) return (n / 1e12).toFixed(2) + "조원";
    if (abs >= 1e8) return (n / 1e8).toFixed(0) + "억원";
    return new Intl.NumberFormat("ko-KR").format(Math.round(n)) + "원";
  },
};

async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
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
});

function initHeader() {
  const inp = $("#globalSearch");
  attachAutocomplete(inp, (item) => navigate("/search", { q: item.ticker }));
  $("#globalSearchBtn").addEventListener("click", () => {
    const q = inp.value.trim();
    if (q) navigate("/search", { q });
  });
  inp.addEventListener("keydown", e => {
    if (e.key === "Enter" && !$(".ac-dropdown.active")) {
      const q = inp.value.trim();
      if (q) navigate("/search", { q });
    }
  });

  api("/api/health").then(h => {
    const flags = [];
    flags.push(`종목 ${h.tickers_loaded}개 (정확평가 ${h.samples_loaded})`);
    flags.push(h.dart_enabled ? "DART ✓" : "DART ✗");
    flags.push(h.naver_news_enabled ? "Naver ✓" : "Naver(RSS)");
    $("#status").textContent = flags.join(" · ");
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

async function render() {
  const { path, params } = parseRoute();
  const root = $("#content");
  if (path.startsWith("/dashboard"))   { setActiveNav("dashboard");   return renderDashboard(root); }
  if (path.startsWith("/undervalued")) { setActiveNav("undervalued"); return renderUndervalued(root); }
  if (path.startsWith("/search"))      { setActiveNav("search");      return renderSearch(root, params); }
  if (path.startsWith("/recommend"))   { setActiveNav("recommend");   return renderRecommend(root, params); }
  if (path.startsWith("/sy-screener")) { setActiveNav("sy-screener"); return renderSyScreener(root); }
  if (path.startsWith("/sy-detail"))   { setActiveNav("sy-detail");   return renderSyDetail(root, params); }
  if (path.startsWith("/news"))        { setActiveNav("news");        return renderNews(root); }
  root.innerHTML = `<div class="error">알 수 없는 페이지: ${path}</div>`;
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

// ---------- DASHBOARD ----------
async function renderDashboard(root) {
  root.innerHTML = `
    <h1 class="page-title">대시보드</h1>
    <p class="page-sub">주요 지수, 환율, 채권금리, 원자재, 가상자산 + 토픽별 시장뉴스 + 저평가 Top5.</p>

    <div id="commodGroups" class="loading">시세 불러오는 중…</div>

    <div class="card">
      <h3>저평가 Top 5 <a href="#/undervalued" style="float:right;font-size:12px">전체 보기 →</a></h3>
      <div id="under5" class="loading">불러오는 중…</div>
    </div>

    <div class="card">
      <h3>시장 뉴스 (전체) <span id="senti" class="muted"></span></h3>
      <div id="news" class="loading">불러오는 중…</div>
    </div>
  `;

  api("/api/commodities").then(groups => {
    const html = Object.entries(groups).map(([name, list]) => `
      <div class="card">
        <h3>${escapeHtml(name)} <span class="muted">(${list.length})</span></h3>
        ${renderQuoteTable(list)}
      </div>
    `).join("");
    $("#commodGroups").innerHTML = html || `<div class="card error">시세 데이터를 불러오지 못했습니다 (네트워크/방화벽). 인터넷 연결된 환경에서 자동 채워집니다.</div>`;
  }).catch(e => {
    $("#commodGroups").innerHTML = `<div class="card error">${e.message}</div>`;
  });

  api("/api/undervalued?n=5").then(list => {
    if (!list.length) { $("#under5").innerHTML = `<div class="muted">조건을 만족하는 종목 없음</div>`; return; }
    $("#under5").innerHTML = renderScreenTable(list);
    bindRowClicks($("#under5"));
  }).catch(e => $("#under5").innerHTML = `<div class="error">${e.message}</div>`);

  api("/api/market-news?n=8").then(d => {
    const s = d.sentiment;
    const cls = s.score > 0.1 ? "pos" : (s.score < -0.1 ? "neg" : "muted");
    $("#senti").innerHTML = `· 감성지수 <span class="${cls}">${(s.score*100).toFixed(0)}</span> (긍정 ${s.positive} / 부정 ${s.negative})`;
    $("#news").innerHTML = renderNewsList(d.items);
  }).catch(e => $("#news").innerHTML = `<div class="error">${e.message}</div>`);
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
      <div class="meta">${escapeHtml(n.source || '')} · ${escapeHtml(n.published || '')}</div>
    </li>`).join("")}</ul>`;
}

// ---------- UNDERVALUED ----------
async function renderUndervalued(root) {
  root.innerHTML = `
    <h1 class="page-title">저평가 Top 10 <span class="muted" style="font-size:13px">(주당 적정주가 기준)</span></h1>
    <p class="page-sub">DCF·RIM·PER·PBR·PSR·EV/EBITDA·Graham·Lynch <strong>9개 모델 가중평균</strong>으로 산출한 <strong>주당 적정주가</strong> 대비 현재가 디스카운트. 정량 필터(ROE≥5%, 흑자, 부채) 통과 종목.</p>
    <div class="card">
      <div style="display:flex;gap:12px;align-items:center;margin-bottom:12px">
        <span class="muted">정확평가가 가능한 한국 블루칩 표본 기반. DART 연동 시 실제 재무로 자동 교체됨.</span>
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
        <li>점수 = 0.6×Upside + 0.2×ROE + 0.2×(1 − PBR/섹터PBR)</li>
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
    $("#undertable").innerHTML = renderScreenTable(list);
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
    <h1 class="page-title">종목 가치평가</h1>
    <p class="page-sub">국내/해외 주식 + ETF. 입력 중 자동완성 — 샘플에 없는 종목은 Yahoo Finance 실시간 데이터로 평가.</p>
    <div class="card">
      <form id="searchForm" style="display:flex;gap:8px;position:relative">
        <input id="qInp" type="text" value="${escapeHtml(q)}" placeholder="삼성전자, AAPL, QQQ, 005930 …" autocomplete="off"
          style="flex:1;padding:10px 12px;background:var(--bg-elev-2);border:1px solid var(--line);color:var(--text);border-radius:6px;font-size:14px">
        <button type="submit" style="padding:10px 20px;background:var(--accent);color:#00322e;border:none;border-radius:6px;cursor:pointer;font-weight:600">평가</button>
      </form>
    </div>
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
    const data = await api(`/api/valuation?q=${encodeURIComponent(q)}`);
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

  const modelEntries = Object.entries(v.by_model || {}).map(([k, val]) => ({
    name: k, value: val, weight: (v.weights && v.weights[k]) || 0,
  })).sort((a, b) => b.weight - a.weight);
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
        ${modelEntries.map(m => `
          <div class="bar-h">
            <div class="name">${modelLabel(m.name)}</div>
            <div class="bar"><div class="fill" style="width:${(m.value / maxModelVal * 100).toFixed(1)}%"></div></div>
            <div class="val">${priceFmt(m.value)}</div>
            <div class="muted" style="width:50px;text-align:right">${(m.weight*100).toFixed(0)}%</div>
          </div>
        `).join("")}
        ${(v.notes || []).length ? `<div class="muted" style="margin-top:8px">${v.notes.join(" / ")}</div>` : ""}
      </div>

      <div class="card">
        <h3>핵심 재무</h3>
        <table>
          <tr class="no-hover"><td>EPS</td><td>${priceFmt(f.eps)}</td></tr>
          <tr class="no-hover"><td>BPS</td><td>${priceFmt(f.bps)}</td></tr>
          <tr class="no-hover"><td>ROE</td><td>${fmt.pct(f.roe, 2)}</td></tr>
          <tr class="no-hover"><td>EPS 성장률 추정</td><td>${fmt.pct(f.growth_rate, 2)}</td></tr>
          <tr class="no-hover"><td>PER (현재)</td><td>${fmt.num(f.per_now)} <span class="muted">섹터 ${f.sector_per}</span></td></tr>
          <tr class="no-hover"><td>PBR (현재)</td><td>${fmt.num(f.pbr_now)} <span class="muted">섹터 ${f.sector_pbr}</span></td></tr>
          <tr class="no-hover"><td>EBITDA</td><td>${fmt.bigKrw(f.ebitda)}</td></tr>
          <tr class="no-hover"><td>FCF</td><td>${fmt.bigKrw(f.fcf)}</td></tr>
          <tr class="no-hover"><td>순부채</td><td>${fmt.bigKrw(f.net_debt)}</td></tr>
          <tr class="no-hover"><td>발행주식수</td><td>${fmt.num(f.shares_outstanding, 0)}주</td></tr>
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
    <h1 class="page-title">투자 추천</h1>
    <p class="page-sub">가치평가 + 뉴스 감성 + 변동성. 단기는 매수/매도/손절가, 장기는 투자 사유.</p>
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
    const d = await api(`/api/recommend?q=${encodeURIComponent(q)}`);
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

// ---------- SY SCREENER ----------
function bigKrwAuto(n) {
  if (n === null || n === undefined) return "-";
  const abs = Math.abs(n);
  if (abs >= 1e12) return (n / 1e12).toFixed(2) + "조";
  if (abs >= 1e8)  return (n / 1e8).toFixed(0) + "억";
  return new Intl.NumberFormat("ko-KR").format(Math.round(n)) + "원";
}

async function renderSyScreener(root) {
  root.innerHTML = `
    <h1 class="page-title">⭐ SY 평가법 저평가 종목 <span class="muted" style="font-size:13px">(기업가치 vs 시총)</span></h1>
    <p class="page-sub"><strong>수익가치 + 자산가치 + 상대가치</strong> 3접근법으로 <strong>기업가치 범위(min/mid/max)</strong> 산출 후 시가총액과 비교. 자동 피어 그룹(같은 섹터+매출 비슷한 기업)으로 멀티플 계산.</p>
    <div class="card" style="background:rgba(124,92,255,0.08);border-color:rgba(124,92,255,0.3)">
      <h3>저평가 Top10 과 무엇이 다른가?</h3>
      <table>
        <tr class="no-hover"><td><strong>Top 10</strong></td><td>주당 적정주가 (9 모델 가중평균) vs 현재가</td></tr>
        <tr class="no-hover"><td><strong>SY 평가법</strong></td><td>총 기업가치 범위 (3 접근법) vs 시가총액 — 자산가치 비중↑, 멀티플 비중↑</td></tr>
      </table>
    </div>
    <div class="card">
      <div class="muted" style="margin-bottom:8px">상승여력 = (종합 기업가치 중간값 − 시총) / 시총.</div>
      <div id="sytable" class="loading">불러오는 중…</div>
    </div>
    <div class="card">
      <h3>SY 평가법 산출 식</h3>
      <ul class="thesis">
        <li><strong>수익가치</strong>: ① DCF (FCFF 10년 + 영구가치) ② EBITDA × 동종 EV/EBITDA ③ 영업이익 × 10배</li>
        <li><strong>자산가치</strong>: 자산총계 − 부채총계 (= 순자산), 청산가치 = 순자산 × 0.7</li>
        <li><strong>상대가치</strong>: ① PER × 순이익 ② PBR × 순자산 ③ PSR × 매출 ④ EV/EBITDA × EBITDA − 순부채</li>
        <li><strong>종합</strong>: 3접근법의 min / median / max → 시총 비교</li>
      </ul>
    </div>
  `;
  try {
    const list = await api("/api/sy/undervalued?n=20");
    if (!list.length) { $("#sytable").innerHTML = `<div class="muted">조건을 만족하는 종목 없음</div>`; return; }
    $("#sytable").innerHTML = renderSyScreenTable(list);
    bindSyRowClicks($("#sytable"));
  } catch (e) {
    $("#sytable").innerHTML = `<div class="error">${e.message}</div>`;
  }
}

function renderSyScreenTable(list) {
  return `<table>
    <thead><tr>
      <th>종목</th><th>섹터</th><th>시총</th>
      <th>수익가치</th><th>자산가치</th><th>상대가치</th>
      <th>종합 (min ~ mid ~ max)</th><th>상승여력 (mid)</th><th>등급</th>
    </tr></thead>
    <tbody>${list.map(r => {
      const ratingCls = r.rating === "STRONG_BUY" ? "strong-buy" : r.rating === "BUY" || r.rating === "ACCUMULATE" ? "buy" : r.rating === "HOLD" ? "hold" : "sell";
      return `<tr data-q="${r.ticker}">
        <td><strong>${escapeHtml(r.name)}</strong> <span class="muted">${r.ticker}</span></td>
        <td class="muted">${escapeHtml(r.sector)}</td>
        <td>${bigKrwAuto(r.market_cap)}</td>
        <td>${bigKrwAuto(r.income_mid)}</td>
        <td>${bigKrwAuto(r.asset_book)}</td>
        <td>${bigKrwAuto(r.market_mid)}</td>
        <td>${bigKrwAuto(r.enterprise_min)} ~ <strong>${bigKrwAuto(r.enterprise_mid)}</strong> ~ ${bigKrwAuto(r.enterprise_max)}</td>
        <td class="${r.upside_mid >= 0 ? 'pos' : 'neg'}">${fmt.pct(r.upside_mid)}</td>
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
    <h1 class="page-title">📋 SY 평가법 상세 분석</h1>
    <p class="page-sub">한 기업을 수익·자산·상대 3접근법으로 종합 평가.</p>
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
    const d = await api(`/api/sy/evaluate?q=${encodeURIComponent(q)}`);
    if (d.error) {
      const sug = (d.suggestions || []).map(s => `<a href="#/sy-detail?q=${encodeURIComponent(s.ticker)}" class="suggest-pill">${escapeHtml(s.name)} <span class="muted">${s.ticker}</span></a>`).join(" ");
      out.innerHTML = `
        <div class="card error">${escapeHtml(d.error)}</div>
        ${d.hint ? `<div class="card muted">${escapeHtml(d.hint)}</div>` : ""}
        ${sug ? `<div class="card">${sug}</div>` : ""}
      `;
      return;
    }
    out.innerHTML = renderSyDetailContent(d);
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
      <div class="kpi"><div class="label">시가총액</div><div class="value">${bigKrwAuto(d.market_cap)}</div></div>
      <div class="kpi"><div class="label">종합 기업가치 (mid)</div><div class="value">${bigKrwAuto(d.enterprise_mid)}</div><div class="sub">${bigKrwAuto(d.enterprise_min)} ~ ${bigKrwAuto(d.enterprise_max)}</div></div>
      <div class="kpi"><div class="label">상승여력 (mid)</div><div class="value ${d.upside_mid>=0?'pos':'neg'}">${fmt.pct(d.upside_mid)}</div><div class="sub"><span class="tag ${ratingCls}">${d.rating}</span></div></div>
    </div>

    <div class="card">
      <h3>3접근법 결과</h3>
      <table>
        <thead><tr><th>접근법</th><th>min</th><th>중간</th><th>max</th><th>vs 시총</th></tr></thead>
        <tbody>
          <tr class="no-hover">
            <td><strong>수익가치접근법</strong></td>
            <td>${bigKrwAuto(d.income_min)}</td>
            <td><strong>${bigKrwAuto(d.income_mid)}</strong></td>
            <td>${bigKrwAuto(d.income_max)}</td>
            <td class="${d.income_mid > d.market_cap ? 'pos' : 'neg'}">${d.market_cap ? fmt.pct((d.income_mid - d.market_cap)/d.market_cap) : '-'}</td>
          </tr>
          <tr class="no-hover">
            <td><strong>자산가치접근법</strong></td>
            <td>${bigKrwAuto(d.asset_liquidation)}</td>
            <td><strong>${bigKrwAuto(d.asset_book)}</strong></td>
            <td>${bigKrwAuto(d.asset_book)}</td>
            <td class="${d.asset_book > d.market_cap ? 'pos' : 'neg'}">${d.market_cap ? fmt.pct((d.asset_book - d.market_cap)/d.market_cap) : '-'}</td>
          </tr>
          <tr class="no-hover">
            <td><strong>상대가치접근법</strong></td>
            <td>${bigKrwAuto(d.market_min)}</td>
            <td><strong>${bigKrwAuto(d.market_mid)}</strong></td>
            <td>${bigKrwAuto(d.market_max)}</td>
            <td class="${d.market_mid > d.market_cap ? 'pos' : 'neg'}">${d.market_cap ? fmt.pct((d.market_mid - d.market_cap)/d.market_cap) : '-'}</td>
          </tr>
          <tr class="no-hover" style="border-top:2px solid var(--accent);background:var(--bg-elev-2)">
            <td><strong>★ 종합 기업가치</strong></td>
            <td>${bigKrwAuto(d.enterprise_min)}</td>
            <td><strong style="color:var(--accent)">${bigKrwAuto(d.enterprise_mid)}</strong></td>
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
          <tr class="no-hover"><td>WACC</td><td>${(inp.wacc*100).toFixed(2)}%</td></tr>
          <tr class="no-hover"><td>단기 성장률</td><td>${(inp.growth_rate_short*100).toFixed(1)}%</td></tr>
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
  `;
}

// ---------- NEWS (topical) ----------
async function renderNews(root) {
  root.innerHTML = `
    <h1 class="page-title">시장 뉴스 (토픽별)</h1>
    <p class="page-sub">코스피·코스닥·미국증시·환율·금리·원유·반도체·2차전지·AI·부동산·가상자산·ETF.</p>
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

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, c => (
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]
  ));
}
