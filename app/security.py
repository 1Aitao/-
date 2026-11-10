# -*- coding: utf-8 -*-
"""安全相关工具：路径穿越防护、文件名合法性校验、随机存储名。"""
import os
import re
import uuid

from . import config

# Windows 保留名与非法字符；同时覆盖 PRD 3.2 提到的空格、#、% 等特殊字符场景
ILLEGAL_CHARS = r'<>:"/\|?*'
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL",
                  "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                  "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}
MAX_NAME_LEN = 255


def validate_name(name: str) -> str:
    """校验文件/文件夹名称，返回去首尾空格后的名称；不合法抛 ValueError。"""
    name = (name or "").strip()
    if not name or name in {".", ".."}:
        raise ValueError("名称不能为空")
    if len(name) > MAX_NAME_LEN:
        raise ValueError("名称过长（最多 255 字符）")
    for ch in ILLEGAL_CHARS:
        if ch in name:
            raise ValueError(f"名称包含非法字符：{ch}")
    if name.split(".")[0].upper() in RESERVED_NAMES:
        raise ValueError("名称为系统保留名")
    if any(ord(c) < 32 for c in name):
        raise ValueError("名称包含不可见控制字符")
    return name


def new_stored_name(original_name: str) -> str:
    """生成随机存储名（PRD 4.1 存储隔离）：
    服务端不使用用户可见文件名落盘，下载时再映射回原始名称，
    同时杜绝任何依赖原始名的执行入口。
    """
    ext = os.path.splitext(original_name)[1][:16]  # 保留扩展名便于识别，截断防超长
    return uuid.uuid4().hex + ext


def storage_path(stored_name: str) -> str:
    """由随机存储名拼出落盘绝对路径。

    stored_name 只能来自服务端生成的 uuid（而非用户输入），
    此处再校验一层，杜绝路径穿越（PRD 4.1）。
    """
    base = os.path.abspath(config.STORAGE_DIR)
    name = os.path.basename(stored_name)  # 剥掉任何路径成分
    full = os.path.abspath(os.path.join(base, name))
    if not full.startswith(base + os.sep):
        raise ValueError("非法存储路径")
    return full


# 快速识别明显带穿越意图的输入（用于接口层提前拒绝并给出明确提示）
TRAVERSAL_PATTERN = re.compile(r"(\.\.[/\\])|(^[/\\])|([A-Za-z]:[/\\])")
