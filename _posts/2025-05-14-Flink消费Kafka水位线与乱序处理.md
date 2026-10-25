---
layout:     post
title:      Flink 消费 Kafka
subtitle:   水位线、乱序与迟到数据怎么落地
date:       2025-05-14
author:     shichaofaan
header-img: img/post-bg-debug.png
catalog: true
tags:
    - Flink
    - Kafka
    - 实时计算
---

做实时任务时，Kafka 负责把数据送进来，Flink 负责按业务时间做窗口、去重、关联。业务时间一沾边，就绕不开三件事：**事件时间、水位线、迟到数据**。网上概念文章很多，真正卡在生产里的，往往是参数怎么设、乱序怎么扛、迟到了要不要补。

这篇文章按落地顺序讲：为什么要用事件时间，水位线怎么配，乱序和迟到分别怎么处理，以及几个容易踩的坑。

## 为什么不能只用处理时间

处理时间简单：算子拿到数据的那一刻就是「当前时间」。延迟低、也不用管 Kafka 里字段乱不乱。问题是：同一条业务事件，因为分区堆积、反压、重启重放，到达算子的时刻会差很多。按处理时间开窗，结果会跟着集群状态飘。

事件时间用消息里的业务时间戳（下单时间、埋点时间、采集时间）。窗口边界跟业务对齐，重放、追数据时结果更稳定。代价是你得自己定义「时间推进到哪了」——这就是水位线在干的事。

经验上：对账、UV、会话窗口、按业务日切分这类场景，优先事件时间；监控大盘、纯告警、对时间精度不敏感的，处理时间够用。

## Kafka Source 里怎么取时间戳

Flink 1.14 之后常用新 Source API。消费 Kafka 时，通常在 `KafkaSource` 上挂 `WatermarkStrategy`，从 value 或 header 里解析事件时间：

```java
KafkaSource<OrderEvent> source = KafkaSource.<OrderEvent>builder()
    .setBootstrapServers(brokers)
    .setTopics("order_event")
    .setGroupId("flink-order-uv")
    .setStartingOffsets(OffsetsInitializer.latest())
    .setValueOnlyDeserializer(new OrderEventDeserializer())
    .build();

WatermarkStrategy<OrderEvent> wm = WatermarkStrategy
    .<OrderEvent>forBoundedOutOfOrderness(Duration.ofSeconds(5))
    .withTimestampAssigner((event, ts) -> event.getEventTimeMillis())
    .withIdleness(Duration.ofMinutes(1));

DataStream<OrderEvent> stream = env.fromSource(
    source, wm, "kafka-order-event");
```

几点注意：

1. **时间戳单位统一成毫秒**。Kafka 自带的 `timestamp` 默认是毫秒，业务字段有时是秒，混用会出现窗口全空或全堆在 1970 附近。
2. **优先用业务字段，不要无用 Kafka 消息时间**。Producer 没开 `message.timestamp.type=CreateTime`，或中间有转发 topic，broker 时间跟业务时间会脱节。
3. **反序列化失败的脏数据**要提前滤掉或打到旁路，否则 `getEventTimeMillis()` 抛异常会直接搞挂 Source 任务。

## 水位线：本质是「我愿意等多久」

`forBoundedOutOfOrderness(Duration.ofSeconds(5))` 的含义可以粗理解为：

> 当前观察到的最大事件时间是 T，那我认为 `T - 5s` 之前的数据基本到齐了，窗口可以关了。

乱序容忍越大，结果越完整，但窗口关闭越晚，端到端延迟越高。生产里常见设 3s～30s，具体看上游写入链路：

| 上游特征 | 乱序容忍建议 |
| --- | --- |
| 单机房、同 topic、生产者时钟较准 | 3s～5s |
| 多机房、跨区采集、手机端上报 | 10s～30s |
| 存在明显晚到的补数通道 | 先用侧输出，别把 out-of-orderness 拉到分钟级 |

`withIdleness` 也很关键。Kafka 某个分区长时间没数据时，如果没有 idle 标记，整条流水线的水位线会被这个「死分区」拖住，窗口一直关不上。设成 1 分钟左右通常够用；流量极不均匀的 topic 可以再调大一点。

## 乱序和迟到不是一回事

容易混：

- **乱序**：事件时间小的记录，比事件时间大的记录后到。只要还在水位线允许范围内，窗口计算时仍会算进去。
- **迟到**：水位线已经越过窗口结束时间，这条数据才到。默认会被丢弃（或进侧输出，看你怎么配）。

窗口上一般这样写：

```java
stream
  .keyBy(OrderEvent::getUserId)
  .window(TumblingEventTimeWindows.of(Time.minutes(1)))
  .allowedLateness(Time.seconds(30))
  .sideOutputLateData(lateTag)
  .aggregate(new UvAggregate())
  .getSideOutput(lateTag)
  .addSink(lateSink);
```

`allowedLateness` 让窗口在关闭后再「多活」一段时间，迟到但仍在 lateness 内的数据会触发窗口更新。代价是状态保留更久，Checkpoint 更大。

实务建议：

1. 主链路用较小的 `out-of-orderness`，保证大多数窗口准时关。
2. 对必须补齐的指标，开短 `allowedLateness`（比如 30s～2min），更新结果表（主键覆盖或 retract）。
3. 超过 lateness 的，进侧输出写到修复 topic / 旁路表，别在主作业里无限等。

## 和 Kafka 分区的关系

水位线在并行 Source 上是按分区推进，再在下游对齐的。某个 partition lag 特别大，或某台 TaskManager 卡住，会影响整条链路的水位线。

排查时优先看：

```text
# 消费是否均匀
kafka-consumer-groups.sh --bootstrap-server ... --describe --group flink-order-uv

# Flink WebUI
currentInputWatermark / currentOutputWatermark
numRecordsInPerSecond
idleTimeMsPerSecond
```

常见现象：

- **水位线不走**：某个 Kafka 分区没数据且没配 idleness；或反压导致 Source 读不动。
- **窗口结果偏少**：乱序容忍太小，大量数据被当迟到丢掉。
- **端到端延迟飙高**：乱序容忍或 allowedLateness 设太大；或 Checkpoint 间隔、状态后端 IO 拖慢。

Kafka 侧也可以配合：保证业务 key 的分区策略稳定；避免一个分区热点导致单并行度水位线拖后腿；追历史数据时用单独作业，别和生产实时作业共用同一套很大的 out-of-orderness。

## 几个生产里反复踩的坑

**1. 事件时间回拨**  
机器时钟回拨、上游重放旧数据、测试环境灌数，都会让水位线停滞甚至触发异常（取决于版本和策略）。灌数、重放用独立消费组，或临时改成处理时间验证逻辑。

**2. 窗口和 sink 语义不匹配**  
窗口在 lateness 内会多次输出，下游如果是 append-only 的 Kafka / 日志表，会出现重复行。结果表用主键 upsert（JDBC upsert、Paimon 主键表、upsert Kafka）更合适。

**3. 多流 join 的水位线**  
双流 event-time join 取决于两条流水位线的最小值。一条流空闲或延迟，另一条再快也 join 不出。空闲流务必配 `withIdleness`，并对齐两边的乱序参数。

**4. 把 Kafka `auto.offset.reset` 和 Flink 状态混着调**  
Flink 靠 checkpoint / savepoint 恢复 offset。改 starting offset 只影响「没有状态的新作业」。线上问题优先看 checkpoint 是否可用，而不是先改 `earliest/latest`。

## 一套比较稳的默认组合

新任务可以先用这套，再按延迟和完整性打磨：

```text
事件时间字段：业务毫秒时间戳
乱序容忍：5s
Source idleness：1min
窗口类型：1min 滚动
allowedLateness：30s
迟到数据：侧输出 -> 修复 topic
结果写入：主键 upsert 表
Checkpoint：30s～1min，exactly-once（按下游能力）
```

先保证「大多数数据准时进结果」，再单独处理「少数迟到数据怎么补」。不要一上来把 out-of-orderness 开到几分钟，把实时任务做成准离线。

## 小结

Flink 消费 Kafka 做事件时间计算，核心不是背概念，而是把三条线理清楚：

1. 时间戳从哪来、单位对不对。
2. 水位线愿意等多久（乱序），窗口关闭后还愿意再收多久（迟到）。
3. 迟到数据和下游写入语义怎么配合，避免重复或丢数。

参数没有标准答案，但有明确的权衡：完整性 ↑ 则延迟 ↑、状态 ↑。把这个权衡写进任务说明里，后面排查会轻松很多。

后续如果写 Paimon 主键表承接这类 upsert 结果，或 Spark Structured Streaming 里类似的 watermark 配置，可以再单独拆一篇对比。
