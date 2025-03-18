---
layout:     post
title:      Doris
subtitle:   varchar与bigint兼容性测试
date:       2025-03-18
author:     shichaofaan
header-img: img/post-bg-ios9-web.jpg
catalog: true
tags:
    - Doris
    - test测试
---

## 关于varchar和bigint在Doris中做为连接字段兼容性分析测试

* bigint数值范围：bigint类型可以存储的数值范围是-263到263-1，所以大小应该在下面范围之内-9,223,372,036,854,775,808到9,223,372,036,854,775,807，19位数字。bigint（x），x与显示宽度有关。

* varchar数值范围：varchar的最大长度受到行定义长度的限制。MySQL要求一个行的定义长度不能超过65,535字节。由于varchar字段的内容是单独存储在聚簇索引之外的，并且内容开头用1到2个字节表示实际长度（长度超过255时需要2个字节），因此varchar字段的最大长度会受到这一限制的影响。如果字符集是gbk（每个字符最多占2个字节），则varchar的最大长度不能超过(65,535-1-2)/2=32,766；如果字符集是utf8（每个字符最多占3个字节），则最大长度不能超过(65,535-1-2)/3=21,844）。
### 结论：可以简单理解为varchar精度远远大于bigint

***
### 1.字段不超限：
>字段类型没有超限制，left join 左表连接字段为bigint，右表连接字段为varchar，互换位置（***没问题，隐式转换正确***）

```SQL
WITH
left_table AS (  
    SELECT CAST(1 AS BIGINT) AS id_bigint,  
           "张三" AS name  
    union all
    SELECT CAST(2 AS BIGINT) AS id_bigint,  
           "李四" AS name
    union all
    SELECT CAST(3 AS BIGINT) AS id_bigint,  
           "王五" AS name
),
right_table AS (
	SELECT CAST(1 AS varchar(1000)) AS id_varchar,  
           "张三@qq.com" AS email  
    union all
    SELECT CAST(2 AS varchar(1000)) AS id_varchar,  
           "李四@123.com" AS email
    union all
    SELECT CAST(3 AS varchar(1000)) AS id_varchar,  
           "王五@eeka.com" AS email 
)
-- 第二种情况，左表varchar，右表bigint
SELECT right_table.id_varchar,  
       right_table.email,  
       left_table.name
FROM right_table  
LEFT JOIN left_table  
ON right_table.id_varchar = left_table.id_bigint;

-- 第一种情况，左表bigint，右表varchar
SELECT left_table.id_bigint,  
       left_table.name,  
       right_table.email  
FROM left_table  
LEFT JOIN right_table  
ON left_table.id_bigint = right_table.id_varchar;
```
***
### 2.大小接近极限：
>bigint字段大小接近极限，left join 左表连接字段为bigint，右表连接字段为varchar，互换位置（***无论左右表如何切换，最后结果是``全链接``***）

```SQL
WITH
left_table AS (  
    SELECT CAST(1234567891234567891 AS BIGINT) AS id_bigint,  
           "张三" AS name  
    union all
    SELECT CAST(1234567891234567892 AS BIGINT) AS id_bigint,  
           "李四" AS name
    union all
    SELECT CAST(1234567891234567893 AS BIGINT) AS id_bigint,  
           "王五" AS name
),
right_table AS (
	SELECT CAST(1234567891234567891 AS varchar(1000)) AS id_varchar,  
           "张三@qq.com" AS email  
    union all
    SELECT CAST(1234567891234567892 AS varchar(1000)) AS id_varchar,  
           "李四@123.com" AS email
    union all
    SELECT CAST(1234567891234567893 AS varchar(1000)) AS id_varchar,  
           "王五@eeka.com" AS email 
)
-- 第一种情况，左表bigint，右表varchar
SELECT left_table.id_bigint, 
	   right_table.id_varchar,
       left_table.name,  
       right_table.email  
FROM left_table  
LEFT JOIN right_table  
ON left_table.id_bigint = right_table.id_varchar;
-- 第二种情况
SELECT right_table.id_varchar, 
	   left_table.id_bigint, 
       right_table.email,  
       left_table.name
FROM right_table  
LEFT JOIN left_table  
ON right_table.id_varchar = left_table.id_bigint;
```

![SQL_Query](https://shichaofaan.github.io/img/in-post/2025-03-18/img001.png)

***
### 3.处于极限中等位置
>bigint字段大小处于极限长度的中等位置，left join 左表连接字段为bigint，右表连接字段为varchar，互换位置（***无论左右表如何切换，最后结果没问题***）

```SQL
WITH
left_table AS (  
    SELECT CAST(1234567891 AS BIGINT) AS id_bigint,  
           "张三" AS name  
    union all
    SELECT CAST(1234567892 AS BIGINT) AS id_bigint,  
           "李四" AS name
    union all
    SELECT CAST(1234567893 AS BIGINT) AS id_bigint,  
           "王五" AS name
),
right_table AS (
	SELECT CAST(1234567891 AS varchar(1000)) AS id_varchar,  
           "张三@qq.com" AS email  
    union all
    SELECT CAST(1234567892 AS varchar(1000)) AS id_varchar,  
           "李四@123.com" AS email
    union all
    SELECT CAST(1234567893 AS varchar(1000)) AS id_varchar,  
           "王五@eeka.com" AS email 
)
-- 第二种情况
SELECT right_table.id_varchar, 
	   left_table.id_bigint, 
       right_table.email,  
       left_table.name
FROM right_table  
LEFT JOIN left_table  
ON right_table.id_varchar = left_table.id_bigint;
-- 第一种情况，左表bigint，右表varchar
SELECT left_table.id_bigint, 
	   right_table.id_varchar,
       left_table.name,  
       right_table.email  
FROM left_table  
LEFT JOIN right_table  
ON left_table.id_bigint = right_table.id_varchar;
```

## 完结
本次bg是Hive调度任务中的join链接风险测试，防止数据join不上，被NULL数据填充