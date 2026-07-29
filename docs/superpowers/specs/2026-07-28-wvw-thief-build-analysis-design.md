# GW2 WvW 盗贼完整 Build 导入与分析设计

日期：2026-07-28  
状态：用户已批准

## 1. 目标

在现有 WvW 盗贼版本化数据基础上，增加一个确定性优先、来源可追溯的完整 Build 导入与分析层。

第一版必须能够：

- 解码游戏内 Build Template Code；
- 解析 GW2Skills 完整编辑器链接；
- 从受支持的社区 Build 页面提取最小必要事实；
- 表示完整的技能、特性、武器和装备配置；
- 判断当前 WvW 版本中的合法性、完整性和过期风险；
- 输出有证据的优点、缺点、适用场景和逐项改进建议；
- 允许玩家持续提交新的 GW2Skills 链接，并通过 Pull Request 审核后进入正式样本库。

第一版只覆盖 WvW 盗贼。自动发现 YouTube 视频、自然语言生成 Build、PvE 和 sPvP 属于后续里程碑。

## 2. 产品形态

GitHub 仓库是数据、规则和分析引擎的事实源，不是最终用户界面的唯一形态。

```text
版本化 GW2 数据
        ↓
完整 Build 标准模型
        ↓
导入、审计和分析引擎
        ↓
命令行 / 未来网页 API / 未来 Codex Skill
```

所有入口必须调用同一套确定性解析和分析代码。Codex Skill 只负责自然语言交互，不另建一套事实数据库。

## 3. 输入格式

### 3.1 游戏内 Build Template Code

输入示例：

```text
[&DQU2KywnBzkKAQAAGQEAAFgAAABXAQAAnwEAAAAAAAAAAAAAAAAAAAAAAAAEBQA2AFoALwAA]
```

解码内容包括职业、三条专精、主要特性、治疗/通用/精英技能、职业专属字段，以及代码中存在的武器和技能变体信息。

Build Template Code 不包含完整装备模板。仅提供此输入时，分析器必须把装备栏位标记为缺失，不能根据常见搭配自动补全。

### 3.2 GW2Skills 完整链接

GW2Skills 链接是第一版推荐输入，用于携带：

- 职业、技能、专精和特性；
- 两套陆地武器；
- 护甲、武器和饰品属性；
- 武器法印；
- 护甲符文；
- 圣物；
- 灌注；
- 食物、通用消耗品和用户选择的计算条件。

GW2Skills 仅作为配置载体和可视化参考。导入器不得信任网站计算出的当前技能数值或最终属性；所有可重算结果必须使用 GW2 Build Lab 当前数据集重新计算。

### 3.3 社区页面链接

第一版支持 MetaBattle 页面适配器，并为 Snow Crows 和 GW2Mists 保留受控适配器接口。

适配器只提取最小必要事实：

- 来源名称和 URL；
- 页面标题、模式、角色和发布日期；
- 页面声称适用的补丁；
- Build Template Code 或完整编辑器链接；
- 页面明确列出的装备配置；
- 发布者评级及其原始标签。

不得复制攻略正文、图片、完整轮转说明或评论。发布者的观点不成为本项目的确定性事实。

### 3.4 项目标准 JSON

网页、CLI、未来 Skill 和社区提交最终都转换为同一个版本化 JSON 模型。

## 4. 完整 Build 模型

顶层记录至少包含：

```json
{
  "schema_version": 1,
  "build_id": "stable-project-id",
  "profession": "Thief",
  "mode": "wvw",
  "context": ["roaming"],
  "specializations": [],
  "traits": [],
  "skills": {},
  "weapons": [],
  "armor": {},
  "trinkets": {},
  "runes": [],
  "relic": null,
  "infusions": [],
  "consumables": {
    "food": null,
    "utility": null
  },
  "assumptions": {},
  "provenance": {},
  "version_audit": {}
}
```

### 4.1 装备完整性

模型必须分别表示：

- 六件护甲；
- 背部、项链、两件饰品和两枚戒指；
- 两套陆地武器及主副手位置；
- 每件武器的属性和法印；
- 六个符文位置；
- 一个圣物；
- 每个灌注位置；
- 食物和通用消耗品。

每个栏位都保存稳定 ArenaNet ID、名称快照、属性前缀、来源和提取置信度。缺失栏位使用显式 `null` 或缺失记录，不用近似值替代。

### 4.2 字段级来源

来源不是只挂在 Build 顶层。导入器必须能够说明某一字段来自：

- 游戏内 Build Code；
- GW2Skills 链接；
- MetaBattle 页面声明；
- 玩家手工补充；
- 项目维护者的审核修正。

冲突字段分别保留，不静默覆盖。

## 5. 版本和可信度状态

Build 审计状态包括：

- `current_verified`：全部关键组件通过当前 WvW 数据验证；
- `publisher_claimed_current`：来源网站声称最新，但项目尚未完全验证；
- `possibly_affected`：收录后有补丁改动过相关组件；
- `stale`：关键机制或配置已经失效；
- `invalid`：当前版本不能合法使用；
- `unverifiable`：缺少必要信息或出现未知 ID。

页面上的 “Up to date” 只能生成 `publisher_claimed_current`。只有本项目完成当前游戏版本的组件合法性、模式分流和补丁影响检查后，才能生成 `current_verified`。

## 6. 导入和审核流程

```text
玩家提交 GW2Skills / Build Code / 社区页面链接
        ↓
候选导入：保留原始链接和抓取元数据
        ↓
解析为标准 JSON
        ↓
Schema、ID、WvW 合法性和版本校验
        ↓
生成来源冲突与补丁影响报告
        ↓
创建或更新 Pull Request
        ↓
人工审核后进入正式样本库
```

候选数据和正式样本分开保存：

```text
data/community-builds/candidates/
data/community-builds/verified/
data/community-builds/reports/
```

自动导入不得直接写入受保护的 `main`。同一规范化 Build 的重复提交合并为多个来源记录，不复制实体。

## 7. 首批种子样本

首批 Roaming 样本覆盖七种差异明显的架构：

1. Daredevil Power S/D；
2. Daredevil Celestial Shadow Arts Axe/Pistol；
3. Daredevil Power Scepter；
4. Daredevil Shadow Arts Dagger/Pistol；
5. Deadeye Shadow Arts Rifle；
6. Specter Celestial Scepter；
7. Core Pistol/Dagger Condition。

Snow Crows Support Specter 只作为 WvW Zerg 对照样本，不进入 Roaming 排名。无法稳定提取或无法确认版本的 GW2Mists 页面登记为来源候选并标记 `unverifiable`，不得为了凑数量导入。

## 8. 分析模型

### 8.1 确定性检查

- Build Code 格式和职业；
- 专精、特性、技能与武器组合合法性；
- WvW 模式可用性和模式分流；
- 装备栏位完整性；
- 属性、法印、符文、圣物和消耗品引用；
- 已删除、未知或被替换的组件；
- 收录版本以后相关组件的补丁变化。

### 8.2 能力维度

每项使用五档等级并输出证据和置信度，不使用缺乏依据的单一总分：

- 爆发伤害；
- 持续输出；
- 生存与恢复；
- 条件清除；
- 控制与打断；
- 机动与脱战；
- 隐身与重置；
- 操作难度。

装备不完整时，只降低受影响维度的置信度，不把未知装备假定为默认装备。

### 8.3 优缺点和改进建议

每条结论必须引用具体技能、特性、装备或规则。改进建议作为派生方案保存，必须列出逐项差异和取舍，例如：

```text
更换特性 A → B
收益：增加条件清除
代价：失去一个爆发增益
适用：面对高症状压力的小规模对局
```

原始 Build 永远保留，不被改进方案覆盖。

## 9. 输出

第一版提供：

```powershell
gw2-build-lab analyze --build-code "<code>"
gw2-build-lab analyze --gw2skills-url "<url>"
gw2-build-lab import-source "<url>"
gw2-build-lab compare build-a.json build-b.json
```

每次分析同时输出：

- 机器可读 JSON；
- 玩家可读 Markdown。

报告包含 Build 身份、完整度、版本状态、合法性、全部装备、能力分析、优点、缺点、对局风险、改进方案、证据和来源。

## 10. 失败处理

- 网站结构变化：该适配器失败并报警，不覆盖现有样本；
- 来源数据版本落后：保留配置并使用本地数据重算；
- 装备不完整：生成部分报告并列出缺失栏位；
- 未知 ID：标记 `unverifiable`；
- 非盗贼或非 WvW：第一版明确拒绝；
- 冲突来源：生成冲突记录并等待人工审核；
- 超长、畸形或恶意输入：限制长度、拒绝非法编码且不写入文件；
- 网络失败：不改变正式样本库。

## 11. 模块边界

在现有 Python 项目中新增聚焦模块：

```text
src/gw2_wvw_data/builds/       标准 Build 模型和 Schema
src/gw2_wvw_data/decoders/     游戏 Build Code 解码
src/gw2_wvw_data/importers/    GW2Skills 和社区页面适配器
src/gw2_wvw_data/audit/        合法性、版本和完整性审计
src/gw2_wvw_data/analysis/     能力维度、证据和改进差异
```

导入器只负责产生标准模型；审计器不访问网页；分析器只消费已审计的标准模型和版本化游戏数据。网站变化不应影响核心分析代码。

## 12. 测试和验收

第一版完成标准：

- 正确解析首批七个盗贼 Roaming 样本；
- Build Template Code 解码结果可重复；
- GW2Skills 链接能还原完整装备栏位；
- 每个技能、装备和结论都有来源或计算依据；
- 不把来源网站的最新标签当成本项目认证；
- 已删除、未知和不合法组合有明确错误；
- 相同输入生成相同 JSON；
- 网站结构变化不会污染已有数据；
- 测试覆盖正常、残缺、过期、冲突和恶意输入；
- 现有数据流水线及其测试继续通过。

## 13. 后续里程碑

在本设计验收后再分别设计：

1. 网页完整 Build 编辑器和公开分析页面；
2. YouTube 单链接导入；
3. 最近 7/30 天 YouTube 自动发现和质量筛选；
4. 自然语言目标到候选 Build 的受约束生成；
5. Codex Skill；
6. PvE 和 sPvP 扩展。

