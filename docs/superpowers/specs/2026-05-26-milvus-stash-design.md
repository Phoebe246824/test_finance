# Milvus 事件暂存重构设计

## 背景

当前项目在黑名单未命中时，会将事件按人员 ID 维度暂存到 Redis List，后续在二次风险评估前按人员 ID 回捞历史事件并批量构图，相关实现位于 [blacklist/store.py](../../blacklist/store.py) 和 [main.py](../../main.py)。

现有方案的问题：

1. Redis 暂存只天然支持按人员 ID 精确回捞，不支持语义相似度回捞。
2. 当前历史事件回捞结果仅来自同人员集合，无法覆盖“非同人但语义强相关”的事件。
3. Redis List 的删除粒度是按 `person:<id>` 整桶删除，会误伤同一人员下尚未消费的其他候选事件。
4. 事件暂存和黑名单管理共用 `BlacklistStore`，职责耦合。

本次重构目标是：仅替换“事件暂存与回捞”链路，不改人员 ID 黑名单、敏感词黑名单、事件相似度黑名单的现有逻辑。

## 当前代码现状

### 事件 ID

当前代码中，事件在进入主流程前已经生成最终 UUID：

- `main.py` 的 `normalize_payload_to_event()` 在构造 `NormalizedEvent` 时直接生成 `str(uuid.uuid4())` 作为 `event_id`。
- `consumer.py` 的 `normalize_event()` 也直接使用 `str(uuid.uuid4())` 生成 `event_id`。
- `models.py` 中 `NormalizedEvent.event_id` 的注释仍写作 ULID，但实际实现是字符串 UUID。

因此本次设计中，Milvus 只保留一个 `event_id` 字段即可，直接复用当前最终 UUID，不再引入第二个业务 ID 字段。

### Redis 暂存

当前 `BlacklistStore` 同时负责两类能力：

- Redis 黑名单管理：`person_blacklist`、`keyword_blacklist`、`event_blacklist`
- Redis 事件暂存：`stash_event()`、`fetch_stashed_events()`、`remove_stashed_events()`

其中暂存逻辑的关键特征是：

- 未命中黑名单时，事件被按 `person:<ID>` 写入 Redis List。
- 回捞时仅按当前事件人员 ID 查询最近 N 条历史事件。
- 去重基于 `event_id`。
- 构图成功后按人员 ID 整桶删除对应 Redis key。

## 设计目标

1. 用 Milvus 替换 Redis 作为事件暂存主存储。
2. 暂存事件同时支持：
   - 按人员 ID 精确回捞
   - 按语义相似度回捞
3. 回捞结果为两路结果的并集，而不是交集。
4. 已成功构图的暂存事件不再参与后续回捞。
5. 仅重构事件暂存链路，保留现有 Redis 黑名单逻辑。

## 非目标

以下内容不在本次重构范围内：

1. 不迁移人员 ID 黑名单到 Milvus。
2. 不迁移敏感词黑名单到 Milvus。
3. 不迁移当前事件相似度黑名单到 Milvus。
4. 不重构主流程的分类、风险评估、Graphiti 搜索与 Dashboard 逻辑。
5. 不强制迁移历史 Redis 暂存数据到 Milvus。

## 架构方案对比

### 方案 A：单 collection 暂存所有事件（推荐）

使用单个 Milvus collection `stashed_events` 保存所有未命中黑名单的事件。

- 同人员回捞：按 `person_ids` 标量过滤
- 语义回捞：按 `embedding` 做向量检索
- 最终结果：并集 + 去重

优点：

- 结构简单，主数据只有一份
- 满足当前“统一事件暂存池”的目标
- 后续扩展时间窗、来源过滤等能力时改动最小

缺点：

- 依赖 Milvus 对 `person_ids` 过滤能力的支持

### 方案 B：事件 collection + 人员索引 collection

使用两个 collection：

- `stashed_events`：正文与 embedding
- `person_event_index`：`person_id -> event_id`

优点：

- 同人精确回捞能力更独立

缺点：

- 维护两套 Milvus 数据，复杂度更高
- 删除、过期、去重逻辑联动更复杂

### 方案 C：Milvus + 代码侧二次索引

事件进入 Milvus，人员索引由应用代码额外维护。

优点：

- 可绕开 Milvus 某些标量过滤限制

缺点：

- 和“不要手动管理额外存储”的目标不一致
- 复杂度最高

### 结论

采用方案 A。先以单 collection 完成最小闭环；若后续验证发现 `person_ids` 标量过滤在性能或表达力上不足，再演进到方案 B。

## 目标架构

### 保留部分

继续保留 Redis 中的：

- `person_blacklist`
- `keyword_blacklist`
- `event_blacklist`

### 新增部分

新增 Milvus collection：

- `stashed_events`

用于保存所有未命中黑名单、待后续回捞的事件。

### 回捞策略

当后续某个事件需要补拉历史暂存事件时：

1. 按人员 ID 精确回捞同人事件。
2. 按当前事件文本 embedding 做语义相似度回捞。
3. 取两路结果的并集。
4. 按 `event_id` 去重。
5. 将去重后的事件与当前事件一起送入批量构图。

## Milvus 数据模型

Collection 名称：`stashed_events`

最小字段集：

- `event_id`：UUID，Milvus 主键
- `person_ids`：事件中抽取出的人员 ID 列表
- `raw_content`：原始文本
- `created_at`：事件发生时间，对应 `NormalizedEvent.timestamp`
- `expire_at`：暂存过期时间
- `embedding`：写入时生成的向量
- `is_graph_built`：是否已成功构图，初始值为 `false`

说明：

- 不引入 `summary` 字段。
- 不引入 `risk_level` 字段。
- 不引入第二个业务事件 ID 字段。

## 字段来源与职责边界

### 标准化阶段已有或直接可得的字段

- `event_id`
- `raw_content`
- `created_at`

### 暂存层负责补齐的字段

- `person_ids`
- `embedding`
- `expire_at`
- `is_graph_built=false`

这次重构不要求把所有字段都前移到标准化阶段统一产出。标准化保持轻量，暂存层负责组装“可检索事件文档”。

## 生命周期与回捞规则

### 暂存写入

当事件未命中黑名单时：

1. 事件已经拥有最终 UUID `event_id`
2. 提取 `person_ids`
3. 生成 `embedding`
4. 写入 Milvus，初始化：
   - `is_graph_built = false`
   - `expire_at = created_at + TTL`

即使 `person_ids` 为空，也允许写入，因为这类事件仍可通过语义检索被回捞。

### 回捞前提条件

所有回捞查询都带以下过滤条件：

- `is_graph_built = false`
- `expire_at > now`
- `event_id != 当前事件 event_id`

### 回捞方式

两路独立召回：

1. 人员 ID 精确召回：命中任一 `person_ids`
2. 语义相似度召回：对当前事件生成或复用 embedding，在 `stashed_events` 中执行向量检索

最终结果处理：

1. 取并集
2. 按 `event_id` 去重
3. 标记来源：
   - `person_match`
   - `semantic_match`
   - `both`
4. 排序优先级：
   - `both`
   - `person_match`
   - `semantic_match`
5. 同类结果内部按时间倒序或相似度排序

按该规则，语义相似但与当前事件没有人员交集的事件，仍然会参与后续构图。

### 构图成功后的处理

批量构图成功后：

- 仅将本次实际消费的暂存事件标记为 `is_graph_built = true`
- 不按人员 ID 整桶标记
- 不因为同一人员命中而批量标记其他未消费事件

如果当前触发事件本身没有进入暂存池，则不需要对它做“已构图”标记。

### 构图失败后的处理

若批量构图部分失败或整体失败：

- 不修改这些暂存事件的 `is_graph_built`
- 让其保留在暂存池中，等待后续再次被召回

### TTL 清理

Milvus 查询侧默认只返回：

- `expire_at > now`
- `is_graph_built = false`

物理删除通过独立清理任务完成：

- 删除 `expire_at <= now` 的记录
- 可选删除 `is_graph_built = true` 且已超过保留期的记录

## 模块边界与最小重构范围

### `blacklist/store.py`

保留 `BlacklistStore`，但仅负责 Redis 黑名单管理：

- `query_person()`
- `query_keywords()`
- `query_event()`
- `append_*()` / `remove_*()` / `get_*()` 黑名单相关方法

移除或废弃其中的 Redis 暂存能力：

- `stash_event()`
- `fetch_stashed_events()`
- `remove_stashed_events()`
- `get_person_event_count()`
- `get_all_person_keys()`

新增独立暂存仓库，例如：

- `MilvusStashStore`

负责：

- `stash_event(event, id_numbers)`
- `fetch_related_events(event, id_numbers, top_k_semantic, max_per_person)`
- `mark_events_graph_built(event_ids)`

### `main.py`

保留现有黑名单判断主线，重点替换以下路径：

1. 未命中黑名单时：
   - 现状：写 Redis 暂存
   - 目标：写 Milvus 暂存

2. 命中黑名单并进入二次风险评估前：
   - 现状：从 Redis 按人员 ID 拉历史事件
   - 目标：从 Milvus 拉“同人并集语义”相关事件

3. 批量构图成功后：
   - 现状：按人员 ID 删除 Redis key
   - 目标：按 `event_id` 标记 Milvus 中的已消费事件为 `is_graph_built=true`

### `_maybe_batch_graph_stashed_events()`

该函数保留流程编排职责，但不再绑定 Redis。新职责为：

1. 从暂存仓库获取相关事件
2. 组装批量构图输入
3. 调用 `batch_add_to_graph()`
4. 成功后标记本次消费事件为已构图

## 测试策略

### 单元测试

覆盖 `MilvusStashStore`：

- 写入事件
- 按人员 ID 回捞
- 按语义相似度回捞
- 并集去重
- `is_graph_built=false` 过滤
- `expire_at` 过滤
- 标记已构图后不再返回

### 流程测试

覆盖主流程接线：

- 未命中黑名单 -> 写 Milvus，不进入 pipeline
- 命中黑名单 + 中高风险 -> 从 Milvus 回捞相关事件
- 构图成功 -> 标记已构图
- 构图失败 -> 保持未构图

### 回归测试

确保以下逻辑不受影响：

- 人员 ID 黑名单命中
- 敏感词黑名单命中
- 当前事件相似度黑名单逻辑

## 迁移策略

采用“先并存、后替换、最后清理”的迁移策略：

1. 先新增 `MilvusStashStore`，通过测试验证其能力
2. 再替换主流程中的暂存写入入口
3. 再替换历史事件回捞入口
4. 最后删除旧 Redis 暂存代码

默认不迁移历史 Redis 暂存数据到 Milvus。理由：

- Redis 暂存数据本身是临时态
- 本次重构关注新事件链路正确性
- 避免为一次性迁移脚本扩大实现范围

只有在确认现有 Redis 暂存历史必须保留时，才单独设计迁移脚本。

## 验证重点

本次重构最重要的验证点：

1. 同人召回结果是否完整
2. 语义召回结果是否稳定
3. 并集去重后是否不会重复构图
4. 标记已构图后是否真的不会再次被回捞

## 重构计划骨架

1. 定义 Milvus 暂存数据模型与配置
2. 实现 `MilvusStashStore`
3. 替换主流程暂存写入
4. 替换主流程回捞逻辑
5. 实现已构图标记与查询过滤
6. 增加 TTL 清理机制
7. 补齐单元测试与流程测试
8. 删除旧 Redis 暂存代码并更新相关注释、日志与文档
