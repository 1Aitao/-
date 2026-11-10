# -*- coding: utf-8 -*-
"""全局配置。账号信息随部署配置下发，支持环境变量覆盖。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据目录（元数据库 + 文件本体），可通过 FMS_DATA_DIR 环境变量重定向
DATA_DIR = os.environ.get("FMS_DATA_DIR") or os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "fms.db")
STORAGE_DIR = os.path.join(DATA_DIR, "storage")

# 预置管理员账号（本期不开放注册）
ADMIN_USERNAME = os.environ.get("FMS_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("FMS_ADMIN_PASS", "admin123")

# 会话密钥（生产环境应通过环境变量注入随机值）
SECRET_KEY = os.environ.get("FMS_SECRET_KEY", "fms-dev-secret-key-change-me")

# 业务限制
MAX_FILE_SIZE = 50 * 1024 * 1024   # 单文件上限 50MB
MAX_CONTENT_LENGTH = 60 * 1024 * 1024  # 请求体上限（预留 multipart 开销）
MAX_DIR_DEPTH = 10                 # 目录层级建议不超过 10 层
PAGE_SIZE_DEFAULT = 50             # 列表默认分页大小

# 允许的排序字段与方向（白名单，防止 SQL 注入拼接）
SORT_FIELDS = {"name", "size", "updated_at"}
SORT_ORDERS = {"asc", "desc"}
