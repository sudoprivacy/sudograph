# sudograph

业务本体即代码：一份 YAML spec → compiler → 图。

对象、关系、带权限的 ops；**git 是历史**。

## 设计决策的 SSOT

**所有设计决策记录在 [Sudo Cloud 架构与设计 §7](https://s.shareone.vip/s/sudo-cloud-plan)，本仓不复述。**

那一节涵盖：harness 四要素、SSOT 硬规则、agent 作业纪律、落库权分档、三层分离、读治理、交互面、量化轴。有分歧以那一页为准；要改决策，改那一页并在节点上留评论，不要改这里。

本 README 只写**这个仓怎么用**。

## 仓库结构

```
schema/spec.schema.json   spec 的 JSON Schema —— owner 规则在这里被做成校验
examples/*.yaml           fixture
compiler/                 读 spec → 校验 → 算值 → 出视图模型
```

## spec 长什么样

见 `examples/weiwai-capitalisation.yaml`。要点：

- `types` 声明对象类型，每个属性带 `owner`（`source` / `ontology`）
- `raw` 是取数入口，写的是**一行可执行命令**，不是数据
- `hooks` 是缺口的具名登记，带解除条件与负责人
- `nodes` 里 `kind: derived` 的节点带一个 `op` 表达式
- `ops` 是写回动作，`intent` 必填

## op 表达式：受限，不是 Python

compiler 解析，**不 eval**。白名单：

- 算术 `+ - * / ( )`
- 节点与属性引用（裸标识符）
- 聚合 `sum(<类型> where <条件> -> <属性>)`、`count(<类型> where <条件>)`
- 比较 `== != < <= > >=`，布尔 `and or not`
- 字面量：数字、单引号字符串、`null`

不支持函数定义、属性访问链、导入、任意调用。需要新能力就加进白名单，**不开后门**。

## edit 记录格式

每次 op 除改属性外，追加一条结构化记录，跟着 spec 进 git：

```yaml
- at: 2026-09-23T10:00:00Z
  by: agent:scode-1
  op: 标记可资本化
  target: 委外合同/C-003
  changes:
    - { prop: 可资本化, from: 待补, to: 是 }
  intent: "OCR 后读出 IP 条款，归甲方"
  refs: [R-CONTRACT]
```

## 数据纪律

- spec 进 git；**原始材料不进**（扫描件、流水、合同 PDF 是数据不是 spec）
- 凭据一律不进 spec，也不进仓库
- 示例中的供应商已脱敏为「行业 + 业务类型」，金额量级已调整
