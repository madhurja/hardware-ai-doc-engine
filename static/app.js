const state = {
  status: null,
  activeView: location.hash.replace("#", "") || "dashboard",
  busy: false,
  installPrompt: null,
};

const qs = (selector) => document.querySelector(selector);
const root = qs("#app");

const icons = {
  upload: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 5 10h4v5h6v-5h4l-7-7Zm-7 15h14v2H5v-2Z"/></svg>',
  file: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6V3Zm7 1.8V8h3.2L13 4.8ZM8 12h8v2H8v-2Zm0 4h8v2H8v-2Z"/></svg>',
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7L8 5Z"/></svg>',
  copy: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 8h11v13H8V8Zm2 2v9h7v-9h-7ZM5 3h11v3h-2V5H7v9h-2V3Z"/></svg>',
  spark: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 2.2 6.8H21l-5.5 4 2.1 6.8-5.6-4.2-5.6 4.2 2.1-6.8L3 8.8h6.8L12 2Z"/></svg>',
  shield: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 5 5v6c0 4.8 2.9 9.1 7 11 4.1-1.9 7-6.2 7-11V5l-7-3Zm0 3.2 4.8 2.1V11c0 3.4-1.9 6.5-4.8 8.1C9.1 17.5 7.2 14.4 7.2 11V7.3L12 5.2Z"/></svg>',
  phone: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 2h10v20H7V2Zm2 2v16h6V4H9Zm2 13h2v1h-2v-1Z"/></svg>',
  chart: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19h14v2H3V3h2v16Zm2-2V9h3v8H7Zm5 0V5h3v12h-3Zm5 0v-6h3v6h-3Z"/></svg>',
  check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 16.2-3.5-3.5L4 14.2 9 19 20 8l-1.5-1.5L9 16.2Z"/></svg>',
  plug: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 2h2v6h2V2h2v6h2V2h2v7c0 2.4-1.7 4.4-4 4.9V22h-2v-8.1c-2.3-.5-4-2.5-4-4.9V2Z"/></svg>',
};

window.addEventListener("hashchange", () => {
  state.activeView = location.hash.replace("#", "") || "dashboard";
  render();
});

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  state.installPrompt = event;
  render();
});

function cx(...items) {
  return items.filter(Boolean).join(" ");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function showToast(message) {
  const toast = qs("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.setTimeout(() => toast.classList.remove("visible"), 3200);
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }
  return data;
}

async function refreshStatus() {
  state.status = await fetchJson("/api/status");
  render();
}

function navigate(view) {
  location.hash = view;
}

function appView() {
  const status = state.status;
  if (!status) {
    return `<main class="boot-screen"><span class="loader"></span><strong>Opening local documentation app</strong></main>`;
  }

  return `
    <div class="app-frame">
      ${sidebar()}
      <main class="main-stage">
        ${topBar()}
        ${activeScreen()}
      </main>
      ${mobileNav()}
    </div>
  `;
}

function sidebar() {
  const nav = [
    ["dashboard", "Dashboard", icons.chart],
    ["intake", "Intake", icons.upload],
    ["generate", "Generate", icons.spark],
    ["plugins", "Plugins", icons.plug],
    ["outputs", "Outputs", icons.file],
    ["run", "Run App", icons.play],
  ];

  return `
    <aside class="sidebar" aria-label="Workspace">
      <button class="brand-button" type="button" data-view="dashboard" aria-label="Open dashboard">
        <span class="brand-mark">${icons.shield}</span>
        <span><strong>Doc Engine</strong><small>Software app mode</small></span>
      </button>
      <nav class="nav-list" aria-label="Sections">
        ${nav.map(([view, label, icon]) => navButton(view, label, icon)).join("")}
      </nav>
      <div class="privacy-panel">
        <span class="status-dot"></span>
        <div>
          <strong>Local-first engine</strong>
          <p>Customer files and generated PDFs stay out of GitHub.</p>
        </div>
      </div>
    </aside>
  `;
}

function mobileNav() {
  const nav = [
    ["dashboard", "Home", icons.chart],
    ["intake", "Files", icons.upload],
    ["generate", "Build", icons.spark],
    ["plugins", "Plugins", icons.plug],
    ["outputs", "PDFs", icons.file],
    ["run", "Run", icons.phone],
  ];
  return `<nav class="mobile-nav" aria-label="Mobile sections">${nav.map(([view, label, icon]) => navButton(view, label, icon)).join("")}</nav>`;
}

function navButton(view, label, icon) {
  return `
    <button class="${cx("nav-button", state.activeView === view && "active")}" type="button" data-view="${view}">
      ${icon}<span>${label}</span>
    </button>
  `;
}

function topBar() {
  const runtime = state.status.runtime || {};
  const score = state.status.analysis?.readiness_score || 0;
  return `
    <header class="topbar">
      <div>
        <p class="eyebrow">Local browser software</p>
        <h1>Hardware AI Documentation Engine</h1>
      </div>
      <div class="top-actions">
        <button class="ghost-btn" type="button" data-copy="${escapeHtml(runtime.local_url || "http://127.0.0.1:8000")}">${icons.copy}<span>Copy Local Link</span></button>
        <button class="ghost-btn" type="button" data-install ${state.installPrompt ? "" : "disabled"}>${icons.phone}<span>Install App</span></button>
        <div class="score-pill"><strong>${score}</strong><span>/100</span></div>
      </div>
    </header>
  `;
}

function activeScreen() {
  if (state.activeView === "intake") return intakeScreen();
  if (state.activeView === "generate") return generateScreen();
  if (state.activeView === "plugins") return pluginsScreen();
  if (state.activeView === "outputs") return outputsScreen();
  if (state.activeView === "run") return runScreen();
  return dashboardScreen();
}

function dashboardScreen() {
  const data = state.status;
  const metadata = data.metadata || {};
  const analysis = data.analysis || {};
  const improvement = data.adaptive_improvement || {};
  const audit = data.quality_audit || {};
  const outputs = data.outputs || [];
  const cards = [
    ["Schematics", metadata.schematic_files_scanned || 0, "PDF evidence scanned"],
    ["Rails", (analysis.power_rails || []).length, "Power domains found"],
    ["Subsystems", (analysis.interface_groups || []).length, "Functional blocks"],
    ["Ports", (analysis.port_map || []).length, "Connector candidates"],
    ["Visuals", (analysis.board_visuals || []).length, "Board images"],
    ["Open Flaws", flawCount(audit), audit.release_status || "Audit status"],
    ["Learning Runs", improvement.runs_total || 0, "Adaptive memory"],
  ];

  return `
    <section class="hero-panel">
      <div class="hero-copy">
        <p class="eyebrow">Professional hardware docs workstation</p>
        <h2>Upload evidence, inspect risks, generate polished PDFs, and run it like a local app.</h2>
        <p>Designed for Windows desktop use and Android browser access on the same Wi-Fi, with an installable PWA shell.</p>
        <div class="hero-actions">
          <button class="primary-btn" type="button" data-view="generate">${icons.spark}<span>Generate PDFs</span></button>
          <button class="secondary-btn" type="button" data-view="run">${icons.play}<span>Run locally</span></button>
        </div>
      </div>
      <figure class="hero-visual">
        <img src="/static/assets/hardware-workbench.jpg" alt="Engineering desk with PCB, schematic sheets, and generated technical documentation">
      </figure>
    </section>
    <section class="metric-grid">${cards.map(metricCard).join("")}</section>
    <section class="content-grid">
      ${analysisPanel("Power Rails", analysis.power_rails || [], (rail) => `<strong>${escapeHtml(rail.net)}</strong><span>${escapeHtml(rail.role)}</span>`)}
      ${analysisPanel("Subsystems", analysis.interface_groups || [], (group) => `<strong>${escapeHtml(group.name)}</strong><span>${escapeHtml((group.evidence || []).slice(0, 4).join(", "))} - ${group.confidence || 0}%</span>`)}
      ${qualityAuditPanel(audit)}
      ${portMapPanel(analysis.port_map || [])}
      ${drcCoveragePanel(analysis.drc_coverage || [])}
      ${drcFindingsPanel(analysis.drc_findings || [], analysis.drc_summary || {})}
      ${skillGatePanel(analysis.skill_review_gates || [])}
      ${optimizationPanel(analysis.optimization_actions || [])}
      ${validationPanel(analysis.validation_matrix || [])}
      ${adaptivePanel(improvement)}
    </section>
  `;
}

function flawCount(audit) {
  const counts = audit.counts || {};
  return (counts.blocker || 0) + (counts.major || 0) + (counts.minor || 0);
}

function metricCard([label, value, note]) {
  return `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`;
}

function analysisPanel(title, items, itemRenderer) {
  const body = items.length
    ? items.slice(0, 8).map((item) => `<div class="mini-row">${itemRenderer(item)}</div>`).join("")
    : `<div class="empty-state">Upload source files to populate this section.</div>`;
  return `<section class="panel"><h3>${escapeHtml(title)}</h3><div class="stack-list">${body}</div></section>`;
}

function optimizationPanel(items) {
  const body = items.length
    ? items.slice(0, 6).map((item) => `
      <div class="priority-row">
        <span class="priority ${escapeHtml(item.priority || "P2")}">${escapeHtml(item.priority || "P2")}</span>
        <div><strong>${escapeHtml(item.area)}</strong><span>${escapeHtml(item.recommendation)}</span></div>
      </div>
    `).join("")
    : `<div class="empty-state">Optimization actions appear after schematic analysis.</div>`;
  return `<section class="panel wide-panel"><h3>200% Optimization Queue</h3><div class="stack-list">${body}</div></section>`;
}

function skillGatePanel(items) {
  const body = items.length
    ? items.slice(0, 6).map((item) => `
      <div class="priority-row">
        <span class="priority ${escapeHtml(item.priority || "P2")}">${escapeHtml(item.priority || "P2")}</span>
        <div>
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.source_skill)} - ${escapeHtml(item.evidence)}</span>
        </div>
      </div>
    `).join("")
    : `<div class="empty-state">Skill gates appear after schematic or PCB evidence is detected.</div>`;
  return `<section class="panel wide-panel"><h3>Schematic/PCB Skill Gates</h3><div class="stack-list">${body}</div></section>`;
}

function validationPanel(items) {
  const body = items.length
    ? items.slice(0, 6).map((item) => `
      <div class="mini-row">
        <strong>${escapeHtml(item.subsystem)}</strong>
        <span>${escapeHtml(item.method)}</span>
      </div>
    `).join("")
    : `<div class="empty-state">Validation matrix appears after analysis.</div>`;
  return `<section class="panel wide-panel"><h3>Validation Matrix</h3><div class="stack-list">${body}</div></section>`;
}

function qualityAuditPanel(audit) {
  const flaws = audit.flaws || [];
  const counts = audit.counts || {};
  const body = flaws.length
    ? flaws.slice(0, 7).map((flaw) => `
      <div class="priority-row">
        <span class="priority ${severityClass(flaw.severity)}">${escapeHtml(flaw.severity || "minor")}</span>
        <div>
          <strong>${escapeHtml(flaw.area)} - ${escapeHtml(flaw.flaw)}</strong>
          <span>${escapeHtml(flaw.fix)}</span>
        </div>
      </div>
    `).join("")
    : `<div class="empty-state">No open evidence flaws were detected from the current inputs.</div>`;
  return `
    <section class="panel wide-panel">
      <h3>Flaw Radar</h3>
      <div class="quality-strip">
        <span>${escapeHtml(audit.release_status || "Not audited")}</span>
        <strong>${escapeHtml(audit.quality_score || 0)}/100</strong>
        <small>${escapeHtml(counts.blocker || 0)} blocker, ${escapeHtml(counts.major || 0)} major, ${escapeHtml(counts.minor || 0)} minor</small>
      </div>
      <div class="stack-list">${body}</div>
    </section>
  `;
}

function drcFindingsPanel(findings, summary) {
  const body = findings.length
    ? findings.slice(0, 8).map((finding) => `
      <div class="priority-row">
        <span class="priority ${severityClass(finding.severity)}">${escapeHtml(finding.severity || "info")}</span>
        <div>
          <strong>${escapeHtml(finding.id)} - ${escapeHtml(finding.domain)}</strong>
          <span>${escapeHtml(finding.finding)}</span>
        </div>
      </div>
    `).join("")
    : `<div class="empty-state">No DRC/ERC rule findings were detected from current evidence.</div>`;
  return `
    <section class="panel wide-panel">
      <h3>DRC/ERC Rule Findings</h3>
      <div class="quality-strip">
        <span>${escapeHtml(summary.finding_count || 0)} findings</span>
        <strong>${escapeHtml(summary.score || 100)}/100</strong>
        <small>PDF-based pre-check; native CAD ERC/DRC still required for final pass/fail.</small>
      </div>
      <div class="stack-list">${body}</div>
    </section>
  `;
}

function drcCoveragePanel(rows) {
  const body = rows.length
    ? rows.map((row) => `
      <div class="mini-row">
        <strong>${escapeHtml(row.domain)} - ${escapeHtml(row.status)}</strong>
        <span>${escapeHtml(row.evidence)} | ${escapeHtml(row.next_step)}</span>
      </div>
    `).join("")
    : `<div class="empty-state">DRC coverage appears after schematic analysis.</div>`;
  return `<section class="panel wide-panel"><h3>DRC Evidence Coverage</h3><div class="stack-list">${body}</div></section>`;
}

function portMapPanel(rows) {
  const body = rows.length
    ? rows.slice(0, 8).map((row) => `
      <div class="mini-row">
        <strong>${escapeHtml(row.port)} - ${escapeHtml(row.function)}</strong>
        <span>${escapeHtml(row.key_signals)} | ${escapeHtml(row.source_page)}</span>
      </div>
    `).join("")
    : `<div class="empty-state">Port mapping appears after EasyEDA, schematic, or connector evidence is detected.</div>`;
  return `<section class="panel wide-panel"><h3>Port And Connector Map</h3><div class="stack-list">${body}</div></section>`;
}

function severityClass(severity) {
  if (severity === "blocker") return "P1";
  if (severity === "major") return "P2";
  return "P3";
}

function adaptivePanel(improvement) {
  const hints = improvement.adaptive_hints || [];
  const risk = (improvement.recurring_risks || [])[0];
  const body = `
    <div class="mini-row"><strong>Runs recorded</strong><span>${escapeHtml(improvement.runs_total || 0)}</span></div>
    <div class="mini-row"><strong>Average readiness</strong><span>${escapeHtml(improvement.average_readiness_score || 0)}/100</span></div>
    <div class="mini-row"><strong>Best readiness</strong><span>${escapeHtml(improvement.best_readiness_score || 0)}/100</span></div>
    ${risk ? `<div class="mini-row"><strong>Recurring risk</strong><span>${escapeHtml(risk.item)} (${escapeHtml(risk.count)})</span></div>` : ""}
    ${hints.slice(0, 3).map((hint) => `<div class="mini-row"><strong>Adaptive hint</strong><span>${escapeHtml(hint)}</span></div>`).join("")}
  `;
  return `<section class="panel wide-panel"><h3>Self-Improvement Memory</h3><div class="stack-list">${body}</div></section>`;
}

function intakeScreen() {
  return `
    <section class="screen-grid">
      <form class="panel form-panel" id="intakeForm">
        <div class="panel-heading">${icons.upload}<div><p class="eyebrow">Intake</p><h2>Add source files</h2></div></div>
        <label for="target">Destination</label>
        <select id="target" name="target">
          <option value="schematics">Schematics / PDFs</option>
          <option value="code">Firmware source</option>
          <option value="pcb">PCB / BOM manifests</option>
        </select>
        <label for="files">Files</label>
        <input id="files" name="files" type="file" multiple>
        <button class="primary-btn" type="submit">${icons.upload}<span>Upload to intake</span></button>
        <p class="helper">Files are stored in ignored local folders and will not be pushed to GitHub.</p>
      </form>
      <section class="panel">
        <h2>Evidence Intake Rules</h2>
        <div class="step-list">
          <div><strong>1</strong><span>Upload schematic PDFs first so rails and blocks can be detected.</span></div>
          <div><strong>2</strong><span>Add firmware files to map pins and interfaces.</span></div>
          <div><strong>3</strong><span>Add BOM or PCB exports to improve part traceability.</span></div>
          <div><strong>4</strong><span>Generate the full package after reviewing the optimization queue.</span></div>
        </div>
      </section>
    </section>
  `;
}

function generateScreen() {
  return `
    <section class="screen-grid">
      <section class="panel form-panel">
        <div class="panel-heading">${icons.spark}<div><p class="eyebrow">Generate</p><h2>Build document pack</h2></div></div>
        <label for="docType">Document type</label>
        <select id="docType">
          <option value="user_manual">Detailed user manual</option>
          <option value="test_report">Functional test report</option>
          <option value="drc_report">Schematic DRC/ERC report</option>
          <option value="compliance_brief">Compliance brief</option>
          <option value="bom">Draft BOM</option>
          <option value="all">Full package</option>
        </select>
        <label class="switch-row">
          <input id="localOnly" type="checkbox" checked>
          <span>Local-only generation</span>
        </label>
        <button class="primary-btn" id="generateBtn" type="button" ${state.busy ? "disabled" : ""}>
          ${state.busy ? '<span class="loader small"></span>' : icons.spark}
          <span>${state.busy ? "Generating..." : "Generate PDFs"}</span>
        </button>
        <p class="helper">Local-only mode uses deterministic analysis. API-assisted drafting remains opt-in.</p>
      </section>
      <section class="panel">
        <h2>Generation Quality Gates</h2>
        <div class="quality-list">
          ${qualityItem("Evidence readiness", `${state.status.analysis?.readiness_score || 0}/100`)}
          ${qualityItem("Optimization actions", (state.status.analysis?.optimization_actions || []).length)}
          ${qualityItem("Validation checks", (state.status.analysis?.validation_matrix || []).length)}
          ${qualityItem("Bring-up steps", (state.status.analysis?.bringup_sequence || []).length)}
          ${qualityItem("Skill-pack gates", (state.status.analysis?.skill_review_gates || []).length)}
          ${qualityItem("DRC findings", (state.status.analysis?.drc_findings || []).length)}
          ${qualityItem("Open flaws", flawCount(state.status.quality_audit || {}))}
          ${qualityItem("Learning runs", state.status.adaptive_improvement?.runs_total || 0)}
        </div>
      </section>
    </section>
  `;
}

function pluginsScreen() {
  const catalog = state.status.plugins || {};
  const plugins = catalog.plugins || [];
  const research = catalog.research_pack || {};
  const summary = catalog.summary || {};
  const categoryRows = groupPluginsByCategory(plugins);
  return `
    <section class="plugin-hero panel">
      <div>
        <p class="eyebrow">Internet and plugin hub</p>
        <h2>Research parts, standards, CAD checks, app access, and AI drafting from one place.</h2>
        <p class="helper">Browser links work immediately. API-style plugins are prepared for credentials when you want deeper automation.</p>
      </div>
      <div class="plugin-summary">
        ${qualityItem("Plugins", summary.total || plugins.length)}
        ${qualityItem("Internet enabled", summary.internet_enabled || 0)}
        ${qualityItem("API ready", summary.api_ready || 0)}
        ${qualityItem("Research links", summary.research_links || 0)}
      </div>
    </section>
    <section class="content-grid">
      ${categoryRows.map(([category, items]) => pluginCategoryPanel(category, items)).join("")}
      ${researchPackPanel(research)}
    </section>
  `;
}

function groupPluginsByCategory(plugins) {
  const groups = new Map();
  for (const plugin of plugins) {
    const category = plugin.category || "Plugins";
    if (!groups.has(category)) groups.set(category, []);
    groups.get(category).push(plugin);
  }
  return [...groups.entries()];
}

function pluginCategoryPanel(category, plugins) {
  const body = plugins.map((plugin) => `
    <article class="plugin-card">
      <div class="plugin-card-head">
        <span class="plugin-mode">${escapeHtml(plugin.mode)}</span>
        <strong>${escapeHtml(plugin.name)}</strong>
      </div>
      <p>${escapeHtml(plugin.description)}</p>
      <div class="plugin-status">
        <span>${escapeHtml(plugin.status || "Ready")}</span>
        ${plugin.internet_required ? "<small>Internet</small>" : "<small>Local</small>"}
        ${plugin.requires_key ? "<small>API key optional</small>" : ""}
      </div>
      <p class="helper">${escapeHtml(plugin.setup)}</p>
      ${pluginActionLinks(plugin.actions || [])}
    </article>
  `).join("");
  return `<section class="panel wide-panel"><h3>${escapeHtml(category)}</h3><div class="plugin-list">${body}</div></section>`;
}

function pluginActionLinks(actions) {
  if (!actions.length) return "";
  return `<div class="plugin-actions">${actions.slice(0, 5).map((action) => `
    <a href="${escapeHtml(action.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(action.label)}</a>
  `).join("")}</div>`;
}

function researchPackPanel(research) {
  const parts = research.parts || [];
  const standards = research.standards || [];
  const cad = research.cad || [];
  const partRows = parts.length
    ? parts.slice(0, 8).map((part) => `
      <div class="research-row">
        <strong>${escapeHtml(part.reference)} - ${escapeHtml(part.query)}</strong>
        ${pluginActionLinks(part.links || [])}
      </div>
    `).join("")
    : `<div class="empty-state">No key part candidates detected yet. Upload schematics or BOM data to create part lookup links.</div>`;
  const standardRows = [...standards, ...cad].slice(0, 8).map((item) => `
    <div class="research-row">
      <strong>${escapeHtml(item.label)}</strong>
      <span>${escapeHtml(item.reason)}</span>
      <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">Open</a>
    </div>
  `).join("");

  return `
    <section class="panel wide-panel">
      <h3>One-Click Research Pack</h3>
      <div class="stack-list">${partRows}</div>
    </section>
    <section class="panel wide-panel">
      <h3>Standards And CAD References</h3>
      <div class="stack-list">${standardRows}</div>
    </section>
  `;
}

function qualityItem(label, value) {
  return `<div class="quality-item">${icons.check}<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function outputsScreen() {
  const outputs = state.status.outputs || [];
  const body = outputs.length
    ? outputs.map((output) => `
      <article class="output-card">
        <div>${icons.file}<span><strong>${escapeHtml(output.name)}</strong><small>${escapeHtml(output.size_kb)} KB - ${escapeHtml(output.modified)}</small></span></div>
        <a class="secondary-btn" href="${escapeHtml(output.url)}" target="_blank" rel="noopener">Download</a>
      </article>
    `).join("")
    : `<div class="panel empty-state">No PDFs generated yet. Build a document pack to populate this area.</div>`;

  return `<section class="output-grid">${body}</section>`;
}

function runScreen() {
  const runtime = state.status.runtime || {};
  const lanUrls = runtime.lan_urls || [];
  return `
    <section class="screen-grid">
      <section class="panel">
        <div class="panel-heading">${icons.play}<div><p class="eyebrow">Windows</p><h2>Run as local software</h2></div></div>
        <div class="command-box"><code>.\\run_windows.ps1</code><button type="button" data-copy=".\\run_windows.ps1">${icons.copy}</button></div>
        <p class="helper">This starts the local HTTP app on your PC. Open the link below in Chrome or Edge.</p>
        <div class="link-card"><span>Local HTTP link</span><a href="${escapeHtml(runtime.local_url)}" target="_blank" rel="noopener">${escapeHtml(runtime.local_url)}</a><button type="button" data-copy="${escapeHtml(runtime.local_url)}">${icons.copy}</button></div>
      </section>
      <section class="panel">
        <div class="panel-heading">${icons.phone}<div><p class="eyebrow">Android</p><h2>Open on phone</h2></div></div>
        <p class="helper">Run the Windows host command, keep the phone and PC on the same Wi-Fi, then open one of these links in Android Chrome.</p>
        <div class="stack-list">
          ${(lanUrls.length ? lanUrls : ["http://YOUR-PC-IP:8000"]).map((url) => `<div class="link-card"><span>Phone link</span><a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a><button type="button" data-copy="${escapeHtml(url)}">${icons.copy}</button></div>`).join("")}
        </div>
      </section>
      <section class="panel wide-panel">
        <h2>Installable App Mode</h2>
        <div class="step-list">
          <div><strong>1</strong><span>Start the server with the Windows command.</span></div>
          <div><strong>2</strong><span>Open the local link on desktop or LAN link on Android.</span></div>
          <div><strong>3</strong><span>Use the browser install option to pin it like an app.</span></div>
          <div><strong>4</strong><span>Keep generated PDFs in output packages and customer inputs in intake folders.</span></div>
        </div>
      </section>
    </section>
  `;
}

async function handleUpload(event) {
  event.preventDefault();
  const files = qs("#files").files;
  if (!files.length) {
    showToast("Choose at least one file first.");
    return;
  }
  const form = new FormData();
  form.append("target", qs("#target").value);
  for (const file of files) {
    form.append("files", file);
  }
  await fetchJson("/api/upload", { method: "POST", body: form });
  showToast("Files added to intake.");
  await refreshStatus();
}

async function handleGenerate() {
  const form = new FormData();
  form.append("document_type", qs("#docType").value);
  form.append("local_only", qs("#localOnly").checked ? "true" : "false");
  state.busy = true;
  render();
  try {
    const result = await fetchJson("/api/generate", { method: "POST", body: form });
    showToast(`Created ${result.created.length} PDF file(s).`);
    await refreshStatus();
  } catch (error) {
    showToast(error.message);
  } finally {
    state.busy = false;
    render();
  }
}

async function installApp() {
  if (!state.installPrompt) {
    showToast("Use the browser menu to install after opening the local link.");
    return;
  }
  state.installPrompt.prompt();
  await state.installPrompt.userChoice.catch(() => null);
  state.installPrompt = null;
  render();
}

async function copyText(value) {
  try {
    await navigator.clipboard.writeText(value);
    showToast("Copied.");
  } catch {
    showToast(value);
  }
}

function bindEvents() {
  root.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => navigate(button.dataset.view));
  });
  root.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", () => copyText(button.dataset.copy));
  });
  root.querySelector("[data-install]")?.addEventListener("click", installApp);
  root.querySelector("#intakeForm")?.addEventListener("submit", (event) => {
    handleUpload(event).catch((error) => showToast(error.message));
  });
  root.querySelector("#generateBtn")?.addEventListener("click", () => {
    handleGenerate().catch((error) => showToast(error.message));
  });
}

function render() {
  root.innerHTML = appView();
  bindEvents();
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/service-worker.js").catch(() => null);
}

render();
refreshStatus().catch((error) => showToast(error.message));
