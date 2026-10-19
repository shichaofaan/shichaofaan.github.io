# data-lineage-hub

把 **DolphinScheduler 调度**、**Git 清洗代码**、**语雀文档** 索引到一起，回答：

> 某一个维度的数据，是如何清洗出来的？

开发顺序：**CLI/API 索引 → 血缘图谱 → 问答助手**。

## 快速开始

```bash
cd data-lineage-hub
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# 使用内置脱敏 fixture 同步并查询
lineage sync --fixture
lineage dim show trade_gmv
lineage doctor

# HTTP API
lineage serve
# GET http://127.0.0.1:8000/dimensions/trade_gmv
# GET http://127.0.0.1:8000/graph?dimension=trade_gmv
# POST http://127.0.0.1:8000/ask  {"question":"trade_gmv 是怎么洗的？"}
```

图谱前端（可选）：

```bash
cd web && npm install && npm run dev
```

## 配置

见 [`.env.example`](.env.example)。密钥只走环境变量 / CI Secrets。

团队标签规范见 [`docs/conventions.md`](docs/conventions.md)。

## CLI

| 命令 | 作用 |
|------|------|
| `lineage sync` | 拉取三源并建边 |
| `lineage sync --fixture` | 使用测试样例，无需真实凭证 |
| `lineage dim show <name>` | 打印维度 → 任务 / 代码 / 文档 |
| `lineage doctor` | 检查缺标签与断链 |
| `lineage serve` | 启动 FastAPI |

## 架构

```
DS / Git / 语雀  →  connectors  →  extractors  →  linkers  →  SQLite
                                                              ↓
                                         CLI / REST / 图谱 UI / QA
```

关联策略：

1. **显式** `dim:<id>`（高置信）
2. **自动** 表字段名匹配（低置信，doctor 标黄）

## 测试

```bash
pytest -q
```
