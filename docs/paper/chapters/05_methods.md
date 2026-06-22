# 5 关系图谱、向量召回与风险评分方法

## 5.1 金融事件关系图谱建模

为帮助分析员理解风险链路，系统将金融事件中的主体、客体、设备、商户和风险信号转化为关系图谱。图数据库使用 Neo4j，本地保存节点、边、标签和属性，前端展示时直接读取数据库中的名称、关系类型和属性，保证页面展示与后端图谱数据一致[6]。

金融事件关系图谱的数据模型如图 3 所示。图谱 schema 在 `graphiti/graphiti_workflow.py` 中通过 Pydantic 模型定义，并作为 Graphiti 的 `entity_types` 和 `edge_types` 传入。节点类型包括：

| 节点类型 | 含义 | 主要属性 |
|---|---|---|
| RiskEvent | 银行零售风控、反欺诈、反洗钱事件 | event_category、occurred_at、amount、currency、risk_level_hint、disposition、evidence |
| Customer | 银行客户、申请人、投诉人、转账发起人等自然人主体 | id_number、customer_role、risk_profile、usual_city、account_age_hint |
| Account | 银行账户、收款账户、新开户账户、涉诈账户或外部支付账户 | id_number、account_role、account_status、opened_duration、owner_hint |
| Merchant | 企业、商户、平台、支付通道、雇主或银行系统 | id_number、merchant_type、risk_status |
| Device | 登录或交易设备、IP、验证码、设备指纹等端侧行为载体 | device_type、device_status、login_city、auth_signal |
| RiskSignal | 可解释风险信号、规则命中、风险关键词或模型线索 | signal_type、severity、rule_id、evidence |

关系类型包括：

| 关系类型 | 含义 | 典型连接范围 | 主要属性 |
|---|---|---|---|
| TransfersFunds | 资金从客户、账户或商户流向另一资金主体 | Customer / Account / Merchant / RiskEvent -> Account / Merchant / Customer | amount、transaction_time、remark、channel、flow_type |
| UsesDevice | 客户或事件使用某设备、IP 或认证信号 | Customer / RiskEvent -> Device | device_status、login_city |
| TriggersSignal | 事件、客户、账户、商户或设备触发风险信号 | RiskEvent / Customer / Account / Merchant / Device -> RiskSignal | trigger_reason、severity |
| MatchesPattern | 事件或主体匹配历史案例、规则、相似投诉或异常模式 | RiskEvent / Customer / Merchant -> RiskSignal 或 RiskEvent | pattern_name、similarity_score |

**图 3 金融事件关系图谱数据模型**

## 5.2 图谱增量构建与交互分析

系统不是一次性构建静态图谱，而是随着事件分析持续增量更新。当前事件被标准化后，图谱构建模块抽取其中的客户、账户、商户、设备、事件和风险信号，写入 Neo4j。高风险事件触发历史回捞后，相关历史事件中的实体和关系也会补入图谱。这样，图谱可以逐渐形成围绕“客户、账户、设备、商户、事件、风险信号”的可追溯证据链。

图 4 展示了一个高风险事件触发历史回捞后的图谱构建结果。图中不仅包含当前事件抽取出的客户、账户、商户和风险信号，也包含从历史暂存事件中补入的相似事件和关联主体；`TransfersFunds`、`UsesDevice`、`TriggersSignal`、`MatchesPattern` 等边类型对应后端图谱 schema 中定义的关系，前端直接从 Neo4j 读取并渲染。前端图谱支持：

1. 拖拽、缩放、平移和全屏查看。
2. 点击节点查看标签、属性、相关边和业务摘要。
3. 点击边查看关系类型、来源节点、目标节点和关系属性。
4. 按人物搜索关系图谱。
5. 对任意节点继续扩展关联节点。

**图 4 事件详情与人物关系图谱交互示例**

## 5.3 低风险事件暂存与高风险事件回捞

在银行业务中，单个事件看起来可能是低风险，但多个事件串联后可能形成明显风险。例如，正常工资入账、普通消费或小额转账单独看风险较低，但当后续出现涉诈账户、虚拟币商户或分拆交易时，这些历史事件可能成为判断资金来源、行为模式和主体关系的重要上下文。

因此，系统采用“低风险暂存、高风险回捞”的机制，其流程如图 5 所示：

1. 未命中高危规则的事件按低风险展示。
2. 低风险事件写入 Milvus 向量暂存池[5]。
3. 暂存时根据事件摘要、主体编号和内容指纹去重，避免重复存储。
4. 高风险事件出现后，系统从 Milvus 召回相似历史事件。
5. 召回结果再通过客户编号、账户编号、关键词和语义相似度过滤。
6. 通过过滤的历史事件被补入关系图谱，并参与二次研判。

**图 5 低风险暂存与高风险回捞流程图**

## 5.4 多维风险评分

系统将风险分数定义为 0 到 1 的连续值。风险评估智能体基于结构化事件、黑名单命中、图谱上下文和历史召回结果，分别计算多个风险维度，再通过加权方式得到总分：

$$
\mathrm{risk\_score}=\sum_{i=1}^{n}\mathrm{dimension\_score}_i \times \mathrm{weight}_i
$$

其中，\(n\) 表示风险维度数量，\(\mathrm{dimension\_score}_i\) 表示第 \(i\) 个风险维度得分，\(\mathrm{weight}_i\) 表示该维度权重。

当前风险维度设计如表 4 所示：

**表 4 多维风险评分维度与权重**

| 风险维度 | 示例信号 | 权重 | 分数来源 |
|---|---|---:|---|
| 客户身份风险 | 黑名单命中、实名一致性、客户异常画像 | 0.15 | 黑名单、结构化事件、模型判断 |
| 交易行为风险 | 分拆交易、快进快出、异常交易备注 | 0.25 | 事件文本、交易行为特征、模型判断 |
| 交易对手风险 | 涉诈账户、虚拟币平台、高危商户 | 0.20 | 黑名单、图谱关系、模型判断 |
| 金额频次风险 | 短期大额、多笔小额规避阈值、资金流速异常 | 0.15 | 金额、频次、时间窗口、模型判断 |
| 设备地域风险 | 新设备、异地登录、异常 IP、验证码失败 | 0.10 | 设备、IP、地理位置、认证信号 |
| 历史上下文风险 | 相似历史事件、同账户反复出现、图谱关联 | 0.10 | Milvus 回捞、Neo4j 图谱上下文 |
| 合规信号风险 | 反洗钱、涉诈、虚拟币、贷款欺诈、监管规则命中 | 0.05 | 规则命中、合规关键词、模型判断 |

风险等级规则如下：

```text
高风险：risk_score >= 0.70
中风险：0.35 <= risk_score < 0.70
低风险：risk_score < 0.35
未命中高危规则事件：按低风险展示，并暂存为历史上下文
```

如果事件只执行一次风险评估，则后续意图识别、趋势预测和前端展示都沿用同一个 `risk_score`，避免不同模块出现分数不一致。若高风险事件触发历史回捞并完成二次风险评估，则系统记录 `second_risk_applied`，并在日志和报告中说明二次评分变化原因。
