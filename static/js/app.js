/* 文件管理系统前端逻辑（原生 JS，无框架依赖） */
(() => {
  "use strict";

  // ---------- 全局状态 ----------
  const state = {
    parentId: 0,          // 当前目录（0 = 根）
    page: 1,
    keyword: "",          // 非空时为全局搜索模式
    sort: "updated_at",
    order: "desc",
    total: 0,
    pageSize: 50,
  };

  const $ = (id) => document.getElementById(id);
  const tbody = $("file-tbody");

  // ---------- 通用请求封装：统一处理 401 跳登录 ----------
  async function api(url, options = {}) {
    const res = await fetch(url, options);
    if (res.status === 401) { location.href = "/login"; throw new Error("unauthorized"); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `请求失败（${res.status}）`);
    return data;
  }
  const jsonBody = (body) => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  // ---------- 格式化 ----------
  function fmtSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    if (bytes < 1024 * 1024 * 1024) return (bytes / 1048576).toFixed(1) + " MB";
    return (bytes / 1073741824).toFixed(2) + " GB";
  }

  // ---------- 列表渲染 ----------
  async function loadList() {
    const params = new URLSearchParams({
      parent_id: state.parentId, page: state.page,
      sort: state.sort, order: state.order, page_size: state.pageSize,
    });
    if (state.keyword) params.set("keyword", state.keyword);

    const data = await api("/api/nodes?" + params);
    state.total = data.total;
    renderBreadcrumb(data.breadcrumb, data.keyword);
    renderRows(data.items);
    renderPager();

    const searching = !!state.keyword;
    $("empty-tip").hidden = !(!searching && data.total === 0);
    $("search-empty").hidden = !(searching && data.total === 0);
    $("list-hint").textContent = searching
      ? `全局搜索「${state.keyword}」，共 ${data.total} 项（点击面包屑可返回目录）`
      : `共 ${data.total} 项`;
  }

  function renderBreadcrumb(chain, keyword) {
    const nav = $("breadcrumb");
    if (keyword) {
      nav.innerHTML = `<a data-id="0">全部文件</a> <span class="sep">›</span> 搜索「${escapeHtml(keyword)}」`;
    } else {
      nav.innerHTML = chain.map((c, i) =>
        (i ? '<span class="sep">›</span> ' : "") +
        (i === chain.length - 1
          ? escapeHtml(c.name === "root" ? "全部文件" : c.name)
          : `<a data-id="${c.id}">${c.name === "root" ? "全部文件" : escapeHtml(c.name)}</a>`)
      ).join("");
    }
    nav.querySelectorAll("a").forEach((a) =>
      a.addEventListener("click", () => enterFolder(Number(a.dataset.id))));
  }

  function renderRows(items) {
    tbody.innerHTML = "";
    if (state.keyword) {
      // 搜索模式附加路径列
      items.forEach((it) => tbody.append(buildRow(it, it.path)));
    } else {
      items.forEach((it) => tbody.append(buildRow(it)));
    }
  }

  function buildRow(it, pathText) {
    const tr = document.createElement("tr");

    const nameTd = document.createElement("td");
    const nameDiv = document.createElement("div");
    nameDiv.className = "file-name";
    nameDiv.append(document.createTextNode(icon(it)));
    const label = document.createElement("span");
    label.textContent = it.name;
    if (it.type === "folder") {
      nameDiv.classList.add("clickable");
      nameDiv.title = "打开文件夹";
      nameDiv.addEventListener("click", () => enterFolder(it.id));
    }
    nameDiv.append(label);
    if (pathText) {
      const path = document.createElement("span");
      path.className = "file-size";
      path.textContent = "  （" + pathText + "）";
      nameDiv.append(path);
    }
    nameTd.append(nameDiv);

    const sizeTd = document.createElement("td");
    sizeTd.className = "file-size";
    sizeTd.textContent = it.type === "folder" ? "—" : fmtSize(it.size);

    const timeTd = document.createElement("td");
    timeTd.className = "file-time";
    timeTd.textContent = it.updated_at;

    const opsTd = document.createElement("td");
    opsTd.className = "col-ops";
    if (it.type === "file") {
      opsTd.append(opBtn("下载", "download", () =>
        { location.href = `/api/download/${it.id}`; }));
    }
    opsTd.append(opBtn("重命名", "ghost rename", () => openRename(it)));
    opsTd.append(opBtn("删除", "ghost danger-text", () => deleteNode(it)));

    tr.append(nameTd, sizeTd, timeTd, opsTd);
    return tr;
  }

  const icon = (it) => it.type === "folder" ? "📂" : "📄";
  const opBtn = (text, cls, onclick) => {
    const b = document.createElement("button");
    b.className = "btn " + cls; b.textContent = text;
    b.addEventListener("click", onclick);
    return b;
  };
  const escapeHtml = (s) => s.replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function renderPager() {
    const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
    $("page-info").textContent = `第 ${state.page} / ${totalPages} 页`;
    $("prev-page").disabled = state.page <= 1;
    $("next-page").disabled = state.page >= totalPages;
  }

  async function enterFolder(id) {
    state.parentId = id;
    state.page = 1;
    state.keyword = "";
    $("search-box").value = "";
    await loadList();
  }

  // ---------- 上传（FR-02）----------
  $("btn-upload").addEventListener("click", () => $("file-input").click());
  $("file-input").addEventListener("change", async (e) => {
    const files = [...e.target.files];
    e.target.value = "";
    if (!files.length) return;

    const panel = $("upload-panel");
    panel.hidden = false;
    panel.innerHTML = "";

    const MAX = 50 * 1024 * 1024;
    const form = new FormData();
    form.append("parent_id", state.parentId);
    files.forEach((f) => {
      form.append("files", f);
      const item = document.createElement("div");
      item.className = "upload-item";
      item.innerHTML = `<span class="upload-name"></span><span class="upload-status doing">上传中…</span>`;
      item.querySelector(".upload-name").textContent = f.name;
      panel.append(item);
    });

    try {
      const data = await api("/api/upload", { method: "POST", body: form });
      [...panel.querySelectorAll(".upload-item")].forEach((item, i) => {
        const r = data.results[i];
        const status = item.querySelector(".upload-status");
        status.classList.remove("doing");
        if (r.ok) { status.classList.add("ok"); status.textContent = r.renamed ? `成功（重命名为 ${r.name}）` : "成功"; }
        else { status.classList.add("fail"); status.textContent = "失败：" + r.message; }
      });
    } catch (err) {
      panel.querySelectorAll(".upload-status").forEach((s) => {
        s.classList.remove("doing"); s.classList.add("fail"); s.textContent = "失败：" + err.message;
      });
    }
    state.page = 1;
    await loadList();
  });

  // ---------- 新建文件夹（FR-06）----------
  $("btn-newfolder").addEventListener("click", async () => {
    const name = prompt("请输入文件夹名称：");
    if (name === null) return;
    try {
      await api("/api/folders", jsonBody({ name, parent_id: state.parentId }));
      await loadList();
    } catch (err) { alert(err.message); }
  });

  // ---------- 重命名（FR-07）----------
  let renameTarget = null;
  const dialog = $("rename-dialog");
  function openRename(node) {
    renameTarget = node;
    $("rename-input").value = node.name;
    $("rename-error").hidden = true;
    dialog.showModal();
  }
  $("rename-cancel").addEventListener("click", () => dialog.close());
  $("rename-ok").addEventListener("click", async (e) => {
    e.preventDefault();
    try {
      const data = await api(`/api/nodes/${renameTarget.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: $("rename-input").value }),
      });
      dialog.close();
      if (data.renamed) alert(`目标名称已存在，已自动命名为：${data.name}`);
      await loadList();
    } catch (err) {
      const errBox = $("rename-error");
      errBox.textContent = err.message; errBox.hidden = false;
    }
  });

  // ---------- 删除（FR-05，二次确认）----------
  async function deleteNode(node) {
    const kind = node.type === "folder" ? "文件夹及其全部内容" : "文件";
    if (!confirm(`确定要删除${kind}「${node.name}」吗？\n删除后不可恢复！`)) return;
    try {
      await api(`/api/nodes/${node.id}`, { method: "DELETE" });
      await loadList();
    } catch (err) { alert(err.message); }
  }

  // ---------- 搜索 / 排序 / 分页 ----------
  let searchTimer = null;
  $("search-box").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.keyword = e.target.value.trim();
      state.page = 1;
      loadList();
    }, 300);
  });
  $("sort-field").addEventListener("change", (e) => { state.sort = e.target.value; loadList(); });
  $("sort-order").addEventListener("change", (e) => { state.order = e.target.value; loadList(); });
  $("prev-page").addEventListener("click", () => { state.page--; loadList(); });
  $("next-page").addEventListener("click", () => { state.page++; loadList(); });

  // ---------- 登出 / 初始化 ----------
  $("logout-btn").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST" }).catch(() => {});
    location.href = "/login";
  });

  api("/api/me").then((d) => { $("current-user").textContent = d.user; loadList(); })
    .catch(() => { location.href = "/login"; });
})();
