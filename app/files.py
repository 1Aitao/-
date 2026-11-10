# -*- coding: utf-8 -*-
"""文件核心链路：列表/搜索/排序（FR-03/08/09）、上传（FR-02）、下载（FR-04）、删除（FR-05）。"""
import os
import time

from flask import Blueprint, jsonify, request, send_file

from . import config, db
from .auth import login_required
from .security import new_stored_name, storage_path, validate_name

bp = Blueprint("files", __name__)


# ---------- 通用工具 ----------

def get_node(node_id: int):
    rows = db.query("SELECT * FROM nodes WHERE id = ?", (node_id,))
    return db.row_to_dict(rows[0]) if rows else None


def unique_name(parent_id, name: str, exclude_id=None) -> str:
    """同目录名称唯一约束下的重名处理（PRD 3.3 开放问题，采用建议策略）：
    自动追加序号，如 报告.docx -> 报告(1).docx。
    """
    base, dot, ext = name.rpartition(".")
    if not dot or not base:
        base, ext = name, ""
    candidate, i = name, 1
    # 根目录下 parent_id 存 NULL（约定 0 表示根），查询需用 IS NULL 语义
    parent_param = None if parent_id == 0 else parent_id
    while True:
        sql = "SELECT id FROM nodes WHERE parent_id IS ? AND name = ?"
        params = [parent_param, candidate]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        if not db.query(sql, params):
            return candidate
        candidate = f"{base}({i}){dot}{ext}" if dot else f"{base}({i})"
        i += 1


def check_parent(parent_id) -> dict:
    """校验父目录存在且确为文件夹；根目录用 parent_id=0 表示。"""
    if parent_id == 0:
        return {"id": 0, "type": "folder", "name": "root"}
    node = get_node(parent_id)
    if not node or node["type"] != "folder":
        raise ValueError("目标文件夹不存在")
    return node


def folder_depth(node: dict) -> int:
    """计算某节点到根的层级深度。"""
    depth, cur = 0, node
    while cur["parent_id"]:
        cur = get_node(cur["parent_id"])
        if cur is None:
            break
        depth += 1
    return depth


def breadcrumb(node: dict) -> list:
    """由任一节点回溯出面包屑路径（FR-06）。"""
    chain = []
    cur = node
    while cur:
        chain.append({"id": cur["id"], "name": cur["name"]})
        cur = get_node(cur["parent_id"]) if cur["parent_id"] else None
    chain.reverse()
    return chain


# ---------- 列表 / 搜索 / 排序（分页） ----------

@bp.get("/api/nodes")
@login_required
def list_nodes():
    """目录浏览与全局搜索统一入口。

    - 无 keyword：列出 parent_id 下直属内容（FR-03）
    - 有 keyword：全局模糊搜索（PRD 3.3 建议策略），并附完整路径
    - 排序字段/方向使用白名单校验，分页避免全量返回（PRD 4.3）
    """
    try:
        parent_id = int(request.args.get("parent_id", 0))
    except ValueError:
        return jsonify({"error": "parent_id 不合法"}), 400

    keyword = (request.args.get("keyword") or "").strip()
    sort = request.args.get("sort", "updated_at")
    order = request.args.get("order", "desc")
    if sort not in config.SORT_FIELDS or order not in config.SORT_ORDERS:
        return jsonify({"error": "排序参数不合法"}), 400

    try:
        page = max(1, int(request.args.get("page", 1)))
        page_size = min(200, max(1, int(request.args.get("page_size", config.PAGE_SIZE_DEFAULT))))
    except ValueError:
        return jsonify({"error": "分页参数不合法"}), 400

    where, params = [], []
    if keyword:
        # 全局搜索：名称模糊匹配（转义 LIKE 通配符）
        escaped = keyword.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        where.append("name LIKE ? ESCAPE '\\' COLLATE NOCASE")
        params.append(f"%{escaped}%")
    else:
        # 约定 parent_id=0 表示根目录，根下子项存的是 NULL，需用 IS NULL 匹配
        where.append("parent_id IS ?")
        params.append(None if parent_id == 0 else parent_id)

    cond = " AND ".join(f"({w})" for w in where)
    total = db.query(f"SELECT COUNT(*) AS c FROM nodes WHERE {cond}", params)[0]["c"]
    rows = db.query(
        f"""SELECT * FROM nodes WHERE {cond}
            ORDER BY type = 'folder' DESC, {sort} {order.upper()}, id ASC
            LIMIT ? OFFSET ?""",
        params + [page_size, (page - 1) * page_size],
    )

    items = []
    for r in rows:
        item = db.row_to_dict(r)
        if keyword:
            # 搜索结果附完整路径，便于定位
            item["path"] = " / ".join(c["name"] for c in breadcrumb(item))
        items.append(item)

    parent = get_node(parent_id) if parent_id else {"id": 0, "name": "root", "parent_id": None}
    return jsonify({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "breadcrumb": breadcrumb(parent),
        "keyword": keyword,
    })


# ---------- 上传 ----------

@bp.post("/api/upload")
@login_required
def upload():
    """多文件上传（FR-02）。

    单文件超 50MB 拒绝并给出明确提示，但不影响同批其他文件（PRD 3.1）。
    文件本体以随机存储名落盘，元数据与落盘先后失败时互相清理，避免脏状态。
    """
    try:
        parent_id = int(request.form.get("parent_id", 0))
        parent = check_parent(parent_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "未选择文件"}), 400

    results = []
    for f in files:
        original = f.filename or ""
        # 恶意内容提前拒绝（../、绝对路径等，PRD 4.1）
        from .security import TRAVERSAL_PATTERN
        if TRAVERSAL_PATTERN.search(original):
            results.append({"name": original, "ok": False, "message": "文件名包含非法路径字符"})
            continue
        try:
            display_name = validate_name(os.path.basename(original.replace("\\", "/")))
        except ValueError as e:
            results.append({"name": original, "ok": False, "message": str(e)})
            continue

        # 读取内容前先校验大小：超限直接拒绝，不做无谓 IO
        f.stream.seek(0, os.SEEK_END)
        size = f.stream.tell()
        if size > config.MAX_FILE_SIZE:
            results.append({"name": original, "ok": False,
                            "message": f"文件超过 50MB 上限（{size / 1024 / 1024:.1f}MB）"})
            continue
        f.stream.seek(0)

        stored = new_stored_name(display_name)
        dest = storage_path(stored)
        try:
            f.save(dest)
            actual_size = os.path.getsize(dest)
            if actual_size > config.MAX_FILE_SIZE:
                raise ValueError(f"文件超过 50MB 上限")
            final_name = unique_name(parent_id, display_name)
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            node_id = db.execute(
                """INSERT INTO nodes (type, name, parent_id, stored_name, size, mime, created_at, updated_at)
                   VALUES ('file', ?, ?, ?, ?, ?, ?, ?)""",
                (final_name, parent_id if parent_id else None, stored,
                 actual_size, f.mimetype or "application/octet-stream", now, now),
            )
            results.append({"name": final_name, "id": node_id, "ok": True,
                            "renamed": final_name != display_name})
        except Exception as e:
            # 落盘或入库失败时清理半成品，保证一致性
            if os.path.exists(dest):
                try:
                    os.remove(dest)
                except OSError:
                    pass
            results.append({"name": original, "ok": False, "message": str(e) or "上传失败"})

    # 目录 mtime 刷新（ parent 为虚拟根时跳过）
    if parent.get("id"):
        db.execute("UPDATE nodes SET updated_at = ? WHERE id = ?",
                   (time.strftime("%Y-%m-%d %H:%M:%S"), parent["id"]))

    failed = [r for r in results if not r["ok"]]
    return jsonify({"results": results, "success": len(results) - len(failed),
                    "failed": len(failed)})


# ---------- 下载 ----------

@bp.get("/api/download/<int:node_id>")
@login_required
def download(node_id):
    """下载单个文件，二进制无损（FR-04）。

    通过 as_attachment 将随机存储名映射回用户可见的原始文件名。
    """
    node = get_node(node_id)
    if not node or node["type"] != "file":
        return jsonify({"error": "文件不存在"}), 404
    path = storage_path(node["stored_name"])
    if not os.path.exists(path):
        return jsonify({"error": "文件已丢失，请联系管理员"}), 404
    return send_file(path, as_attachment=True, download_name=node["name"])


# ---------- 删除 ----------

def _collect_subtree(node_id: int, acc: list):
    """递归收集子树（文件夹删除需级联，回收站列入后续规划）。"""
    acc.append(node_id)
    for r in db.query("SELECT id FROM nodes WHERE parent_id = ?", (node_id,)):
        _collect_subtree(r["id"], acc)


@bp.delete("/api/nodes/<int:node_id>")
@login_required
def delete_node(node_id):
    """物理删除（前端已做二次确认）。文件夹级联删除，文件与元数据同批清理。"""
    node = get_node(node_id)
    if not node:
        return jsonify({"error": "条目不存在"}), 404

    ids, stored_files = [], []
    with db.transaction() as conn:
        _collect_subtree(node_id, ids)
        marks = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT stored_name FROM nodes WHERE type = 'file' AND id IN ({marks})", ids
        ).fetchall()
        stored_files = [r["stored_name"] for r in rows if r["stored_name"]]
        conn.execute(f"DELETE FROM nodes WHERE id IN ({marks})", ids)

    # 元数据提交成功后再清理文件本体；残留文件可由运维清理，不影响一致性
    for stored in stored_files:
        try:
            os.remove(storage_path(stored))
        except OSError:
            pass
    return jsonify({"ok": True, "deleted": len(ids)})
