import cytoscape from "cytoscape";

const API = "";

const colorByKind = {
  dimension: "#3dba8a",
  entity: "#8fa399",
  ds_task: "#4ea1ff",
  code_span: "#f0a05a",
  yuque_doc: "#b48cff",
};

const cy = cytoscape({
  container: document.getElementById("cy"),
  style: [
    {
      selector: "node",
      style: {
        label: "data(label)",
        color: "#e7f0ea",
        "background-color": "data(color)",
        "font-size": 11,
        "text-wrap": "wrap",
        "text-max-width": 120,
        "text-valign": "center",
        width: 28,
        height: 28,
        "border-width": 1,
        "border-color": "#1b2a23",
      },
    },
    {
      selector: "edge",
      style: {
        width: 1.5,
        "line-color": "#334840",
        "target-arrow-color": "#334840",
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
        label: "data(rel)",
        "font-size": 8,
        color: "#8fa399",
        "text-rotation": "autorotate",
      },
    },
  ],
  layout: { name: "cose", animate: true, animationDuration: 500 },
});

const detailEl = document.getElementById("detail");
const answerEl = document.getElementById("answer");

function renderDetail(node) {
  const meta = node.data("meta") || {};
  const kind = node.data("kind");
  const lines = [`类型: ${kind}`, `标签: ${node.data("label")}`, ""];

  if (kind === "ds_task") {
    lines.push(`项目: ${meta.project || ""}`);
    lines.push(`工作流: ${meta.workflow || ""}`);
    lines.push(`任务: ${meta.task_name || ""}`);
    if (meta.ui_url) lines.push(`链接: ${meta.ui_url}`);
  } else if (kind === "code_span") {
    lines.push(`仓库: ${meta.repo || ""}`);
    lines.push(`路径: ${meta.path || ""}`);
    lines.push(`行号: ${meta.start_line}-${meta.end_line}`);
    if (meta.blob_url) lines.push(`链接: ${meta.blob_url}`);
  } else if (kind === "yuque_doc") {
    lines.push(`标题: ${meta.title || ""}`);
    if (meta.url) lines.push(`链接: ${meta.url}`);
  } else if (kind === "dimension") {
    lines.push(`id: ${meta.id || ""}`);
    lines.push(`source: ${meta.source || ""}`);
  }

  const url = meta.ui_url || meta.blob_url || meta.url;
  detailEl.classList.remove("muted");
  detailEl.innerHTML = lines
    .map((l) => {
      if (l.startsWith("链接: ")) {
        const href = l.slice(4);
        return `链接: <a href="${href}" target="_blank" rel="noreferrer">${href}</a>`;
      }
      return l;
    })
    .join("\n");

  if (url) {
    // click-through convenience
  }
}

async function loadGraph(dimension) {
  const resp = await fetch(`${API}/graph?dimension=${encodeURIComponent(dimension)}`);
  if (!resp.ok) {
    detailEl.textContent = `未找到维度: ${dimension}`;
    detailEl.classList.add("muted");
    cy.elements().remove();
    return;
  }
  const payload = await resp.json();
  const elements = [
    ...payload.nodes.map((n) => ({
      data: {
        id: n.id,
        label: n.label,
        kind: n.kind,
        color: colorByKind[n.kind] || "#8fa399",
        meta: n.meta,
      },
    })),
    ...payload.edges.map((e, idx) => ({
      data: {
        id: `e${idx}`,
        source: e.from_id,
        target: e.to_id,
        rel: e.rel,
      },
    })),
  ];
  cy.elements().remove();
  cy.add(elements);
  cy.layout({ name: "cose", animate: true, animationDuration: 600, fit: true, padding: 30 }).run();
}

cy.on("tap", "node", (evt) => {
  renderDetail(evt.target);
});

document.getElementById("search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const dimension = document.getElementById("dimension").value.trim();
  if (!dimension) return;
  await loadGraph(dimension);
});

document.getElementById("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = document.getElementById("question").value.trim();
  const dimension = document.getElementById("dimension").value.trim() || undefined;
  if (!question) return;
  answerEl.classList.remove("muted");
  answerEl.textContent = "思考中…";
  const resp = await fetch(`${API}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, dimension }),
  });
  const data = await resp.json();
  answerEl.textContent = data.answer || JSON.stringify(data);
});

// bootstrap sample
document.getElementById("dimension").value = "trade_gmv";
fetch(`${API}/dimensions/trade_gmv`)
  .then((r) => (r.ok ? loadGraph("trade_gmv") : null))
  .catch(() => {});
