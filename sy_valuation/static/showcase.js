// SY Valuation — B2B 쇼케이스 계층 (app.js 뒤에 로드)
//
//  1) API 콘솔      : 앱이 실제로 보낸 모든 API 호출을 기록해 curl / MCP tool call / 응답 JSON 으로 보여준다.
//                     "이 화면은 이 호출 하나로 만들어졌다"를 시연 중에 그대로 증명.
//  2) 가정 시뮬레이터 : #/sim — WACC·성장률·멀티플을 바꾸면 POST /api/v1/valuations/compute 로 즉시 재계산.
//                     상장사(ticker) 와 직접 입력(비상장·딜 타깃) 두 모드.
//
// app.js 의 전역($, $$, fmt, escapeHtml, attachAutocomplete, navigate, metaStrip)을 사용한다.

(function () {
  "use strict";

  // ───────────────────────── 공통 ─────────────────────────
  const apiKey = () => { try { return localStorage.getItem("sy_api_key") || ""; } catch { return ""; } };
  const isB2B = (path) => path.startsWith("/api/v1/") || path === "/mcp";
  const esc = (s) => escapeHtml(String(s ?? ""));
  const pretty = (text) => { try { return JSON.stringify(JSON.parse(text), null, 2); } catch { return text || ""; } };

  async function copyText(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
      if (btn) { const old = btn.textContent; btn.textContent = "복사됨"; setTimeout(() => (btn.textContent = old), 1200); }
    } catch { /* 클립보드 권한 없음 — 무시 */ }
  }

  // ───────────────────────── 1) API 콘솔 ─────────────────────────
  const LOG = [];
  const MAX_LOG = 40;
  let seq = 0, drawerOpen = false, openEntryId = null, openTab = "curl", mcpInfo = null;

  const origFetch = window.fetch.bind(window);
  window.fetch = async function (input, init = {}) {
    let path;
    try {
      const u = new URL(typeof input === "string" ? input : input.url, location.origin);
      if (u.origin !== location.origin) return origFetch(input, init);
      path = u.pathname + u.search;
    } catch { return origFetch(input, init); }

    const tracked = (path.startsWith("/api/") || path === "/mcp")
      && !/^\/api\/(admin\/|ping|health|prefetch)/.test(path);
    if (!tracked) return origFetch(input, init);

    if (isB2B(path.split("?")[0]) && apiKey()) {
      init = { ...init, headers: { ...(init.headers || {}), Authorization: "Bearer " + apiKey() } };
    }
    const entry = {
      id: ++seq, method: (init.method || "GET").toUpperCase(), path,
      body: typeof init.body === "string" ? init.body : null,
      status: null, ms: null, text: null, t0: performance.now(),
    };
    LOG.unshift(entry);
    if (LOG.length > MAX_LOG) LOG.pop();
    refreshConsole();
    try {
      const res = await origFetch(input, init);
      entry.status = res.status;
      entry.ms = Math.round(performance.now() - entry.t0);
      res.clone().text().then(t => { entry.text = t; refreshConsole(); }).catch(() => {});
      refreshConsole();
      return res;
    } catch (e) {
      entry.status = "ERR";
      entry.ms = Math.round(performance.now() - entry.t0);
      refreshConsole();
      throw e;
    }
  };

  // REST 호출 → 동등한 MCP tool call
  function toMcpCall(entry) {
    const [p, qs] = entry.path.split("?");
    const q = new URLSearchParams(qs || "");
    if (p === "/api/sy/evaluate") return { name: "get_valuation", arguments: { ticker: q.get("q") || "" } };
    if (p === "/api/search") return { name: "search_company", arguments: { query: q.get("q") || "" } };
    if (p === "/api/sy/undervalued") return { name: "screen_undervalued", arguments: { n: Number(q.get("n") || 10) } };
    if (p === "/api/v1/valuations/compute" && entry.body) {
      try { return { name: "compute_valuation", arguments: JSON.parse(entry.body) }; } catch { return null; }
    }
    if (p === "/mcp" && entry.body) {
      try { const m = JSON.parse(entry.body); if (m.method === "tools/call") return m.params; } catch {}
    }
    return null;
  }

  function curlOf(entry) {
    const lines = [`curl -X ${entry.method} '${location.origin}${entry.path}'`];
    if (isB2B(entry.path.split("?")[0])) lines.push(`  -H 'Authorization: Bearer $SY_API_KEY'`);
    if (entry.body) {
      lines.push(`  -H 'Content-Type: application/json'`);
      lines.push(`  -d '${entry.body.replace(/'/g, "'\\''")}'`);
    }
    return lines.join(" \\\n");
  }

  function mcpOf(entry) {
    const call = toMcpCall(entry);
    if (!call) return null;
    return JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: call }, null, 2);
  }

  function ensureConsoleDom() {
    if ($("#apiFab")) return;
    const fab = document.createElement("button");
    fab.id = "apiFab";
    fab.className = "api-fab";
    fab.setAttribute("aria-label", "API 콘솔 열기");
    fab.addEventListener("click", () => { drawerOpen = !drawerOpen; refreshConsole(); });
    document.body.appendChild(fab);

    const drawer = document.createElement("aside");
    drawer.id = "apiDrawer";
    drawer.className = "api-drawer";
    document.body.appendChild(drawer);

    drawer.addEventListener("click", (e) => {
      const t = e.target.closest("[data-act]");
      if (!t) return;
      const act = t.dataset.act;
      if (act === "close") { drawerOpen = false; }
      else if (act === "toggle") { const id = Number(t.dataset.id); openEntryId = openEntryId === id ? null : id; }
      else if (act === "tab") { openTab = t.dataset.tab; }
      else if (act === "copy") { return copyText($("#apiCode")?.textContent || "", t); }
      else if (act === "copy-mcp-config") { return copyText($("#mcpConfig")?.textContent || "", t); }
      else if (act === "mcp-test") { return runMcpTest(); }
      else if (act === "clear") { LOG.length = 0; openEntryId = null; }
      refreshConsole();
    });
    drawer.addEventListener("change", (e) => {
      if (e.target.id === "apiKeyInp") {
        try {
          const v = e.target.value.trim();
          if (v) localStorage.setItem("sy_api_key", v); else localStorage.removeItem("sy_api_key");
        } catch {}
      }
    });
  }

  async function runMcpTest() {
    mcpInfo = { loading: true };
    refreshConsole();
    const rpc = (id, method, params) => fetch("/mcp", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id, method, params: params || {} }),
    }).then(r => r.json());
    try {
      const init = await rpc(1, "initialize", {
        protocolVersion: "2025-06-18", capabilities: {},
        clientInfo: { name: "sy-showcase-console", version: "1.0.0" },
      });
      if (init.error) throw new Error(init.error.message);
      const list = await rpc(2, "tools/list");
      if (list.error) throw new Error(list.error.message);
      mcpInfo = { server: init.result.serverInfo, version: init.result.protocolVersion, tools: list.result.tools };
    } catch (e) {
      mcpInfo = { error: e.message || String(e) };
    }
    refreshConsole();
  }

  function mcpPanelHtml() {
    const config = JSON.stringify({ mcpServers: { "sy-valuation": { type: "http", url: location.origin + "/mcp" } } }, null, 2);
    let body = "";
    if (mcpInfo?.loading) body = `<div class="muted">MCP 서버에 연결 중…</div>`;
    else if (mcpInfo?.error) body = `<div class="error">연결 실패: ${esc(mcpInfo.error)}</div>`;
    else if (mcpInfo?.tools) {
      body = `
        <div class="api-ok">연결됨 · ${esc(mcpInfo.server?.title || mcpInfo.server?.name)} · protocol ${esc(mcpInfo.version)}</div>
        <ul class="mcp-tools">
          ${mcpInfo.tools.map(t => `<li><code>${esc(t.name)}</code><span>${esc(t.description)}</span></li>`).join("")}
        </ul>
        <div class="api-sub">사내 에이전트 설정에 아래만 추가하면 연동 끝</div>
        <pre id="mcpConfig" class="api-code">${esc(config)}</pre>
        <button class="api-btn" data-act="copy-mcp-config">설정 복사</button>`;
    }
    return `
      <div class="api-mcp">
        <div class="api-mcp-head">
          <b>MCP 서버</b><code>${esc(location.origin)}/mcp</code>
          <button class="api-btn" data-act="mcp-test">연결 테스트</button>
        </div>
        ${body}
      </div>`;
  }

  function entryHtml(e) {
    const open = e.id === openEntryId;
    const ok = typeof e.status === "number" && e.status < 400;
    const size = e.text != null ? (e.text.length / 1024).toFixed(1) + "KB" : "";
    const meta = e.status == null ? "…" : `${e.status} · ${e.ms}ms${size ? " · " + size : ""}`;
    let detail = "";
    if (open) {
      const mcp = mcpOf(e);
      const tab = openTab === "mcp" && !mcp ? "curl" : openTab;
      let code;
      if (tab === "curl") code = curlOf(e);
      else if (tab === "mcp") code = mcp;
      else code = e.text == null ? "(응답 대기 중)" : pretty(e.text).slice(0, 30000);
      detail = `
        <div class="api-detail">
          <div class="api-tabs">
            <button data-act="tab" data-tab="curl" class="${tab === "curl" ? "on" : ""}">REST (curl)</button>
            <button data-act="tab" data-tab="mcp" class="${tab === "mcp" ? "on" : ""}" ${mcp ? "" : "disabled title='MCP 도구 미제공 엔드포인트'"}>MCP tool call</button>
            <button data-act="tab" data-tab="res" class="${tab === "res" ? "on" : ""}">응답 JSON</button>
            <button class="api-btn right" data-act="copy">복사</button>
          </div>
          <pre id="apiCode" class="api-code">${esc(code)}</pre>
        </div>`;
    }
    return `
      <li class="api-entry ${open ? "open" : ""}">
        <button class="api-row" data-act="toggle" data-id="${e.id}">
          <span class="api-method m-${e.method.toLowerCase()}">${e.method}</span>
          <span class="api-path">${esc(e.path)}</span>
          <span class="api-meta ${e.status == null ? "" : ok ? "ok" : "bad"}">${meta}</span>
        </button>
        ${detail}
      </li>`;
  }

  let refreshQueued = false;
  function refreshConsole() {
    if (refreshQueued) return;
    refreshQueued = true;
    requestAnimationFrame(() => {
      refreshQueued = false;
      if (!document.body) return;
      ensureConsoleDom();
      $("#apiFab").innerHTML = `<span>&lt;/&gt; API</span><b>${LOG.length}</b>`;
      const drawer = $("#apiDrawer");
      drawer.classList.toggle("open", drawerOpen);
      if (!drawerOpen) return;
      // 입력 중인 키 필드는 다시 그리지 않도록 값 보존
      const focusedKey = document.activeElement?.id === "apiKeyInp";
      if (focusedKey) return;
      const scroll = drawer.scrollTop;
      drawer.innerHTML = `
        <header class="api-head">
          <div>
            <b>API 콘솔</b>
            <div class="api-sub">이 화면을 만든 실제 호출 — 그대로 사내 시스템에서 재현 가능</div>
          </div>
          <button class="api-btn" data-act="close" aria-label="닫기">닫기</button>
        </header>
        ${mcpPanelHtml()}
        <div class="api-keyrow">
          <label for="apiKeyInp">API Key</label>
          <input id="apiKeyInp" type="password" autocomplete="off" placeholder="공개 데모는 비워두세요" value="${esc(apiKey())}">
          <button class="api-btn" data-act="clear">기록 지우기</button>
        </div>
        <ul class="api-list">
          ${LOG.length ? LOG.map(entryHtml).join("") : `<li class="muted api-empty">아직 호출이 없습니다. 화면을 이동해 보세요.</li>`}
        </ul>`;
      drawer.scrollTop = scroll;
    });
  }

  window.addEventListener("DOMContentLoaded", refreshConsole);

  // ───────────────────────── 2) 가정 시뮬레이터 ─────────────────────────
  const SLIDERS = [
    { k: "wacc", label: "WACC (할인율)", min: 0.05, max: 0.15, step: 0.0025, pct: true },
    { k: "growth_rate_short", label: "단기 성장률 (1~5년차)", min: 0, max: 0.20, step: 0.005, pct: true },
    { k: "terminal_growth", label: "영구성장률", min: 0, max: 0.04, step: 0.0025, pct: true },
    { k: "peer_per_avg", label: "피어 PER", min: 1, max: 60, step: 0.5 },
    { k: "peer_ev_ebitda_avg", label: "피어 EV/EBITDA", min: 1, max: 30, step: 0.5 },
    { k: "liquidation_discount", label: "청산 할인계수", min: 0.3, max: 1, step: 0.05 },
  ];
  // 직접 입력 폼 (억원 단위 입력 → 원으로 변환)
  const CUSTOM_FIELDS = [
    ["revenue", "매출액", 500], ["operating_income", "영업이익", 60], ["net_income", "당기순이익", 45],
    ["ebitda", "EBITDA", 80], ["fcf", "잉여현금흐름(FCFF)", 40], ["total_assets", "자산총계", 600],
    ["total_liabilities", "부채총계", 200], ["net_debt", "순차입금", 50],
  ];

  const sim = { base: null, inputs: null, assumptions: {}, last: null, reqSeq: 0, timer: null };

  async function postCompute(body) {
    const res = await fetch("/api/v1/valuations/compute", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    let data;
    try { data = await res.json(); } catch { throw new Error(`서버 응답을 읽지 못했습니다 (HTTP ${res.status})`); }
    if (!res.ok || data.error) throw new Error(data.error?.message || `요청 실패 (HTTP ${res.status})`);
    return data;
  }

  window.renderSimulator = async function (root, params) {
    const mode = params.mode === "custom" ? "custom" : "ticker";
    const q = params.q || "";
    root.innerHTML = `
      <h1 class="page-title">가정 시뮬레이터<span class="muted">／ COMPUTE API · LIVE</span></h1>
      ${metaStrip("§06·SIMULATOR", "POST /api/v1/valuations/compute", "결정론적 재계산", "LLM 미개입")}
      <p class="page-sub">가정을 바꾸면 계산 엔진 API 가 즉시 다시 계산합니다. 같은 입력은 언제나 같은 결과 — 화면에 보이는 모든 숫자는 우측 하단 API 콘솔의 호출로 재현할 수 있습니다.</p>
      <div class="page-tabs">
        <button class="tab ${mode === "ticker" ? "active" : ""}" data-mode="ticker">상장사 (종목 검색)</button>
        <button class="tab ${mode === "custom" ? "active" : ""}" data-mode="custom">직접 입력 (비상장 · 딜 타깃)</button>
      </div>
      <div id="simEntry"></div>
      <div id="simBody"></div>`;
    $$(".page-tabs .tab", root).forEach(b => b.addEventListener("click", () =>
      navigate("/sim", b.dataset.mode === "custom" ? { mode: "custom" } : {})));

    sim.base = sim.inputs = sim.last = null;
    sim.assumptions = {};
    const entry = $("#simEntry"), body = $("#simBody");

    if (mode === "ticker") {
      entry.innerHTML = `
        <form id="simForm" class="page-search">
          <input id="simInp" type="text" value="${esc(q)}" placeholder="기업명 또는 종목코드 — 예: 삼성전자, 005930" autocomplete="off">
          <button type="submit">불러오기</button>
        </form>`;
      const inp = $("#simInp");
      attachAutocomplete(inp, (item) => navigate("/sim", { q: item.ticker }));
      $("#simForm").addEventListener("submit", e => {
        e.preventDefault();
        const v = inp.value.trim();
        if (v) navigate("/sim", { q: v });
      });
      if (!q) { body.innerHTML = `<div class="card muted">종목을 검색하면 최신 공시 재무로 기본 평가를 불러온 뒤 가정을 조정할 수 있습니다.</div>`; return; }
      await loadBase(body, { ticker: q });
    } else {
      entry.innerHTML = `
        <form id="simCustom" class="card sim-custom">
          <div class="sim-custom-grid">
            <label>회사명<input name="name" type="text" value="Target Co." maxlength="40"></label>
            <label>섹터<input name="sector" type="text" value="IT서비스" maxlength="20"></label>
            ${CUSTOM_FIELDS.map(([k, label, def]) =>
              `<label>${label} <span class="muted">(억원)</span><input name="${k}" type="number" step="any" value="${def}"></label>`).join("")}
            <label>발행주식수 <span class="muted">(주)</span><input name="shares_outstanding" type="number" step="1" min="0" value="1000000"></label>
          </div>
          <button type="submit">이 재무로 평가</button>
          <span class="muted sim-custom-note">입력값은 계산 요청에만 쓰이며 서버에 저장되지 않습니다.</span>
        </form>`;
      $("#simCustom").addEventListener("submit", async e => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const inputs = { name: String(fd.get("name") || "Target Co."), sector: String(fd.get("sector") || "기타") };
        for (const [k] of CUSTOM_FIELDS) inputs[k] = (Number(fd.get(k)) || 0) * 1e8;
        inputs.shares_outstanding = Number(fd.get("shares_outstanding")) || 0;
        sim.assumptions = {};
        await loadBase(body, { inputs });
      });
      body.innerHTML = `<div class="card muted">재무 수치를 넣고 평가를 실행하세요. 외부 데이터 조회 없이 입력값만으로 계산합니다.</div>`;
    }
  };

  async function loadBase(body, req) {
    body.innerHTML = `<div class="loading">기본 평가 계산 중…</div>`;
    try {
      const data = await postCompute({ ...req, sensitivity: { metric: "income_dcf" } });
      sim.base = data;
      sim.inputs = data.result.inputs;
      sim.last = data;
      renderSimBody(body);
    } catch (e) {
      body.innerHTML = `<div class="error">${esc(e.message)}</div>`;
    }
  }

  function sliderRange(s, v) {
    return { min: Math.min(s.min, v), max: Math.max(s.max, v) };
  }
  const showVal = (s, v) => s.pct ? (v * 100).toFixed(2) + "%" : Number(v).toFixed(2) + (s.k.startsWith("peer_") ? "x" : "");

  function renderSimBody(body) {
    const inp = sim.inputs;
    body.innerHTML = `
      <div class="sim-layout">
        <section class="card sim-controls">
          <h3>가정 조정 <button id="simReset" class="api-btn right" type="button">기준값으로</button></h3>
          ${SLIDERS.map(s => {
            const v = Number(inp[s.k]) || 0, r = sliderRange(s, v);
            return `
              <div class="sim-slider" data-k="${s.k}">
                <div class="sim-slider-head"><label for="sl_${s.k}">${s.label}</label><output id="out_${s.k}">${showVal(s, v)}</output></div>
                <input id="sl_${s.k}" type="range" min="${r.min}" max="${r.max}" step="${s.step}" value="${v}">
                <div class="sim-slider-base muted">기준 ${showVal(s, v)}</div>
              </div>`;
          }).join("")}
        </section>
        <section id="simResult" class="sim-result"></section>
      </div>`;
    SLIDERS.forEach(s => {
      const el = $("#sl_" + s.k);
      el.addEventListener("input", () => {
        const v = Number(el.value);
        $("#out_" + s.k).textContent = showVal(s, v);
        if (Math.abs(v - Number(inp[s.k])) < 1e-9) delete sim.assumptions[s.k];
        else sim.assumptions[s.k] = v;
        clearTimeout(sim.timer);
        sim.timer = setTimeout(recompute, 180);
      });
    });
    $("#simReset").addEventListener("click", () => {
      sim.assumptions = {};
      SLIDERS.forEach(s => { const v = Number(inp[s.k]) || 0; $("#sl_" + s.k).value = v; $("#out_" + s.k).textContent = showVal(s, v); });
      recompute();
    });
    renderSimResult();
  }

  async function recompute() {
    const my = ++sim.reqSeq;
    const out = $("#simResult");
    if (!out || !sim.inputs) return;
    out.classList.add("busy");
    try {
      // inputs 를 그대로 보내므로 외부 데이터 조회 없는 순수 계산 호출
      const data = await postCompute({
        inputs: sim.inputs, assumptions: sim.assumptions, sensitivity: { metric: "income_dcf" },
      });
      if (my !== sim.reqSeq) return;
      sim.last = data;
      renderSimResult();
    } catch (e) {
      if (my !== sim.reqSeq) return;
      renderSimResult(e.message);
    } finally {
      if (my === sim.reqSeq) out.classList.remove("busy");
    }
  }

  function deltaHtml(base, now, asPct = true) {
    if (!base || now == null) return `<span class="muted">-</span>`;
    const d = (now - base) / Math.abs(base);
    if (Math.abs(d) < 1e-9) return `<span class="muted">0.0%</span>`;
    return `<span class="${d >= 0 ? "pos" : "neg"}">${d >= 0 ? "+" : ""}${(d * 100).toFixed(1)}%</span>`;
  }

  function rangeBarsHtml(r) {
    const rows = [
      ["수익가치", r.income_min, r.income_mid, r.income_max],
      ["자산가치", r.asset_min, r.asset_mid, r.asset_max],
      ["상대가치", r.market_min, r.market_mid, r.market_max],
      ["종합", r.enterprise_min, r.enterprise_mid, r.enterprise_max],
    ];
    const top = Math.max(r.market_cap || 0, ...rows.map(x => x[3] || 0)) * 1.05 || 1;
    const pos = v => Math.max(0, Math.min(100, (v / top) * 100));
    const mcapLine = r.market_cap > 0
      ? `<div class="ff-mcap" style="left:${pos(r.market_cap)}%"><span>시가총액 ${fmt.bigKrw(r.market_cap)}</span></div>` : "";
    return `
      <div class="ff">
        ${rows.map(([label, lo, mid, hi]) => `
          <div class="ff-row ${label === "종합" ? "ff-total" : ""}">
            <div class="ff-label">${label}</div>
            <div class="ff-track">
              ${hi > 0 ? `<div class="ff-bar" style="left:${pos(lo)}%;width:${Math.max(pos(hi) - pos(lo), 0.6)}%"></div>
                          <div class="ff-mid" style="left:${pos(mid)}%"></div>` : ""}
            </div>
            <div class="ff-val">${hi > 0 ? `${fmt.bigKrw(lo)} ~ <b>${fmt.bigKrw(mid)}</b> ~ ${fmt.bigKrw(hi)}` : "산출 불가"}</div>
          </div>`).join("")}
        <div class="ff-row ff-axis"><div class="ff-label"></div><div class="ff-track ff-track-axis">${mcapLine}</div><div class="ff-val"></div></div>
      </div>`;
  }

  function sensitivityHtml(s, inp) {
    if (!s || !s.grid?.length) return "";
    const flat = s.grid.flat().filter(v => v != null && v > 0);
    if (!flat.length) return `<div class="muted">DCF 산출 불가 (FCF ≤ 0) — 민감도 표를 만들 수 없습니다.</div>`;
    const lo = Math.min(...flat), hi = Math.max(...flat);
    const near = (a, b) => Math.abs(a - b) < 1e-9;
    const pc = v => (v * 100).toFixed(2) + "%";
    return `
      <table class="sens">
        <thead><tr><th>영구성장률 ＼ WACC</th>${s.x_values.map(x => `<th class="${near(x, inp.wacc) ? "cur" : ""}">${pc(x)}</th>`).join("")}</tr></thead>
        <tbody>
          ${s.grid.map((row, i) => `
            <tr><th class="${near(s.y_values[i], inp.terminal_growth) ? "cur" : ""}">${pc(s.y_values[i])}</th>
              ${row.map((v, j) => {
                if (v == null || v <= 0) return `<td class="muted">-</td>`;
                const t = hi > lo ? (v - lo) / (hi - lo) : 0.5;
                const cur = near(s.x_values[j], inp.wacc) && near(s.y_values[i], inp.terminal_growth);
                return `<td class="${cur ? "cur" : ""}" style="background:rgba(22,101,52,${(0.04 + t * 0.26).toFixed(3)})">${fmt.bigKrw(v)}</td>`;
              }).join("")}
            </tr>`).join("")}
        </tbody>
      </table>`;
  }

  function renderSimResult(errMsg) {
    const out = $("#simResult");
    if (!out) return;
    const data = sim.last, base = sim.base.result, r = data.result, inp = r.inputs;
    const perShare = r.fair_price_mid > 0;
    const headNow = perShare ? r.fair_price_mid : r.enterprise_mid;
    const headBase = perShare ? base.fair_price_mid : base.enterprise_mid;
    const headFmt = perShare ? fmt.krw : fmt.bigKrw;
    const changed = Object.keys(sim.assumptions).length > 0;
    const prov = sim.base.provenance || {};
    const basis = prov.source === "client_inputs" ? "직접 입력 재무" : (prov.financials_basis || "시장 데이터");
    const baseRows = Object.fromEntries((base.detail_rows || []).map(x => [x.method.replace(/\(×[\d.]+\)/, ""), x.value]));
    const reqPreview = JSON.stringify({
      inputs: `{ …${r.name} 재무 ${Object.keys(sim.inputs).length}개 필드 }`,
      assumptions: sim.assumptions, sensitivity: { metric: "income_dcf" },
    }, null, 2);

    out.innerHTML = `
      ${errMsg ? `<div class="error">${esc(errMsg)} <span class="muted">— 아래는 마지막 유효 결과입니다.</span></div>` : ""}
      <div class="card">
        <div class="sim-head">
          <div>
            <div class="muted">${esc(r.name)} · ${esc(r.sector)} · ${esc(basis)}</div>
            <div class="sim-kpis">
              <div class="sim-kpi main">
                <span>${perShare ? "주당 적정가 (mid)" : "기업가치 (mid)"}</span>
                <b>${headFmt(headNow)}</b>
                <small>${changed ? `기준 ${headFmt(headBase)} · ${deltaHtml(headBase, headNow)}` : "기준 가정"}</small>
              </div>
              <div class="sim-kpi"><span>DCF 가치</span><b>${fmt.bigKrw(r.income_dcf)}</b><small>${changed ? deltaHtml(base.income_dcf, r.income_dcf) : "&nbsp;"}</small></div>
              <div class="sim-kpi"><span>기업가치 (mid)</span><b>${fmt.bigKrw(r.enterprise_mid)}</b><small>${changed ? deltaHtml(base.enterprise_mid, r.enterprise_mid) : "&nbsp;"}</small></div>
              ${r.upside_mid != null ? `<div class="sim-kpi"><span>시총 대비</span><b class="${r.upside_mid >= 0 ? "pos" : "neg"}">${fmt.pct(r.upside_mid, 1)}</b><small>${esc(r.rating)}</small></div>` : ""}
            </div>
          </div>
        </div>
        <div class="sim-proof">
          <span class="proof-badge">결정론적 계산</span>
          <span>input_hash <code title="${esc(data.input_hash)}">${esc((data.input_hash || "").slice(7, 23))}…</code></span>
          <span>${esc(data.engine_version)}</span>
          <span class="muted">같은 해시는 언제 호출해도 같은 결과</span>
        </div>
      </div>

      <div class="card">
        <h3>접근법별 가치 범위 <span class="muted" style="font-size:11px">／ min ~ mid ~ max</span></h3>
        ${rangeBarsHtml(r)}
      </div>

      <div class="card">
        <h3>DCF 민감도 <span class="muted" style="font-size:11px">／ WACC × 영구성장률 → DCF 기업가치</span></h3>
        ${sensitivityHtml(data.sensitivity, inp)}
      </div>

      <div class="card">
        <h3>모델별 산출값 <span class="muted" style="font-size:11px">／ 기준 대비</span></h3>
        <table class="kpi-table sim-models">
          <tr><th>접근법</th><th>모델</th><th class="right">기준</th><th class="right">시나리오</th><th class="right">Δ</th></tr>
          ${(r.detail_rows || []).map(row => {
            const b = baseRows[row.method.replace(/\(×[\d.]+\)/, "")] || 0;
            return `<tr><td>${esc(row.approach)}</td><td>${esc(row.method)}</td>
              <td class="right">${fmt.bigKrw(b)}</td><td class="right"><b>${fmt.bigKrw(row.value)}</b></td>
              <td class="right">${deltaHtml(b, row.value)}</td></tr>`;
          }).join("")}
        </table>
        ${(r.notes || []).length ? `<ul class="sim-notes muted">${r.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
      </div>

      <div class="card">
        <h3>이 결과를 만든 요청 <span class="muted" style="font-size:11px">／ POST /api/v1/valuations/compute</span></h3>
        <pre class="api-code">${esc(reqPreview)}</pre>
        <div class="muted" style="font-size:12px">전체 요청·응답과 curl / MCP tool call 은 우측 하단 <b>&lt;/&gt; API</b> 콘솔에서 복사할 수 있습니다.</div>
      </div>`;
  }
})();
