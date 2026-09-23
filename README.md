# sudograph

业务本体即代码：一份 YAML spec → compiler → 图。

对象、关系、带权限的 ops；**git 是历史**。

## 三条不让步的规则

1. **图 = 代码 = 数据 = 校验，同源。** 不存在"另一个核对脚本"——校验就是跑同一份 spec。
2. **每个属性声明 owner。** `source`（上游事实，归 connector）/ `ontology`（这里做的决定，归 ops）。不存在两者都是；ops 只许写 `owner=ontology`。
3. **值不进 spec。** spec 里只有 connector 命令，数字在渲染时才取；取数时刻与校验属于渲染产物。

## 三层

| 层 | 谁写 | 产出 |
|---|---|---|
| 描述 spec | agent | 节点 · 依赖 · op · connector 命令 |
| 编译 compiler | 代码 | 值 · 校验结果 · 视图模型（折叠 / 分组 / top-N） |
| 渲染 renderer | 库 | 图应用（交互）· mermaid（静态回落） |

折叠与分组归 compiler，**不得进 spec**——否则排版需求会污染"图 = 代码"。

## op 表达式：受限，不是 Python

compiler 解析，**不 eval**。支持：

- 算术 `+ - * / ( )`
- 节点与属性引用（裸标识符）
- 聚合 `sum(<类型> where <条件> -> <属性>)`、`count(<类型> where <条件>)`
- 比较 `== != < <= > >=`，布尔 `and or not`
- 字面量：数字、单引号字符串、`null`

不支持：函数定义、属性访问链、导入、任意调用。需要新能力就加进 compiler 的白名单，**不开后门**。

## 落库权按可逆性分档

| class | 判据 | 谁能落 |
|---|---|---|
| `DerivedOp` | 可逆 · 重算即恢复 | agent 直接落 |
| `RecordableOp` | 不可逆 · 金额由 infra 派生 | agent 生成，人按按钮 |
| `BlockedOp` | 当前材料下不构成合法写入 | 谁都不能落，先补材料 |

所有 op 的 `intent` **必填**，且须指向具体的 raw 或 hook，不是自由文本。

## edit 记录

每次 op 除改属性外，追加一条结构化记录，**跟着 spec 进 git**：

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

历史**按对象聚合渲染**（点节点看它自己的时间线），不是全局 commit 列表。

## 数据纪律

- spec 进 git；**原始材料不进**（扫描件、流水、合同 PDF 是数据不是 spec）
- 凭据一律不进 spec，也不进仓库
- 示例中的供应商已脱敏为「行业 + 业务类型」，金额量级已调整

## 设计出处

决策记录在 [Sudo Cloud 架构与设计 §7](https://s.shareone.vip/s/sudo-cloud-plan)。
