# -*- coding: utf-8 -*-
"""目录管理（FR-06）与重命名（FR-07）。"""
import time

from flask import Blueprint, jsonify, request

from . import config
from .auth import login_required
from .files import breadcrumb, check_parent, folder_depth, get_node, unique_name
from .db import execute
from .security import validate_name

bp = Blueprint("folders", __name__)


@bp.post("/api/folders")
@login_required
def create_folder():
    """新建文件夹，同目录重名时自动追加序号（与文件重名策略一致）。"""
    data = request.get_json(silent=True) or {}
    try:
        parent_id = int(data.get("parent_id", 0))
        parent = check_parent(parent_id)
        name = validate_name(data.get("name"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # 目录层级限制（PRD 3.1 FR-06 建议不超过 10 层）
    if parent.get("id") and folder_depth(parent) + 1 >= config.MAX_DIR_DEPTH:
        return jsonify({"error": f"目录层级已达上限（{config.MAX_DIR_DEPTH} 层）"}), 400

    final_name = unique_name(parent_id, name)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    node_id = execute(
        """INSERT INTO nodes (type, name, parent_id, size, created_at, updated_at)
           VALUES ('folder', ?, ?, 0, ?, ?)""",
        (final_name, parent_id if parent_id else None, now, now),
    )
    return jsonify({"id": node_id, "name": final_name, "renamed": final_name != name})


@bp.patch("/api/nodes/<int:node_id>")
@login_required
def rename(node_id):
    """重命名文件或文件夹：非空与合法字符校验，同目录唯一。"""
    node = get_node(node_id)
    if not node:
        return jsonify({"error": "条目不存在"}), 404

    data = request.get_json(silent=True) or {}
    try:
        name = validate_name(data.get("name"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    final_name = unique_name(node["parent_id"], name, exclude_id=node_id)
    execute("UPDATE nodes SET name = ?, updated_at = ? WHERE id = ?",
            (final_name, time.strftime("%Y-%m-%d %H:%M:%S"), node_id))
    return jsonify({"id": node_id, "name": final_name, "renamed": final_name != name,
                    "old_name": node["name"]})
