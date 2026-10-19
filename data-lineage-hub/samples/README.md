# Samples

内置脱敏样例位于 `tests/fixtures/`：

- `ds/tasks.json` — DolphinScheduler 任务
- `git_repo/sql/` — 清洗 SQL
- `yuque/docs.json` — 语雀口径文档

运行：

```bash
lineage sync --fixture
lineage dim show trade_gmv
```
