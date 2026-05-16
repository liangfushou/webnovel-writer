---
name: webnovel-two-stage-polish
description: 两阶段润色：DeepSeek 通用去AI + 番茄版排版。严格执行 YAML 规则，消除 AI 痕迹，适配手机阅读。
allowed-tools: Read Write Edit Bash
---

# 两阶段润色技能

**核心功能**：严格按照 YAML 规则执行两阶段润色，确保生成的正文自然流畅且适配番茄平台。

## 用法

```bash
# 方式 1：润色指定文件
/webnovel-two-stage-polish 正文/第0001章-标题.md

# 方式 2：润色指定章节号（自动查找文件）
/webnovel-two-stage-polish 1

# 方式 3：润色最新章节
/webnovel-two-stage-polish
```

**中文说明**：
- 输入：章节文件路径或章节号
- 输出：经过两阶段润色的正文（覆盖原文件）
- 流程：Stage 1 (DeepSeek 去AI) → Stage 2 (番茄排版)

---

## 执行流程

### 准备：定位文件

```bash
# 如果用户提供文件路径，直接使用
# 如果用户提供章节号，查找对应文件
# 如果用户未提供参数，查找最新章节

export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SCRIPTS_DIR="${WORKSPACE_ROOT}/webnovel-writer/scripts"

# 预检
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" preflight
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"

# 确定章节文件
if [ -f "${USER_INPUT}" ]; then
  CHAPTER_FILE="${USER_INPUT}"
elif [[ "${USER_INPUT}" =~ ^[0-9]+$ ]]; then
  CHAPTER_NUM="${USER_INPUT}"
  CHAPTER_FILE=$(find "${PROJECT_ROOT}/正文" -name "第$(printf '%04d' ${CHAPTER_NUM})章-*.md" | head -1)
else
  # 查找最新章节
  CHAPTER_FILE=$(ls -t "${PROJECT_ROOT}/正文"/第*章-*.md 2>/dev/null | head -1)
fi

if [ ! -f "${CHAPTER_FILE}" ]; then
  echo "错误：找不到章节文件"
  exit 1
fi

echo "📄 目标文件: ${CHAPTER_FILE}"
```

---

### Stage 1：DeepSeek 通用去AI润色

**目标**：消除 AI 写作痕迹，提升文学质感

**YAML 规则文件**：`webnovel-writer/skills/webnovel-write/references/deepseek-universal-polish.yaml`

**执行步骤**：

1. **读取原文**
   ```bash
   ORIGINAL_TEXT=$(cat "${CHAPTER_FILE}")
   ```

2. **读取 YAML 规则**
   ```bash
   YAML_STAGE1="webnovel-writer/skills/webnovel-write/references/deepseek-universal-polish.yaml"
   ```

3. **构建 DeepSeek 提示词**
   
   System Prompt:
   ```
   你是一位专业的中文小说编辑，擅长将 AI 生成的文本润色为自然、流畅、富有文学质感的人类写作风格。
   
   你的任务：对用户提供的中文小说文本执行人性化润色，消除 AI 写作痕迹，保留原意，提升可读性与真实感。
   
   执行顺序：
   1. 删除：移除所有 AI 填充词、模板段落、元说明
   2. 规范：执行标点、数字汉字化规范
   3. 替换：按字典执行短语和词汇替换（长key优先，随机候选，排除黑名单）
   4. 重写：执行语义层润色（消除AI腔、增强文学质感、保留原意）
   5. 输出：直接给出润色后正文，无需任何附加说明
   
   核心规则：
   - 删除 23 条 AI 填充词（综上所述、值得注意的是等）
   - 删除 18 种 AI 模板段落（首先其次最后、一方面另一方面等）
   - 删除 8 种元说明（我将按照您的、故事梗概等）
   - 引号统一为「」『』
   - 省略号统一为……
   - 破折号统一为——
   - 数字汉字化（年份、年代、月份、日期）
   - 148 条 AI 套话短语替换（85% 概率）
   - 105 条通用词汇替换（50% 概率）
   - 消除 AI 腔：被动改主动、打散模板、去过度连接、落地具体细节
   - 增强文学质感：感官细节、角色个性对话、情绪融入景物、节奏变化
   - 保留原意：不添加情节、不改因果、保持专有名词
   
   重要：
   - 直接输出润色后的正文，不附任何说明、解释或前言
   - 不输出'润色完成''以下是润色结果'等元说明
   - 段落数量与原文保持一致，不增删段落
   - 保留原文的章节标题格式
   ```

   User Prompt:
   ```
   请对以下章节正文执行 DeepSeek 通用去AI润色：
   
   {ORIGINAL_TEXT}
   ```

4. **执行润色**
   
   使用 Claude 自己执行润色（因为我们在 Claude Code 环境中）：
   - 读取 YAML 规则
   - 按照规则处理文本
   - 输出润色后的文本

5. **保存 Stage 1 结果**
   ```bash
   # 保存到临时文件
   echo "${STAGE1_OUTPUT}" > "${PROJECT_ROOT}/.webnovel/tmp/polish_stage1.md"
   ```

---

### Stage 2：番茄版排版优化

**目标**：适配手机竖屏阅读，短平快爽文节奏

**YAML 规则文件**：`webnovel-writer/skills/webnovel-write/references/tomato-mobile-formatting.yaml`

**执行步骤**：

1. **读取 Stage 1 输出**
   ```bash
   STAGE1_TEXT=$(cat "${PROJECT_ROOT}/.webnovel/tmp/polish_stage1.md")
   ```

2. **读取 YAML 规则**
   ```bash
   YAML_STAGE2="webnovel-writer/skills/webnovel-write/references/tomato-mobile-formatting.yaml"
   ```

3. **构建番茄排版提示词**
   
   System Prompt:
   ```
   你现在是番茄小说平台的白金作家兼主编。你的核心任务是将文本改编成适配手机竖屏的『爽文排版』。
   
   【极简短段】
   - 任何人的一句话必须独占一段！
   - 任何环境描写不能超过两句话！
   - 如果超过，必须强制按回车换行！
   
   【情绪外放】
   - 把主角内心的纠结、沉思，全部转化为外在的动作（如：冷笑、皱眉、握拳、叹息）
   
   【砍掉树枝】
   - 直接删掉没用的风景描写、衣服首饰描写、路人甲的背景介绍
   - 剧情必须像火箭一样往前推！
   
   执行规则：
   1. 对话孤立：任何对话前后必须有双换行
   2. 文字墙粉碎：连续 40 字无换行且遇句号，强制换行
   3. 删除冗余描写：设定铺陈、环境描写极限压缩
   4. 删除番茄禁忌词：不知不觉间、经过漫长的等待等
   5. 节奏提速替换（85% 概率）：
      - "他想了想" → "他眼珠一转"
      - "慢慢地走过去" → "大步上前"
      - "看了很久" → "目光一扫"
      - "非常生气" → "怒火中烧"
      - "拿" → "一把抓过"
      - "跑" → "狂奔"
   6. 空白优化：收敛过多空行为标准双换行
   7. 章末留白：章末增加额外空行
   
   【输出要求】
   - 直接输出改编后的正文，不附任何说明
   - 段落极短，对话独立，节奏飞快
   - 保留原文的情节和人物，只改排版和节奏
   ```

   User Prompt:
   ```
   请对以下文本执行番茄版排版优化：
   
   {STAGE1_TEXT}
   ```

4. **执行排版优化**
   
   使用 Claude 自己执行排版优化：
   - 读取 YAML 规则
   - 按照规则处理文本
   - 输出排版后的文本

5. **保存 Stage 2 结果**
   ```bash
   # 保存到临时文件
   echo "${STAGE2_OUTPUT}" > "${PROJECT_ROOT}/.webnovel/tmp/polish_stage2.md"
   ```

---

### 最终：写回正文

```bash
# 备份原文件
cp "${CHAPTER_FILE}" "${CHAPTER_FILE}.backup"

# 写回润色后的正文
echo "${STAGE2_OUTPUT}" > "${CHAPTER_FILE}"

echo "✅ 两阶段润色完成！"
echo "📄 原文备份: ${CHAPTER_FILE}.backup"
echo "📄 润色结果: ${CHAPTER_FILE}"
```

---

## 严格执行规则

### 禁止事项

1. **禁止跳过任何步骤**
   - 必须完整执行 Stage 1 和 Stage 2
   - 不得合并两个阶段
   - 不得简化规则

2. **禁止伪造结果**
   - 必须真实读取 YAML 文件
   - 必须真实执行所有规则
   - 不得假装执行

3. **禁止修改原意**
   - 只改表达，不改剧情
   - 保留原文的情节和人物
   - 不添加新情节

### 必须事项

1. **必须读取 YAML 规则**
   - Stage 1: `deepseek-universal-polish.yaml`
   - Stage 2: `tomato-mobile-formatting.yaml`

2. **必须按顺序执行**
   - 先 Stage 1（去AI）
   - 后 Stage 2（排版）
   - 不得颠倒顺序

3. **必须保存中间结果**
   - Stage 1 输出保存到 `.webnovel/tmp/polish_stage1.md`
   - Stage 2 输出保存到 `.webnovel/tmp/polish_stage2.md`
   - 原文备份到 `{原文件}.backup`

---

## 输出报告

执行完成后，输出以下报告：

```
## 两阶段润色报告

### 文件信息
- 原文件: {CHAPTER_FILE}
- 原文备份: {CHAPTER_FILE}.backup
- Stage 1 输出: .webnovel/tmp/polish_stage1.md
- Stage 2 输出: .webnovel/tmp/polish_stage2.md

### Stage 1: DeepSeek 通用去AI
- 执行状态: ✅ 完成
- 规则文件: deepseek-universal-polish.yaml
- 主要修改:
  - AI 填充词删除: {N} 处
  - AI 模板段落删除: {N} 处
  - 格式规范: {N} 处
  - 字典替换: {N} 处
  - 语义重写: {N} 处

### Stage 2: 番茄版排版
- 执行状态: ✅ 完成
- 规则文件: tomato-mobile-formatting.yaml
- 主要修改:
  - 对话孤立: {N} 处
  - 文字墙切分: {N} 处
  - 冗余描写删除: {N} 处
  - 禁忌词删除: {N} 处
  - 节奏提速替换: {N} 处

### 最终结果
✅ 两阶段润色完成！正文已更新。
```

---

## 与其他 skill 的集成

### 在 /webnovel-chapter 中使用

在 `/webnovel-chapter` 的 Step 4 中，调用本 skill：

```bash
# Step 4.1 + 4.2：两阶段润色
/webnovel-two-stage-polish "${CHAPTER_FILE}"
```

这样可以确保：
- 严格执行 YAML 规则
- 不跳过任何步骤
- 保存中间结果
- 生成完整报告

---

## 推荐用法

```bash
# 场景 1：润色刚写好的章节
/webnovel-two-stage-polish 正文/第0001章-标题.md

# 场景 2：润色指定章节号
/webnovel-two-stage-polish 1

# 场景 3：润色最新章节
/webnovel-two-stage-polish

# 场景 4：在写章流程中自动调用
/webnovel-chapter 1  # 内部会调用本 skill
```

---

**预期时间**：约 2-3 分钟/章（取决于章节长度）

**注意事项**：
- 会覆盖原文件（但会自动备份）
- 必须严格按照 YAML 规则执行
- 不修改剧情，只改表达和排版
