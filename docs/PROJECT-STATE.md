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

第一阶段设计：

- `docs/superpowers/specs/2026-07-28-gw2-wvw-thief-data-design.md`

## 当前里程碑

实现“完整 Build 导入与分析”：

- 游戏内 Build Template Code；
- GW2Skills 完整链接；
- MetaBattle 等受控来源；
- 全部装备、法印、符文、圣物、灌注和消耗品；
- WvW 合法性与过期审计；
- 有证据的优缺点和改进建议；
- 玩家持续提交链接并通过 PR 进入样本库。

已批准设计：

- `docs/superpowers/specs/2026-07-28-wvw-thief-build-analysis-design.md`

实施计划：

- `docs/superpowers/plans/2026-07-28-wvw-thief-build-analysis.md`

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

1. 导入候选；
2. 解析标准模型；
3. 校验当前 WvW 版本；
4. 生成分析和冲突报告；
5. 创建 Pull Request；
6. 人工审核后进入正式样本库。

## 新 Codex 任务检查清单

1. 确认仓库和当前分支；
2. 阅读本文件和最新规范/计划；
3. 检查 `git status`，保留用户已有改动；
4. 查询当前 ArenaNet Build ID 和最近补丁；
5. 实现前运行相关测试；
6. 不绕过 `validate-data` 或直接推送受保护的 `main`。

