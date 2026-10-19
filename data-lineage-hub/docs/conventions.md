# 维度标签约定（dim）

三源要对齐，优先使用显式标签 `dim:<id>`。

## 写法

```text
dim:trade_gmv
```

- `id` 使用小写字母、数字、下划线，例如 `trade_gmv`、`user_active_days`
- 同一业务口径在 DS / Git / 语雀中必须使用**完全相同**的 `dim_id`

## 落点

| 来源 | 放哪里 |
|------|--------|
| DolphinScheduler | 任务描述（description）、任务参数、或脚本首行注释 |
| Git | SQL/脚本文件头注释，或相关代码块附近 |
| 语雀 | 文档标题前缀，或正文首行 |

### 示例：SQL 文件头

```sql
-- dim:trade_gmv
-- 口径：有效订单 GMV，剔除取消单
INSERT INTO dws.trade_gmv ...
```

### 示例：语雀标题

```text
dim:trade_gmv 交易 GMV 口径说明
```

## 无标签时

系统会尝试从 SQL / 文档中抽取 `库.表.字段` 并做模糊匹配，置信度较低。
运行 `lineage doctor` 查看断链与缺标签项，尽快补上显式 `dim:`。
