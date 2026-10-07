# BR：锚点不可见提示容易被理解为“评论被隐藏”

页面：https://s.shareone.vip/s/sudograph-northwind

复现截图：用户于 2026-10-07 提供。顶部显示 “2 comments are not shown in the current view”，下面却列出同样两条评论，并标记 “Lost Anchor”。

## 实际行为与问题归属

评论卡片保留在侧栏是合理的：正文定位失败后，用户仍需要阅读和处理评论。提示实际统计的是正文中无法定位/显示的**锚点**，文案却写成**评论未显示**，造成界面看起来矛盾。这部分属于 ShareOne 的提示语和状态表达问题，不应通过隐藏侧栏卡片来修复。

本地源码证据：`frontend/src/components/comments/CommentSidebar.tsx` 的 `lostAnchorComments` 来自 `lostAnchors`，用于绘制顶部摘要；`use-comment-annotations.ts` 在 `fromStore` 定位失败时将文本评论加入该集合；`comment-labels.ts` 却把集合数量描述为 “comments are not shown”。应用声明的 hidden 和 missing 也会进入同一集合，当前徽标统一显示 “Lost Anchor”。

## 建议行为

- 提示改为：“当前图中有 2 条评论的锚点不可见；评论仍保留在下方。”英文：“2 comment anchors are unavailable in this view. The comments remain below.”
- 能确定是应用视图暂时隐藏时，显示“当前视图隐藏 / Hidden in this view”；定位失败或目标删除时，显示“无法定位 / Anchor unavailable”。文本锚点定位失败时，不应推断目标已经被删除。
- 切换回原视图且定位成功后移除提示；始终允许从侧栏阅读、回复评论。

## 验收

1. 锚点暂时隐藏、目标删除、文本定位失败三种情形的提示均不声称侧栏评论已隐藏。
2. 摘要数量与当前不可定位锚点数量一致，恢复后数量减少。
3. 中英文含义一致，侧栏卡片始终保留。

说明：旧文本评论存的是 DIV 索引与文本上下文，并没有应用节点身份。此 BR 只确认提示文案问题；不把所有定位失败归因于 ShareOne。Sudograph 自身的展开操作另行修复，节点标签已有稳定 `data-node-id`，新增稳定 DOM id；应用区域评论继续使用 ShareOne anchor SDK。
