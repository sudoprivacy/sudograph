# Northwind 阶段一基线

[在线示例](https://s.shareone.vip/s/sudograph-northwind-phase-one-baseline) 已发布为独立分享，
评论已关闭。[冻结的原生 HTML](2026-10-10/index.html) 是 compiler / shared renderer 的直接产物，
可下载后在本地浏览器打开。它包含公开的 Northwind 样例数据，不包含 ShareOne 审阅页的
历史评论或宿主注入代码。公开展示使用另一份分享；原审阅线程不并入 example。
ShareOne remote-url 当前最多拉取 10 MiB，本文件为 11,621,933 字节，
因此在线示例使用原文件上传，未绑定远程自动跟随。已下载回读确认与冻结文件逐字节一致，
并用匿名浏览器检查中文界面、30 个源对象、204 个字段，以及无评论入口。

[publication.json](publication.json) 记录公开示例和本次收尾验证；源数据与 renderer
版本仍以冻结目录中的 manifest 为准。

本次冻结是**阶段一内部验收基线**：结构和数据完整性已核对，业务含义仍需人参与核对。
没有因此宣布生产权限部署或当前版本完整的无上下文 agent 验收已经完成。

## 来源与覆盖范围

源仓库是 [jpwhite3/northwind-SQLite3](https://github.com/jpwhite3/northwind-SQLite3)，
固定版本为 [`4f56e7f5906dfd23b25244c5bfe8fb5da6402efd`](https://github.com/jpwhite3/northwind-SQLite3/tree/4f56e7f5906dfd23b25244c5bfe8fb5da6402efd)。
上游已提供填好数据的 `dist/northwind.db`。本 demo 直接只读使用该文件；
未在本机另做 CSV 导入或 `make populate`。本地文件已与上游该 Git blob 逐字节比较，完全相同。

数据库 SHA-256：`2f4f5c68dfcd33ba27373eae48c7a4869800c68095ee0f9f0da494f83382a877`。
上游 MIT 许可随示例保存在 [LICENSE.northwind.txt](2026-10-10/LICENSE.northwind.txt)。

| 范围 | 数量 | 含义 |
| --- | ---: | --- |
| 源表 | 13 | 包含所有业务源表，含空表 |
| 源视图 | 17 | 包含上游 SQL 定义和所有查询结果，含空视图 |
| 源字段 | 204 | 包括二进制字段 |
| 表内记录 | 625,890 | 只计源表 |
| 表和视图结果行 | 1,909,973 | 视图会再次展示底层表的数据，不能当作独立事实的总数 |
| 字段值 | 23,841,939 | 全量逐值比较，保留类型、NULL、重复行和浮点位模式 |
| 非空二进制值 | 17 | 逐字节及大小、摘要比较 |

“全覆盖”指上述固定版本 SQLite 的业务表、视图、字段及记录。
SQLite 自己的 `sqlite_sequence`、索引不各自作为业务对象画在图上；
也不表示上游仓库中的生成程序、图片说明、其他数据库实现都已经建模。
源视图原有计算属于源事实；阶段一没有再编写净销售额等业务定义。

`generation.yaml` 中保留了当时的 `raw.exclude` 说明：它们描述旧的业务类型绑定范围，
不是完整源快照的过滤条件。完整性以 `source_schema` 的源对象清单和全量审计为准，
其视图、无主键重复行和二进制字段都已包含。后续业务模型不得用这份历史说明
把完整源覆盖误说成只覆盖已绑定字段。

## 固定的内容

[baseline.json](2026-10-10/baseline.json) 固定 renderer 代码版本、源仓库版本、数据库摘要、
生成选项、文件摘要和覆盖数量；[validation.json](2026-10-10/validation.json) 记录核对方法、
结果及验收边界。`generation.yaml` 是原位置 `examples/northwind.yaml` 的配置副本，
相对 DSN 仍按原位置解析，不能直接在基线子目录运行它。

源数据提取时间是 HTML 的 `projection.generated_at`：`2026-10-08T10:29:34.263342+00:00`。
冻结时间另记在 manifest 中。数据提取后曾由更新后的共享 renderer 重生成界面；
冻结没有冒充重新扫描了一次数据库。

已有干净 agent 在 2026-10-07 独立完成了当时的投影流程。它的产物后来通过共享 renderer
获得完整源字段和记录展示。**这证明旧流程能独立完成、共享能力能复用；尚不是当前代码
从零重跑一遍的证明。** 之前 3 题盲测为 3/3，但隔离依靠指令，未使用 OS 沙箱，
也不证明业务含义正确。当前包保留这些限制，后续验收可继续补充。

字段与表的 inspector 已有真实分页记录；画布上直接预览几条完整行还未实现。
独立环境中的服务端权限验收已通过，当前公开 HTML 则是静态样例，不是按生产用户鉴权的入口。

## 检查和复现

在 sudograph 仓库根目录安装依赖后，检查所有冻结示例：

```sh
python -m tools.check_baselines
```

CI 也运行这个入口，校验锁定文件的大小和摘要、原生 bundle 的阶段与完整性契约，
以及覆盖声明。CI 不下载 Northwind；**摘要校验不能替代对源库的全量比较**。
在持有固定版本源库的机器上，可以再次运行全量比较：

```sh
python -m tools.check_baselines examples/northwind-phase-one/2026-10-10/baseline.json --source ../northwind-SQLite3/dist/northwind.db
```

这个检查器不包含 Northwind 表名或字段名规则；测试使用另一个临时数据库，
验证漏对象、错误值、缺失片段、虚报覆盖和冻结文件变更都会失败。

重新扫描同一份源数据：

1. 获取上游固定版本的 [dist/northwind.db](https://raw.githubusercontent.com/jpwhite3/northwind-SQLite3/4f56e7f5906dfd23b25244c5bfe8fb5da6402efd/dist/northwind.db)，先核对上述 SHA-256。
2. 要复现历史版本，使用 sudograph `89668f844e41ccadeab45e9b797baf41277cce58`，
   按其原有目录结构放置源库。在该 checkout 根目录运行：

   ```sh
   python -m compiler.cli examples/northwind.yaml --mode source_projection --records --app northwind.html --lang zh
   ```

3. 新的 agent 应从源库使用通用扫描入口，而不复制手写业务释义：

   ```sh
   python -m compiler.project sqlite:////absolute/path/northwind.db projection.yaml --name "Northwind 数据投影" --app projection.html --records
   ```

新扫描的时间戳会变化；当前源 ID 的命名空间来自规范化的物理数据库路径，
换机器或移动文件时需要显式处理源迁移，不能承诺 ID 或 HTML 摘要不变。
语言和显示别名也可能不同。应比较源事实、覆盖和交互质量。

若要**精确重放这份 HTML**，使用固定的 renderer，读取 HTML 内 `const BUNDLE = `
后的 JSON，调用 `compiler.app.render(bundle, language="zh")`，以 CRLF 换行写入 UTF-8 文件。
冻结时已验证这样重放会逐字节得到 `index.html`，其 SHA-256 为
`9d0e4d6d9607fe1e2207a441fcd04a29d08daf1ea18aa068cc0f9c3ba57db121`。
不应在冻结文件里手工修图；后续共享代码改进应产生一个新的基线。

阶段二另外添加经过核对的业务定义与业务视图，引用同一源对象和字段身份。
本阶段一快照保留为核对基线；试点业务问题及其呈现方式另行讨论。
