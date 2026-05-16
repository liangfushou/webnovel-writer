# story-long-analyze vs webnovel-review 对比分析

## 核心定位对比

| 维度 | story-long-analyze | webnovel-review |
|------|-------------------|-----------------|
| **定位** | 拆解爆款小说，学习套路 | 审查自己写的章节质量 |
| **分析对象** | 别人的书（对标书） | 自己的书（本项目章节） |
| **目的** | 学习、借鉴、对标 | 质量检查、问题发现 |
| **输出** | 拆文报告、结构分析 | 审查报告、问题列表 |
| **使用时机** | 开书前、学习阶段 | 写完章节后 |

## 功能对比

### story-long-analyze 的功能

| 功能 | 说明 | webnovel-review 是否有 |
|------|------|---------------------|
| ✅ **黄金三章拆解** | 分析开篇钩子、爽点设计 | ❌ 无 |
| ✅ **整体结构分析** | 故事线、人物架构、节奏地图 | ❌ 无 |
| ✅ **爽点设计分析** | 拆解爽点密度和类型 | ❌ 无 |
| ✅ **人设架构分析** | 主角、配角、反派设计 | ❌ 无 |
| ✅ **写法技巧提取** | 一笔两用、延迟揭示等 | ❌ 无 |
| ✅ **深度拆解模式** | 逐章拆解整本书 | ❌ 无 |
| ✅ **对标学习** | 学习爆款套路 | ❌ 无 |

### webnovel-review 的功能

| 功能 | 说明 | story-long-analyze 是否有 |
|------|------|----------------------|
| ✅ **设定一致性检查** | 检查力量体系、世界观冲突 | ❌ 无 |
| ✅ **时间线检查** | 检查时间逻辑错误 | ❌ 无 |
| ✅ **连续性检查** | 检查前后章节衔接 | ❌ 无 |
| ✅ **人物OOC检查** | 检查角色行为是否符合人设 | ❌ 无 |
| ✅ **伏笔检查** | 检查伏笔是否遗漏 | ❌ 无 |
| ✅ **问题分级** | critical/high/medium/low | ❌ 无 |
| ✅ **自动落库** | 写入 index.db 和 state.json | ❌ 无 |
| ✅ **blocking 机制** | 严重问题阻断流程 | ❌ 无 |

## 使用场景对比

### story-long-analyze 适合

| 场景 | 说明 |
|------|------|
| ✅ **开书前学习** | 分析对标书，学习套路 |
| ✅ **黄金三章研究** | 学习如何写好开篇 |
| ✅ **爽点设计学习** | 学习如何设计爽点 |
| ✅ **节奏控制学习** | 学习如何控制节奏 |
| ✅ **人设架构学习** | 学习如何设计角色 |
| ✅ **写法技巧学习** | 学习具体写作技巧 |

### webnovel-review 适合

| 场景 | 说明 |
|------|------|
| ✅ **章节质量检查** | 写完章节后自动审查 |
| ✅ **设定冲突检查** | 发现设定矛盾 |
| ✅ **时间线检查** | 发现时间逻辑错误 |
| ✅ **连续性检查** | 发现前后不衔接 |
| ✅ **OOC 检查** | 发现角色行为不符 |
| ✅ **伏笔检查** | 发现伏笔遗漏 |

## 工作流程对比

### story-long-analyze 流程

```
Phase 1: 确认拆解对象
    ↓
Phase 2: 黄金三章拆解
    ↓
Phase 3: 整体结构分析
    ↓
Phase 4: 输出拆文报告
    ↓
（可选）Phase 2B: 深度拆解整本书
```

**输出**：
- 拆文报告.md
- 黄金三章分析
- 整体结构分析
- 角色/剧情/设定分析

### webnovel-review 流程

```
Step 1: 解析项目根目录
    ↓
Step 2: 确定章节号
    ↓
Step 3: 调用 reviewer（Python 脚本）
    ↓
Step 4: 生成审查报告
    ↓
Step 5: 写入 index.db 和 state.json
    ↓
Step 6: 判断是否有 blocking issue
```

**输出**：
- 审查报告.md
- review_results.json
- review_metrics.json
- 数据库记录

## 互补性分析

### 两者是互补的，不冲突

| 阶段 | 使用哪个 | 目的 |
|------|---------|------|
| **开书前** | story-long-analyze | 学习对标书，了解套路 |
| **写作中** | webnovel-review | 检查自己写的章节质量 |
| **遇到瓶颈** | story-long-analyze | 回去看对标书怎么处理 |
| **质量把关** | webnovel-review | 确保没有设定冲突 |

### 典型工作流

```
1. 开书前：用 story-long-analyze 拆解 3-5 本对标书
   ↓
2. 学习套路：提取黄金三章、爽点设计、节奏控制
   ↓
3. 开始写作：用 /webnovel-chapter 写章节
   ↓
4. 自动审查：webnovel-review 自动检查质量
   ↓
5. 遇到问题：回去用 story-long-analyze 看对标书怎么处理
   ↓
6. 继续写作：循环 3-5
```

## 是否需要集成？

### 方案 1：不集成（推荐）

**理由**：
- ✅ 两者定位完全不同（学习 vs 检查）
- ✅ 使用时机不同（开书前 vs 写作中）
- ✅ 分析对象不同（别人的书 vs 自己的书）
- ✅ 保持独立更清晰

**使用方式**：
- 学习阶段：在 `oh-story-claudecode` 项目中使用 `/story-long-analyze`
- 写作阶段：在 `webnovel-writer` 项目中使用 `/webnovel-chapter`（自动调用 webnovel-review）

### 方案 2：创建快捷命令（可选）

如果你经常需要在 webnovel-writer 项目中分析对标书，可以创建一个快捷命令：

```bash
/webnovel-analyze
```

功能：
- 调用 story-long-analyze 的核心功能
- 输出到 `对标/` 目录
- 与现有项目结构兼容

**优势**：
- 在一个项目中完成学习和写作
- 对标分析结果自动保存到项目中

**劣势**：
- 需要适配工作
- 可能与现有功能重复

## 推荐方案

### ✅ 保持独立（推荐）

**不集成 story-long-analyze**，原因：
1. 两者定位完全不同
2. webnovel-review 已经足够强大
3. story-long-analyze 更适合学习阶段
4. 保持独立更清晰

**使用建议**：
- **开书前**：在 `oh-story-claudecode` 项目中使用 `/story-long-analyze` 拆解对标书
- **写作中**：在 `webnovel-writer` 项目中使用 `/webnovel-chapter`（自动调用 webnovel-review）
- **遇到瓶颈**：回到 `oh-story-claudecode` 项目，用 `/story-long-analyze` 再看对标书

### ⚪ 可选：集成对标分析

如果你希望在 webnovel-writer 项目中也能分析对标书，可以创建：

```bash
/webnovel-analyze
```

但这不是必需的，因为：
- story-long-analyze 在另一个项目中已经很好用
- 两个项目切换也很方便
- 强行集成可能导致功能混乱

## 结论

### 推荐做法

1. ✅ **保持 story-long-analyze 独立**：不集成到 webnovel-writer
2. ✅ **webnovel-review 保持现状**：已经集成在 `/webnovel-chapter` 的 Step 3 中
3. ⚪ **可选：创建快捷命令**：如果你经常需要在 webnovel-writer 中分析对标书

### 当前状态

| 项目 | 技能 | 用途 |
|------|------|------|
| oh-story-claudecode | `/story-long-analyze` | 拆解对标书，学习套路 |
| webnovel-writer | `/webnovel-chapter` | 写章节（自动调用 webnovel-review） |
| webnovel-writer | `/webnovel-deslop` | 单独去AI味 |

---

**你希望我：**
1. 保持现状，不集成 story-long-analyze
2. 创建 `/webnovel-analyze` 快捷命令
3. 其他方案？

请告诉我你的选择！
