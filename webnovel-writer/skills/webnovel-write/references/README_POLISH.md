# ✅ 两阶段润色集成完成

## 修改总结

已成功将两个润色提示词集成到 webnovel-writer 的自动写作流程中。

## 修改的文件

### 1. 技能文件（SKILL.md）
- ⚪ `/webnovel-writer/skills/webnovel-write/SKILL.md` - **保持原有流程不变**
- ✅ `/webnovel-writer/skills/webnovel-chapter/SKILL.md` - **Step 4 已更新为两阶段润色**

### 2. 新增提示词文件
- ✅ `references/deepseek-universal-polish.yaml` (2.9 KB)
- ✅ `references/tomato-mobile-formatting.yaml` (5.3 KB)

### 3. 新增文档文件
- ✅ `references/polish-orchestrator.md` (7.3 KB)
- ✅ `references/POLISH_USAGE.md` (5.8 KB)
- ✅ `references/INTEGRATION_SUMMARY.md` (5.4 KB)

## 使用方式

### 推荐命令（最常用）

```bash
/webnovel-writer:webnovel-chapter [章节号]
```

**示例**：
```bash
# 写第 1 章
/webnovel-writer:webnovel-chapter 1

# 写第 12 章
/webnovel-writer:webnovel-chapter 12

# 自动写下一章（从 state.json 读取）
/webnovel-writer:webnovel-chapter
```

### 备用命令（不使用两阶段润色）

```bash
/webnovel-writer:webnovel-write [章节号]
```

**注意**：此命令使用原有的 NCS 润色流程，**不包含**两阶段润色。如需使用两阶段润色，请使用 `/webnovel-writer:webnovel-chapter`。

## 自动执行流程

当你运行上述命令时，Claude 会自动执行：

```
Step 1: 生成 NCS 上下文包
    ↓
Step 2: NCS 主写作（生成初稿）
    ↓
Step 3: 审查
    ↓
Step 4.1: DeepSeek 通用去AI润色 ⭐ 新增
    ↓
Step 4.2: 番茄版排版优化 ⭐ 新增
    ↓
Step 4.3: NCS 终检与问题修复
    ↓
Step 5: 提交（data-agent + chapter-commit）
    ↓
Step 6: Git 备份
```

## Step 4 详细说明

### Step 4.1: DeepSeek 通用去AI润色

Claude 会：
1. 读取 `deepseek-universal-polish.yaml` 提示词
2. 读取 Step 2 生成的章节正文
3. 按照提示词规则执行润色：
   - 删除 AI 填充词和模板段落
   - 格式规范（引号、省略号、破折号、数字汉字化）
   - 字典替换（278 条规则）
   - 语义重写（消除 AI 腔、增强文学质感）
4. 保存到 `.webnovel/tmp/polish_stage1.md`

### Step 4.2: 番茄版排版优化

Claude 会：
1. 读取 `tomato-mobile-formatting.yaml` 提示词
2. 读取 Step 4.1 的输出
3. 按照提示词规则执行排版：
   - 对话独立成段（前后双换行）
   - 文字墙粉碎（40 字强制换行）
   - 删除冗余描写和番茄禁忌词
   - 节奏提速（18 条动作词典）
4. 写回 `正文/第{NNNN}章-{title}.md`

### Step 4.3: NCS 终检

Claude 会：
1. 修复审查报告中的问题
2. 调用 NCS 的 authenticity pass
3. 执行 Anti-AI 终检
4. 输出 `anti_ai_force_check: pass/fail`

## 工作原理

- **SKILL.md 是给 Claude 的指令文档**
- Claude 读取 SKILL.md 后，会按照 Step 4.1、4.2、4.3 的描述自动执行
- Claude 会读取 YAML 提示词文件，理解其中的规则
- Claude 会根据规则对章节进行润色和排版
- **整个过程完全自动化，无需手动干预**

## 验证输出质量

运行命令后，检查生成的章节：

```bash
# 查看最新章节
cat 正文/第0001章-*.md

# 检查是否还有 AI 填充词
grep -E "综上所述|值得注意的是|不难发现" 正文/第0001章-*.md

# 检查引号是否统一
grep -E '「|」' 正文/第0001章-*.md

# 检查段落长度
awk 'BEGIN{RS="\n\n"} {if(length($0)>80) print NR": "length($0)" chars"}' 正文/第0001章-*.md
```

## 模式选择

### 默认模式（推荐）
```bash
/webnovel-writer:webnovel-chapter 1
```
完整执行 4.1 → 4.2 → 4.3

### Fast 模式
```bash
/webnovel-writer:webnovel-chapter 1 --fast
```
4.1 和 4.2 正常，4.3 简化

### Minimal 模式
```bash
/webnovel-writer:webnovel-chapter 1 --minimal
```
跳过 4.1 和 4.2，仅执行 4.3

## 调整配置

如需调整段落长度或其他参数，编辑：

```bash
# 调整番茄版段落长度
vim references/tomato-mobile-formatting.yaml

# 找到这一行并修改
config:
  max_chars_per_paragraph: 80  # 改为你想要的长度
```

## 故障排查

### 问题：输出仍有 AI 痕迹
**原因**：Claude 可能没有完全理解提示词规则  
**解决**：重新运行命令，或在对话中提醒 Claude 严格遵循提示词

### 问题：段落仍然过长
**原因**：番茄版规则可能没有生效  
**解决**：检查 `tomato-mobile-formatting.yaml` 是否存在，重新运行

### 问题：剧情被改变了
**原因**：这是严重错误  
**解决**：立即停止，检查 Step 4.1 和 4.2 的输出，确认提示词中的"保留原意"规则

## 更多信息

- 详细技术文档：`references/polish-orchestrator.md`
- 使用指南：`references/POLISH_USAGE.md`
- 集成总结：`references/INTEGRATION_SUMMARY.md`

---

**集成完成时间**: 2026-05-10  
**状态**: ✅ 已完成并可使用  
**测试命令**: `/webnovel-writer:webnovel-chapter`
