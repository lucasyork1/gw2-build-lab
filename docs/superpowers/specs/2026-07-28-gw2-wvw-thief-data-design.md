# GW2 WvW 盗贼 Build 数据库设计

日期：2026-07-28
状态：待用户审阅

## 1. 目标

建立一个可公开协作、可追踪版本、可持续更新的 GitHub 数据仓库，为后续的 GW2 WvW 盗贼 Build 导入、审计、改良和生成提供可信数据。

第一阶段只覆盖：

- 游戏模式：WvW
- 场景边界：先建立数据底座，不预设 1v1、1vX 或小队评分权重
- 职业：Thief，包括核心职业和当前可用精英特长
- 数据语言：以稳定 ID 为主键，保留英文及官方 API 可提供的中文名称

## 2. 非目标

第一阶段不做：

- PvE 或 sPvP 数据与推荐
- 图形化网站
- 自动修改玩家的游戏账户或角色
- 无人审核地发布补丁数据
- 复制 MetaBattle、Snow Crows、GW2Mists 的攻略全文
- 声称存在唯一、客观的“最强 Build”

## 3. 核心原则

### 3.1 来源优先级

1. ArenaNet 官方 API：实体 ID、职业、技能、Traits、Specializations、Items 和 Itemstats。
2. ArenaNet 官方补丁：WvW 模式分流、重做及即时修复。
3. GW2 Wiki：补充历史、隐藏交互和来源定位，但不直接当作无条件真相。
4. 第三方 Build 网站：只作为候选 Build 和社区经验。
5. 玩家提交：必须经过结构、版本和来源校验。

来源冲突时不静默覆盖。正式数据保留冲突记录并进入人工审核。

### 3.2 版本优先

每个可变实体至少记录：

- `game_build_id`
- `effective_patch`
- `mode`
- `fetched_at`
- `source_url`
- `source_type`
- `verification_status`

当前数据与历史快照分开保存。任何 Build 分析必须声明所用数据版本。

### 3.3 可解释

任何 WvW 修正、过期判定和推荐结论都必须能回溯到具体实体、补丁和规则，不能只输出模型主观判断。

## 4. 数据范围

### 4.1 盗贼职业数据

- Profession、核心机制与资源
- 核心及精英 Specializations
- Major/Minor Traits
- 治疗、通用、精英、职业和翻转技能
- 武器权限、武器技能链、双持技能与 Stealth Attack
- Initiative、Stealth、Shadowstep、Steal 等相关机制索引

### 4.2 装备数据

- 盗贼在 WvW 可使用的武器与护甲类型
- Level 80 Exotic/Ascended 属性组合
- Superior Runes
- Superior Sigils
- Relics
- WvW 有效 Food 与 Utility Consumables
- Sigil 共享冷却、叠加限制等可验证交互

### 4.3 WvW 修正

官方 API 无法完整表示的模式分流写入独立覆盖层。每条覆盖必须包含：

- 被修正实体的稳定 ID
- 字段路径
- WvW 当前值
- 原始值或前一版本值
- 生效补丁
- 来源 URL
- 审核状态

覆盖层不得直接改写原始快照。

## 5. 仓库结构

```text
schemas/                 JSON Schema
data/
  raw/                   官方 API 原始快照索引
  normalized/            标准化当前数据
  history/               按游戏版本保存的差异
  wvw-overrides/         WvW 专属修正
  community-builds/      经许可或玩家主动提交的 Build
  provenance/            来源、抓取和校验记录
scripts/
  fetch/                 获取官方公共 API 数据
  normalize/             标准化与跨实体关联
  validate/              Schema、引用和规则校验
  release/               生成 SQLite 和发布清单
tests/
.github/
  workflows/             定时检查、PR 校验、Release
CONTRIBUTING.md
CODE_OF_CONDUCT.md
SECURITY.md
```

Git 中以 JSON 和来源记录作为可审查的事实源。SQLite 是生成物，放入 GitHub Release，不把二进制数据库的每次变化直接提交到主分支。

## 6. 自动更新流程

1. GitHub Actions 定时执行，也允许维护者手动触发。
2. 检查 ArenaNet 当前游戏 Build ID 和已记录版本。
3. 只在版本变化或手动请求时获取相关公共 API 数据。
4. 保留原始响应摘要与请求信息。
5. 生成标准化盗贼数据。
6. 应用已审核的 WvW 覆盖。
7. 执行 Schema、引用完整性、合法组合和回归测试。
8. 生成机器可读差异报告。
9. 自动创建更新分支或 PR，不直接写入保护分支。
10. 人工确认补丁影响后合并。
11. 生成带版本号的 JSON 包、SQLite、校验和与 manifest。

网络失败、API 部分返回、Schema 突变或来源冲突都会中止发布；旧的稳定 Release 保持可用。

## 7. 第三方与玩家 Build

### 7.1 收录方式

第三方页面默认只保存：

- 来源名称和 URL
- 页面声明的更新时间
- 导入时间
- Build Template Code（在许可允许或由用户主动提交时）
- 解析后的稳定 ID 引用
- 版本审计结果

不自动复制攻略正文、图片、作者说明或评分。自动抓取前必须核对网站条款、robots 指令及许可。

### 7.2 过期判定

状态包括：

- `current_verified`
- `possibly_affected`
- `stale`
- `unverifiable`
- `invalid`

判断依据不是网页的 “Up to date” 标签，而是：

1. Build Code 能否解码。
2. 组合在当前 WvW 是否合法。
3. 收录后相关技能、Traits、装备组件是否被补丁影响。
4. 改动是否破坏原 Build 的目标和协同。
5. 是否经过指定补丁下的人工验证。

原始 Build 永不被静默覆盖。改良版作为派生记录，保留逐项差异、理由和适用版本。

## 8. 社区协作

社区可以通过 Issues 和 Pull Requests：

- 提交玩家原创 Build
- 报告过期或错误数据
- 添加补丁来源
- 提交 WvW 覆盖
- 补充实战验证
- 改进确定性评分规则

PR 模板要求填写游戏版本、模式、Build Code、来源、测试场景和利益冲突。自动检查通过不等于 Build 已获实战认可；人工验证与维护者审核分别记录。

主分支启用保护规则，至少要求数据校验工作流通过。项目使用行为准则和清晰的贡献署名。

## 9. Build 分析器的后续接口

数据层稳定后实现：

1. Build Code 解码与规范化。
2. 网页链接导入适配器。
3. 当前版本合法性检查。
4. 补丁影响图和过期报告。
5. 资源、攻防、机动、控制、解控和清症状等确定性特征计算。
6. 根据玩家目标调整权重。
7. 生成候选改良方案和逐项差异。

自然语言只负责把用户表达映射为受约束的目标字段，例如“更耐打”映射为生存、解控和清症状权重；数据查询、合法性和评分由确定性代码完成。

## 10. 合规与许可边界

ArenaNet API 的使用受其 Content Terms of Use 与 Website Terms of Use 约束。ArenaNet 用户协议还包含对把其内容输入生成式 AI 工具的限制。为降低风险：

- 抓取、解析、对比和评分使用确定性程序。
- 不把官方原文、Wiki 正文或第三方攻略全文发送给生成式模型。
- 不用第三方内容训练模型。
- 不假冒 ArenaNet 官方产品。
- 所有来源保留归属和链接。
- 公开发布前重新核对届时有效的条款；如果自然语言生成方案仍涉及不明确的许可范围，先向 ArenaNet 请求书面确认。

代码可采用 MIT License。项目原创 Schema、规则和社区注释可采用 CC BY 4.0；ArenaNet、Wiki 和第三方材料不因进入索引而改变原有权利归属。未经确认的外部原文不进入发布数据集。

## 11. 安全与隐私

基础数据全部来自无鉴权公共端点，不需要玩家 API Key。未来如支持读取玩家角色：

- API Key 只在客户端或受保护的服务端使用。
- 不写入日志、数据库、Issues 或 Build 分享链接。
- 仓库和 CI 不保存真实玩家密钥。

## 12. 测试与验收

第一阶段完成标准：

- 能从空目录重复生成盗贼 WvW 数据集。
- 所有稳定 ID 引用通过完整性检查。
- 所有记录包含来源、版本、模式和校验状态。
- WvW 覆盖不会污染原始快照。
- 相同输入生成字节稳定或语义稳定的输出。
- 模拟 API 超时、部分数据和 Schema 变化时不会发布损坏版本。
- 给定一个受补丁影响的示例 Build，能列出具体受影响组件。
- JSON Release 与 SQLite 的记录数量和关键字段一致。

## 13. 实施顺序

1. 建立本地仓库、Schema 和最小 CI。
2. 接入官方公共 API 并生成盗贼基础数据。
3. 建立 WvW 覆盖与补丁版本机制。
4. 加入验证、差异报告和 Release。
5. 增加社区贡献模板。
6. 实现 Build Code 解码与过期审计。
7. 在数据层通过验收后设计具体战斗场景评分。
8. 最后评估自然语言入口的合规实现。

GitHub 连接当前不可用，因此先在本地完成设计和实现；创建用户账户下的公开仓库、启用分支保护和 GitHub Actions，需要用户完成 GitHub 连接后执行。
