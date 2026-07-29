# GW2 Build Lab 项目状态

本文件是跨 Codex 任务的持久上下文。开始新任务时先阅读本文件、`README.md`、最新设计规范和实施计划。

## 项目

- GitHub：https://github.com/lucasyork1/gw2-build-lab
- 当前范围：Guild Wars 2 美服，WvW，Thief
- 目标：建立可更新、可解释、可供社区协作的完整 Build 导入、审计、分析和生成系统

## 已完成

- 版本化 ArenaNet 公共 API 数据获取；
- WvW 盗贼技能、特性、装备、升级组件、消耗品和圣物数据；
- 中英文名称；
- WvW 修正层；
- Schema、来源、完整性和语义差异校验；
- 确定性 JSON/SQLite Release 构建；
- GitHub Actions 更新 PR、校验和 Release 工作流；
- 社区 Issue/PR 模板；
- `main` 分支保护和必需的 `validate-data` 检查。
- 游戏内 Build Template Code 的确定性离线解码；
- GW2Skills 完整编辑器链接导入；
- MetaBattle 受控最小事实导入；
- Build 完整性、WvW 合法性和版本状态审计；
- 八个能力维度的证据规则、结构化对比及 JSON/Markdown 报告；
- 七种首批 Roaming 架构的离线验收样本；
- 候选导入、报告、维护者审核和 PR 晋升的社区工作流。

第一阶段设计：

- `docs/superpowers/specs/2026-07-28-gw2-wvw-thief-data-design.md`

## 当前里程碑

“完整 Build 导入与分析”里程碑已实现并进入维护状态。统一链路为：

```text
Build Code / GW2Skills / MetaBattle
  -> canonical BuildRecord
  -> completeness, legality and version audit
  -> evidence-backed analysis
  -> deterministic JSON and Markdown
```

已批准设计：

- `docs/superpowers/specs/2026-07-28-wvw-thief-build-analysis-design.md`

实施计划：

- `docs/superpowers/plans/2026-07-28-wvw-thief-build-analysis.md`

## 当前数据集

- 发布时捕获的 ArenaNet Build ID：`204489`
- 数据抓取时间：`2026-07-29T02:05:07Z`
- 当前数据目录：`data/normalized/current`
- 分析规则：`data/analysis-rules/thief-wvw-v1.json`

每次新数据发布都必须重新读取 `/v2/build` 和相关官方补丁。这里记录的
Build ID 是本次数据集快照，不代表未来会自动保持最新。

## 操作命令

```text
gw2-wvw-data analyze --build-code "[&...]" --dataset data/normalized/current --json out/build.json --markdown out/build.md
gw2-wvw-data analyze --gw2skills-url "https://en.gw2skills.net/editor/?..." --dataset data/normalized/current --json out/build.json --markdown out/build.md
gw2-wvw-data import-source "https://metabattle.com/wiki/Build:Example" --dataset data/normalized/current --candidate-dir data/community-builds/candidates
gw2-wvw-data compare build-a.json build-b.json --json out/comparison.json --markdown out/comparison.md
gw2-wvw-data validate --dataset data/normalized/current --sources data/provenance/sources.json
```

## 约束

- ArenaNet API 和官方补丁优先；
- 第三方网站和视频是社区证据，不是自动真相；
- 不复制第三方攻略正文、图片或完整字幕；
- 不把 “Up to date” 标签直接当成项目认证；
- 缺失数据必须明确显示，不允许 AI 猜测装备；
- 自动更新只创建 PR，不直接写入受保护的 `main`；
- 所有建议必须能追溯到技能、特性、装备、补丁或规则。

## 玩家提交工作流

玩家可以在 Codex 任务中提供：

- GW2Skills 链接；
- 游戏内 Build Code；
- MetaBattle/Snow Crows/GW2Mists 页面；
- 后续支持的 YouTube 链接。

处理顺序：

1. 导入到 `data/community-builds/candidates/`；
2. 生成审计和分析到 `data/community-builds/reports/`；
3. 维护者检查来源、缺失值、冲突、合法性和补丁影响；
4. 在 Pull Request 中提出晋升；
5. 人工审核后移动到 `data/community-builds/verified/`。

自动导入和报告生成不得直接写入 verified 目录。
`publisher_claimed_current` 只表示发布者声称当前；只有完整 ArenaNet ID、
装备栏位、WvW 合法性、匹配的数据集 Build ID 和补丁检查全部通过后，才能
标记 `current_verified`。

## 当前限制

- Build Template Code 不含完整装备和 Roaming/Zerg 场景，单独输入通常是
  `unverifiable`；
- GW2Skills 装备 ID 在完成 ArenaNet ID 映射前仍是站点本地 ID；
- 社区页面自动适配器目前只有 MetaBattle；Snow Crows 和 GW2Mists 仅可作为
  人工证据链接；
- 网络导入只允许 `en.gw2skills.net`、`metabattle.com` 和
  `www.metabattle.com` 的 HTTPS HTML，并执行 URL、重定向、超时和响应体限制；
- 分析只使用项目规则中的明确证据，不输出无依据的单一总分；
- 尚不支持 YouTube 导入/自动发现、自然语言 Build 生成、PvE 或 sPvP。

## 下一里程碑边界

下一项已批准的产品边界是“网页完整 Build 编辑器和公开分析页”。开始实现前
必须单独完成设计和实施计划；本里程碑不扩展到 YouTube、自然语言生成、
Codex Skill、PvE 或 sPvP。

## 新 Codex 任务检查清单

1. 确认仓库和当前分支；
2. 阅读本文件和最新规范/计划；
3. 检查 `git status`，保留用户已有改动；
4. 查询当前 ArenaNet Build ID 和最近补丁；
5. 实现前运行相关测试；
6. 不绕过 `validate-data` 或直接推送受保护的 `main`。

