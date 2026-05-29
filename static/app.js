const state = {
  status: null,
};

const qs = (selector) => document.querySelector(selector);

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
  renderStatus(state.status);
}

function renderStatus(data) {
  const metadata = data.metadata || {};
  const analysis = data.analysis || {};
  const outputs = data.outputs || [];

  qs("#metricSchematics").textContent = metadata.schematic_files_scanned || 0;
  qs("#metricRails").textContent = (analysis.power_rails || []).length;
  qs("#metricInterfaces").textContent = (analysis.interface_groups || []).length;
  qs("#metricOutputs").textContent = outputs.length;

  renderTags("#railsList", (analysis.power_rails || []).map((rail) => `${rail.net} - ${rail.role}`));
  renderTags("#interfacesList", (analysis.interface_groups || []).map((group) => `${group.name} (${group.confidence}%)`));
  renderCompact("#partsList", (analysis.key_parts || []).map((part) => ({
    title: part.reference,
    meta: part.value_or_part,
  })));
  renderCompact("#riskList", (analysis.risk_flags || []).map((risk) => ({
    title: risk,
    meta: "Review before release",
  })));
  renderOutputs(outputs);
}

function renderTags(selector, items) {
  const target = qs(selector);
  target.innerHTML = "";
  const safeItems = items.length ? items : ["No evidence detected yet"];
  for (const item of safeItems) {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = item;
    target.appendChild(tag);
  }
}

function renderCompact(selector, items) {
  const target = qs(selector);
  target.innerHTML = "";
  const safeItems = items.length ? items : [{ title: "No items yet", meta: "Upload or analyze files" }];
  for (const item of safeItems) {
    const row = document.createElement("div");
    row.className = "compact-item";
    row.innerHTML = `<div><strong></strong><span></span></div>`;
    row.querySelector("strong").textContent = item.title;
    row.querySelector("span").textContent = item.meta;
    target.appendChild(row);
  }
}

function renderOutputs(outputs) {
  const target = qs("#outputList");
  target.innerHTML = "";
  if (!outputs.length) {
    const empty = document.createElement("div");
    empty.className = "output-item";
    empty.innerHTML = "<div><strong>No PDFs generated yet</strong><span>Run a document pack to populate this area.</span></div>";
    target.appendChild(empty);
    return;
  }
  for (const output of outputs) {
    const row = document.createElement("div");
    row.className = "output-item";
    row.innerHTML = `<div><strong></strong><span></span></div><a>Download</a>`;
    row.querySelector("strong").textContent = output.name;
    row.querySelector("span").textContent = `${output.size_kb} KB - ${output.modified}`;
    const link = row.querySelector("a");
    link.href = output.url;
    link.target = "_blank";
    link.rel = "noopener";
    target.appendChild(row);
  }
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
  qs("#files").value = "";
  showToast("Files added to intake.");
  await refreshStatus();
}

async function handleGenerate() {
  const button = qs("#generateBtn");
  const form = new FormData();
  form.append("document_type", qs("#docType").value);
  form.append("local_only", qs("#localOnly").checked ? "true" : "false");
  button.disabled = true;
  button.textContent = "Generating...";
  try {
    const result = await fetchJson("/api/generate", { method: "POST", body: form });
    showToast(`Created ${result.created.length} PDF file(s).`);
    await refreshStatus();
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 2.2 6.8H21l-5.5 4 2.1 6.8-5.6-4.2-5.6 4.2 2.1-6.8L3 8.8h6.8L12 2Z"/></svg> Generate PDFs';
  }
}

qs("#intake").addEventListener("submit", (event) => {
  handleUpload(event).catch((error) => showToast(error.message));
});
qs("#generateBtn").addEventListener("click", () => {
  handleGenerate().catch((error) => showToast(error.message));
});

refreshStatus().catch((error) => showToast(error.message));

