# 文件管理系统（面试作品 · V1.0）

依据《文件管理系统需求文档 V1.0》（PRD-FMS-2026-001）实现的内部网页版文件管理系统，覆盖本期全部 P0 必交付项与 P1 尽量交付项。

## 技术选型

| 项 | 选型 | 理由 |
|----|------|------|
| 后端 | Python 3.12 + Flask | 轻量成熟、社区组件丰富，满足前后端分离 HTTP API 要求 |
| 元数据存储 | SQLite（Python 标准库 sqlite3） | 嵌入式方案，零部署成本，满足"服务重启后元数据不丢失"；写入加锁 + 事务保证操作一致性 |
| 文件存储 | 服务端本地磁盘 `data/storage/` | 符合本期边界（不接对象存储）；以 UUID 随机存储名落盘，实现存储隔离 |
| 前端 | 原生 HTML / CSS / JS | 无构建步骤，结构清晰，聚焦核心链路体验 |

## 运行说明

```bash
# 1. 安装依赖（建议虚拟环境）
pip install -r requirements.txt

# 2. 启动服务
python run.py

# 3. 浏览器访问
http://127.0.0.1:5000
```

预置账号（可通过环境变量覆盖）：

- 账号：`qwer`（`FMS_ADMIN_USER`）
- 密码：`qwerlol`（`FMS_ADMIN_PASS`）

首次启动自动创建 `data/` 目录（SQLite 元数据库 + 文件存储），该目录已加入 `.gitignore`。

## 接口说明

所有业务接口需登录态（Cookie 会话），未登录统一返回 `401`。

| 方法 | 路径 | 关键参数 | 响应 |
|------|------|----------|------|
| POST | `/api/login` | JSON：`username`、`password` | `{"user": "admin"}`，失败 401 |
| POST | `/api/logout` | — | `{"ok": true}` |
| GET | `/api/me` | — | `{"user": "admin"}` / 401 |
| GET | `/api/nodes` | `parent_id`、`keyword`（全局搜索）、`sort`（name/size/updated_at）、`order`（asc/desc）、`page`、`page_size` | `{"items":[], "total", "page", "breadcrumb":[], "keyword"}` |
| POST | `/api/upload` | multipart：`parent_id` + `files[]`（可多选） | `{"results":[{name,id,ok,renamed,message}], "success", "failed"}` |
| GET | `/api/download/<id>` | 路径参数文件 id | 文件流（`Content-Disposition` 映射回原始文件名） |
| POST | `/api/folders` | JSON：`name`、`parent_id` | `{"id", "name", "renamed"}` |
| PATCH | `/api/nodes/<id>` | JSON：`name` | `{"id", "name", "renamed"}` |
| DELETE | `/api/nodes/<id>` | 路径参数 id | `{"ok": true, "deleted": n}`，文件夹级联删除 |

## 设计说明

### 数据模型

单表 `nodes` 自关联表达目录树（文件与文件夹统一建模）：

```sql
nodes(id, type 'file'|'folder', name, parent_id → nodes.id,
      stored_name, size, mime, created_at, updated_at)
UNIQUE(parent_id, name)   -- 同目录名称唯一
```

- 文件本体不存数据库，仅记录元数据；`stored_name` 为 UUID 随机存储名。
- 目录层级在应用层校验（≤10 层），避免递归查询开销。

### 存储组织

```
data/
├── fms.db        # SQLite 元数据库
└── storage/      # 文件本体，UUID 命名，与用户可见名解耦
```

### 关键实现取舍

1. **重名处理**（PRD 3.3 开放问题）：采用建议策略——自动追加序号 `报告(1).docx`；上传与重命名接口返回 `renamed` 标记，前端有明确提示。
2. **搜索范围**：采用建议策略——全局搜索，结果附带完整路径便于定位。
3. **路径穿越防护**：接口层以节点 id 而非路径定位文件；存储名仅由服务端生成，`storage_path()` 再做白名单目录校验；带 `../`、绝对路径特征的输入在上传入口提前拒绝。
4. **操作一致性**：删除在单事务内完成元数据级联清理后再清理文件本体，避免"部分成功"中间状态；上传失败自动清理半成品文件。
5. **性能**：列表强制分页（默认 50 条，上限 200）；文件上传使用独立请求线程，不阻塞浏览/删除等操作。
6. **异常与边界**：文件名覆盖空格、`#`、`%`、Emoji、超长名（255）、Windows 保留名等场景的校验与提示。

### 未完成项（如实标注）

- **P2 未实现**：图片预览（FR-10）、批量操作（FR-11）、存储配额（FR-12）。按 PRD 本期边界属预留项。
- **已知限制**：回收站为物理删除（第 7 章规划项）；数据模型已预留 `type` 字段区分对象，接入回收站仅需增加软删除标记位。

### 对后续规划的预留考虑

- **大文件分片上传**：`nodes.stored_name` 与用户可见名解耦，后续可在 storage 层叠加分片合并逻辑而不动元数据模型。
- **多用户与配额**：`nodes` 表可平滑增加 `owner_id` 列；接口鉴权已集中在 `login_required` 装饰器，可扩展为按用户过滤。
