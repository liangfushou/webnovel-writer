# story-long-write vs webnovel-chapter 对比分析

## 核心定位对比

| 维度 | story-long-write | webnovel-chapter |
|------|-----------------|------------------|
| **定位** | 从零开始写长篇（选题→大纲→写作） | 基于现有项目写章节 |
| **适用场景** | 新书开书、大纲搭建 | 已有大纲，日常写章 |
| **工作流程** | Phase 1-4（选题→设定→大纲→写作） | Step 1-6（合同→写作→审查→润色→提交） |
| **项目管理** | 手动文件管理 | 自动化状态机 + 数据库 |
| **技术栈** | 纯 Claude 对话 | Python 脚本 + NCS + 数据库 |

## 功能对比

### story-long-write 的优势

| 功能 | 说明 | webnovel-writer 是否有 |
|------|------|---------------------|
| ✅ **选题确认** | 帮助选择题材、对标分析 | ❌ 需要手动 |
| ✅ **核心设定** | 主角、世界观、核心冲突 | ✅ 有（设定集） |
| ✅ **卷级大纲** | 全书结构规划 | ✅ 有（总纲、卷纲） |
| ✅ **细纲搭建** | 每章细纲（钩子+爽点） | ✅ 有（章纲） |
| ✅ **对标分析** | 拆解对标书，学习套路 | ⚪ 部分有（CSV 参考） |
| ✅ **开篇设计** | 黄金三章法则 | ⚪ 部分有（章节合同） |
| ⚪ **正文写作** | 辅助写作，但无自动化 | ✅ **全自动化** |

### webnovel-chapter 的优势

| 功能 | 说明 | story-long-write 是否有 |
|------|------|---------------------|
| ✅ **自动化流程** | 一键生成章节（合同→写作→审查→提交） | ❌ 需要手动 |
| ✅ **NCS 集成** | Novel-Control-Station 专业写作引擎 | ❌ 无 |
| ✅ **两阶段润色** | DeepSeek 去AI + 番茄版排版 | ❌ 无（需手动调用 story-deslop） |
| ✅ **审查系统** | 自动检查设定、时间线、连续性 | ❌ 无 |
| ✅ **数据提取** | data-agent 自动提取事实 | ❌ 无 |
| ✅ **状态机管理** | state.json + projection + index.db | ❌ 无 |
| ✅ **Dashboard** | 可视化面板查看项目状态 | ❌ 无 |
| ✅ **Git 自动备份** | 每章自动提交 | ❌ 需手动 |

## 工作流程对比

### story-long-write 流程

```
Phase 1: 确认选题方向
    ↓
Phase 2: 核心设定（主角、世界观、冲突）
    ↓
Phase 3: 大纲搭建（卷纲 + 细纲）
    ↓
Phase 4: 正文写作辅助（手动写作，Claude 辅助）
```

**特点**：
- ✅ 适合新手，从零开始
- ✅ 有完整的开书指导
- ❌ 写作阶段需要手动操作
- ❌ 无自动化审查和提交

### webnovel-chapter 流程

```
准备: 刷新合同树
    ↓
Step 1: 生成 NCS 上下文包
    ↓
Step 2: NCS 主写作（自动生成初稿）
    ↓
Step 3: 审查（自动检查）
    ↓
Step 4.1: DeepSeek 通用去AI润色
    ↓
Step 4.2: 番茄版排版优化
    ↓
Step 5: 提交（data-agent + chapter-commit）
    ↓
Step 6: Git 备份
```

**特点**：
- ✅ 全自动化，一键完成
- ✅ 有专业写作引擎（NCS）
- ✅ 有两阶段润色
- ✅ 有自动审查和数据提取
- ❌ 需要已有大纲和设定
- ❌ 无开书指导

## 文件结构对比

### story-long-write

```
{书名}/
├── 设定/
│   ├── 世界观/
│   ├── 角色/
│   ├── 势力/
│   ├── 关系.md
│   └── 题材定位.md
├── 大纲/
│   ├── 大纲.md
│   ├── 卷纲_第一卷.md
│   └── 细纲_第001章.md
├── 正文/
│   └── 第001章_章名.md
├── 对标/
│   └── {对标书名}/
└── 追踪/
    ├── 伏笔.md
    └── 时间线.md
```

**特点**：简单、直观、手动管理

### webnovel-writer

```
{书名}/
├── 设定集/
│   ├── 主角卡.md
│   ├── 世界观.md
│   ├── 力量体系.md
│   ├── 角色库/
│   └── 技能物品时间线.md
├── 大纲/
│   ├── 总纲.md
│   ├── 第X卷-详细大纲.md
│   ├── 第X卷-时间线.md
│   └── 第X卷-节拍表.md
├── 正文/
│   └── 第0001章-章名.md
├── .webnovel/
│   ├── state.json
│   ├── index.db
│   ├── contracts/
│   ├── summaries/
│   ├── knowledge/
│   └── tmp/
└── .story-system/
    ├── MASTER_SETTING.json
    └── chapters/
```

**特点**：复杂、自动化、数据库驱动

## 适用场景

### story-long-write 适合

- ✅ **新手开书**：不知道怎么开始
- ✅ **选题阶段**：还在考虑写什么
- ✅ **大纲搭建**：需要从零搭建大纲
- ✅ **对标学习**：想学习热门书的套路
- ✅ **简单项目**：不需要复杂的状态管理

### webnovel-chapter 适合

- ✅ **日常写作**：已有大纲，每天写章节
- ✅ **自动化需求**：希望一键完成写作流程
- ✅ **质量要求高**：需要自动审查和润色
- ✅ **长期项目**：需要状态管理和数据追踪
- ✅ **团队协作**：需要 Dashboard 和数据库

## 互补性分析

### 可以结合使用

```
阶段 1: 开书（使用 story-long-write）
  - 选题确认
  - 核心设定
  - 大纲搭建
  ↓
阶段 2: 迁移到 webnovel-writer
  - 导入设定和大纲
  - 初始化项目
  ↓
阶段 3: 日常写作（使用 webnovel-chapter）
  - 自动化写章节
  - 自动审查和润色
  - 自动提交和备份
```

### 功能互补

| 需求 | 使用哪个 |
|------|---------|
| 我想开一本新书 | story-long-write |
| 我不知道写什么题材 | story-long-write |
| 我想学习对标书 | story-long-write |
| 我已有大纲，想快速写章节 | webnovel-chapter |
| 我需要自动去AI味 | webnovel-chapter |
| 我需要番茄平台排版 | webnovel-chapter |
| 我需要自动审查 | webnovel-chapter |
| 我需要 Dashboard 查看进度 | webnovel-chapter |

## 推荐方案

### 方案 1：保持独立（推荐）

**不集成 story-long-write**，原因：
- webnovel-writer 已经有完整的写作流程
- story-long-write 更适合开书阶段
- 两个项目定位不同，强行集成会混乱

**使用方式**：
- 开书时：在 `oh-story-claudecode` 项目中使用 `/story-long-write`
- 日常写作：在 `webnovel-writer` 项目中使用 `/webnovel-chapter`

### 方案 2：集成开书功能（可选）

**只集成 story-long-write 的 Phase 1-3**（选题、设定、大纲），创建新技能：

```bash
/webnovel-init-book
```

功能：
- Phase 1: 选题确认
- Phase 2: 核心设定
- Phase 3: 大纲搭建
- 自动转换为 webnovel-writer 格式

**优势**：
- 在一个项目中完成从开书到写作
- 自动格式转换

**劣势**：
- 需要大量适配工作
- 可能与现有 `/webnovel-writer:webnovel-init` 冲突

### 方案 3：集成对标分析（推荐）

**只集成 story-long-scan**（扫榜功能），创建新技能：

```bash
/webnovel-scan
```

功能：
- 扫描起点、番茄排行榜
- 分析热门题材和套路
- 为选题提供参考

**优势**：
- 功能独立，不冲突
- 对现有流程有帮助

## 结论

### 推荐做法

1. ✅ **保持 story-long-write 独立**：不集成到 webnovel-writer
2. ✅ **集成 story-long-scan**：创建 `/webnovel-scan` 用于市场调研
3. ✅ **集成 story-cover**：创建 `/webnovel-cover` 用于生成封面
4. ⚪ **可选：集成 story-deslop**：如果觉得现有润色不够，可以作为补充

### 使用建议

- **开书阶段**：使用 `oh-story-claudecode` 项目的 `/story-long-write`
- **日常写作**：使用 `webnovel-writer` 项目的 `/webnovel-chapter`
- **市场调研**：使用 `/webnovel-scan`（待集成）
- **生成封面**：使用 `/webnovel-cover`（待集成）

---

**你希望我：**
1. 保持现状，不集成 story-long-write
2. 集成 story-long-scan + story-cover
3. 其他方案？

请告诉我你的选择！
