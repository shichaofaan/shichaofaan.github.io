---
layout:     post
title:      Flink CDC 与 binlog
subtitle:   一次 MySQL binlog 文件块损坏的故障复盘
date:       2025-09-24
author:     shichaofaan
header-img: img/post-bg-hacker.jpg
catalog: true
tags:
    - Flink
    - Flink CDC
    - MySQL
---

Flink CDC 读 MySQL，底层跟的是 binlog。多数时候问题出在权限、GTID、表结构变更，真正碰到 **binlog 文件块损坏** 的次数不多，但一旦碰上，作业会反复失败，位点卡住，下游湖表停更。

这篇记录一次从报错到恢复的过程，方便以后对照。

## 案例现象

任务：Flink CDC 同步订单库 `order_*` 若干表到 Paimon 主键表，并行度 4，`scan.startup.mode=latest-offset` 上线后已稳定跑两个月。

某日凌晨 02:17 开始，Job 持续重启，TaskManager 日志反复出现类似错误（简化）：

```text
Caused by: java.io.IOException: binlog checksum mismatch / corrupt event
  at ... BinlogReader ...
Caused by: EventDataDeserializationException: Failed to deserialize data of EventHeaderV4
...
The binlog file mysql-bin.000384 near position 194563728 looks corrupted
```

同时 MySQL 侧 `SHOW BINARY LOGS` 能看到 `mysql-bin.000384`，主从复制也在同一位点附近报 checksum 相关错误。Flink 每次拉起都从 checkpoint 保存的 binlog 位点继续读，读到坏块就炸，形成重启循环。

下游表现：Paimon 表停在 02:10 左右的数据，Lag 监控按「源库最新事务时间 - 湖表最大事件时间」计算，延迟持续增大。

## 原因确认

DBA 在主机上做了校验（示意）：

```bash
# 检查 binlog 完整性（工具因版本而异）
mysqlbinlog --verify-binlog-checksum mysql-bin.000384 > /tmp/bin384.sql
# 在可疑 position 附近截断查看
mysqlbinlog --start-position=194560000 --stop-position=194570000 mysql-bin.000384
```

现象是某个 event 中间二进制内容异常，checksum 对不上。根因后来定位到：**凌晨磁盘阵列一次短暂故障，binlog 所在盘出现局部写损坏**；主库当时 `sync_binlog` 与刷盘策略下，坏块已经落在 `mysql-bin.000384`。从库通过复制也读到了坏事件，复制线程中断。

这不是 Flink 的 bug，但 Flink CDC 作为 binlog 消费者，会正面撞上损坏点。

## 处理思路：跳过坏块还是切新文件？

第一反应「跳过坏 position 继续读」风险很大：跳过的可能不只是噪声，还可能包含真实的 INSERT/UPDATE。对订单这种不能丢的数据，**不能靠瞎跳位点糊弄过去**。

我们按这个顺序做：

### 1. 冻结自动重启，避免狂刷

先把作业停止（或把重启策略临时关掉），避免每分钟打一次坏位点，把错误日志和元数据冲乱。

### 2. 确认损坏范围

DBA 确认：

- 损坏集中在 `mysql-bin.000384` 某一小段；
- 其后若强行 `FLUSH LOGS` 切到 `mysql-bin.000385`，新文件正常；
- 从库在坏点之后无法靠原 binlog 继续，需要重新搭建或从备份追。

对 Flink 而言：checkpoint 里记的是坏文件坏位点，继续用这个 savepoint/checkpoint 起不来。

### 3. 选恢复策略

可选路径大致三个：

| 策略 | 做法 | 风险 |
| --- | --- | --- |
| A. 跳过坏位点 | 改 starting position 到坏块之后 | 可能丢变更 |
| B. 换新 binlog 文件 + 补数 | 从完好位点 / 新文件起，对窗口期做批补 | 运维复杂，但可控 |
| C. 全量重做 | snapshot 重做 + 再切增量 | 最稳，耗时长 |

订单表日增几千万级，全量窗口太长，选了 **B**：

1. 源库评估后切换 binlog（确保新文件完好）。
2. 取损坏时间窗口 `[02:10, 03:05]`（含缓冲）。
3. Flink CDC 作业用新的启动位点（完好 position / GTID）起增量。
4. 窗口期内用 Spark 批任务按主键从源库拉快照，写入同一张 Paimon 表做 upsert 补齐。

伪代码示意补数：

```sql
-- Spark 批补：按更新时间窗口拉源库
INSERT INTO paimon.db.order_wide
SELECT *
FROM jdbc_source.order_wide
WHERE updated_at >= '2025-09-24 02:10:00'
  AND updated_at <  '2025-09-24 03:05:00';
```

Paimon 主键表 upsert，批补与后续增量重叠的主键会被覆盖成一致结果。

### 4. 校验

补完后做三套校验：

1. 窗口内源库 `COUNT` / `SUM(amount)` vs 湖表。
2. 按主键抽样 `LEFT JOIN` 找差异。
3. 增量作业追上后，延迟监控恢复到分钟内。

发现约 200 来条差异，多数是窗口边界上的更新，扩大 5 分钟边界重跑批补后对齐。

## Flink 侧配置上的反思

出事时有几个放大问题的点：

1. **重启策略过猛**  
   `restart-strategy.fixed-delay.attempts` 很大，坏位点会无限撞墙。对 CDC 这类外部依赖，失败应尽快告警并人工介入，而不是空转。

2. **只有增量、没有定期对账**  
   若早有按表的日级校验，损坏导致的停更会更快被业务发现；这次是延迟告警先响。

3. **checkpoint 绑死坏位点**  
   恢复时需要「放弃该 checkpoint、用新位点启动」的明确操作手册。提前写好比凌晨现场想要快。

4. **binlog 保留与备份**  
   和 DBA 约定：binlog 盘监控、checksum 校验、损坏时的切换流程，CDC 消费账号只读且限流，避免和业务抢 IO。

## 以后再遇到怎么判

快速判断清单：

```text
1. 是反序列化/checksum 错，还是权限、表结构变更？
2. MySQL 主从复制是否也卡在同一文件同一附近 position？
3. 若主从也坏，基本坐实 binlog 文件问题，别只重启 Flink。
4. 评估能否跳过：不能丢的表 → 切新 binlog + 窗口批补或全量。
5. 启新作业前明确：用哪个 GTID/文件位点，旧 checkpoint 是否作废。
```

## 小结

这次故障不在 Flink SQL 写法，而在 **binlog 物理损坏 + CDC 位点卡死 + 自动重启空转**。处理关键是承认「坏块不可盲目跳过」，用完好位点恢复增量，再用主键表批补把窗口补平。

和 DBA 的协作比改作业参数更重要：磁盘、checksum、主从、binlog 切换，这些决定你能不能在小时级恢复，而不是拖成重做全量。
