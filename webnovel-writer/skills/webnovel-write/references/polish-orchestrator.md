---
name: polish-orchestrator
purpose: Step 4 两阶段润色编排器，协调 DeepSeek 通用润色和番茄版排版优化
---

# 润色编排器

## 概述

Step 4 采用**两阶段串联润色**策略：

```
Step 2 输出（NCS 生成的章节）
    ↓
Step 4.1: DeepSeek 通用去AI润色
    ↓
Step 4.2: 番茄版排版优化
    ↓
Step 4.3: NCS 终检与问题修复
    ↓
Step 5 提交
```

## 阶段详解

### Step 4.1: DeepSeek 通用去AI润色

**目标**：消除 AI 写作痕迹，提升文学质感

**输入**：`正文/第{NNNN}章-{title}.md`（Step 2 NCS 生成）

**执行**：
1. 读取 `deepseek-universal-polish.yaml`
2. 将整个文件内容作为 system prompt 或 user prompt 前置
3. 提供章节正文给 LLM（推荐 DeepSeek-V3）
4. LLM 自动执行：删除 → 规范 → 替换 → 重写
5. 输出润色后正文（不含任何元说明）

**输出**：`.webnovel/tmp/polish_stage1.md`（文学化底稿）

**关键规则**：
- 删除 23 条 AI 填充词
- 删除 18 种 AI 模板段落
- 格式规范（引号、省略号、破折号、数字汉字化）
- 字典替换（148 短语 + 105 词汇 + 25 口语）
- 语义重写（消除 AI 腔、增强文学质感、保留原意）

### Step 4.2: 番茄版排版优化

**目标**：适配手机竖屏阅读，短平快爽文节奏

**输入**：`.webnovel/tmp/polish_stage1.md`（第一阶段输出）

**执行**：
1. 读取 `tomato-mobile-formatting.yaml`
2. 将整个文件内容作为 system prompt 或 user prompt 前置
3. 提供第一阶段输出给 LLM
4. LLM 自动执行：对话孤立 → 文字墙粉碎 → 删除冗余 → 节奏提速 → 空白优化
5. 输出番茄平台版本（不含任何元说明）

**输出**：`正文/第{NNNN}章-{title}.md`（覆盖原文件）

**关键规则**：
- 对话独立成段（前后双换行）
- 段落最多 80 字、2 句话
- 删除番茄禁忌词（9 条拖慢节奏的词）
- 节奏提速字典（11 条，85% 概率）
- 视觉动作字典（7 条，85% 概率）

### Step 4.3: NCS 终检与问题修复

**目标**：修复审查问题，执行 Anti-AI 终检

**输入**：`正文/第{NNNN}章-{title}.md`（第二阶段输出）

**执行**：
1. 读取 Step 3 审查报告（`.webnovel/tmp/review_results.json`）
2. 修复非 blocking issue
3. 调用 Novel-Control-Station-Skill 的 `polish` / authenticity pass
4. 执行 `polish-guide.md` 的 Anti-AI 7 层规则
5. 输出 `anti_ai_force_check: pass/fail`

**输出**：`正文/第{NNNN}章-{title}.md`（最终版本）

**放行条件**：
- `anti_ai_force_check=pass`
- 所有 critical issue 已修复
- 未触碰润色红线（不改剧情、不改设定、不删伏笔）

## 实现示例

### Python 实现

```python
import json
from pathlib import Path

def polish_stage_1(chapter_file: Path, output_file: Path):
    """第一阶段：DeepSeek 通用润色"""
    # 读取提示词
    prompt_file = Path("references/deepseek-universal-polish.yaml")
    with open(prompt_file, 'r', encoding='utf-8') as f:
        system_prompt = f.read()
    
    # 读取章节
    with open(chapter_file, 'r', encoding='utf-8') as f:
        chapter_text = f.read()
    
    # 调用 LLM（示例使用 DeepSeek API）
    response = call_deepseek_api(
        system=system_prompt,
        user=chapter_text,
        model="deepseek-chat"
    )
    
    # 保存输出
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(response)
    
    print(f"✓ Stage 1 完成: {output_file}")

def polish_stage_2(input_file: Path, output_file: Path):
    """第二阶段：番茄版排版优化"""
    # 读取提示词
    prompt_file = Path("references/tomato-mobile-formatting.yaml")
    with open(prompt_file, 'r', encoding='utf-8') as f:
        system_prompt = f.read()
    
    # 读取第一阶段输出
    with open(input_file, 'r', encoding='utf-8') as f:
        stage1_text = f.read()
    
    # 调用 LLM
    response = call_deepseek_api(
        system=system_prompt,
        user=stage1_text,
        model="deepseek-chat"
    )
    
    # 保存输出
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(response)
    
    print(f"✓ Stage 2 完成: {output_file}")

def polish_stage_3(chapter_file: Path, review_file: Path):
    """第三阶段：NCS 终检"""
    # 读取审查报告
    with open(review_file, 'r', encoding='utf-8') as f:
        review_data = json.load(f)
    
    # 调用 NCS polish
    result = call_ncs_polish(
        chapter_file=chapter_file,
        review_data=review_data
    )
    
    if result['anti_ai_force_check'] == 'pass':
        print(f"✓ Stage 3 完成: anti_ai_force_check=pass")
        return True
    else:
        print(f"✗ Stage 3 失败: anti_ai_force_check=fail")
        return False

# 主流程
def run_polish_pipeline(chapter_num: int, project_root: Path):
    """执行完整的两阶段润色流程"""
    chapter_file = project_root / f"正文/第{chapter_num:04d}章-{title}.md"
    stage1_output = project_root / ".webnovel/tmp/polish_stage1.md"
    
    # Stage 1: DeepSeek 通用润色
    polish_stage_1(chapter_file, stage1_output)
    
    # Stage 2: 番茄版排版优化
    polish_stage_2(stage1_output, chapter_file)
    
    # Stage 3: NCS 终检
    review_file = project_root / ".webnovel/tmp/review_results.json"
    success = polish_stage_3(chapter_file, review_file)
    
    if not success:
        raise Exception("润色未通过终检，需要重新执行 Stage 3")
    
    return chapter_file
```

## 模式差异

### 默认模式
```
Step 4.1 (DeepSeek 通用) → Step 4.2 (番茄版) → Step 4.3 (NCS 终检)
```

### --fast 模式
```
Step 4.1 (DeepSeek 通用) → Step 4.2 (番茄版) → Step 4.3 (简化终检)
```

### --minimal 模式
```
跳过 Step 4.1 和 4.2 → Step 4.3 (仅排版和终检)
```

## 注意事项

1. **顺序不可颠倒**：必须先通用润色，再番茄排版
2. **中间文件保留**：`.webnovel/tmp/polish_stage1.md` 保留用于调试
3. **LLM 选择**：推荐使用 DeepSeek-V3 或 Claude Opus
4. **输出验证**：确保 LLM 输出不含元说明（"润色完成"等）
5. **失败重试**：如果 Stage 3 失败，只重跑 Stage 3，不回退 Stage 1-2

## 质量检查清单

- [ ] Stage 1 输出无 AI 填充词（综上所述、值得注意的是等）
- [ ] Stage 1 输出无 AI 模板段落（首先其次最后等）
- [ ] Stage 1 输出引号已统一为「」『』
- [ ] Stage 2 输出对话独立成段
- [ ] Stage 2 输出段落长度 ≤ 80 字
- [ ] Stage 2 输出无番茄禁忌词（不知不觉间等）
- [ ] Stage 3 输出 `anti_ai_force_check=pass`
- [ ] 最终输出保留原文情节和人物
- [ ] 最终输出未触碰润色红线

## 故障排查

### 问题：Stage 1 输出仍有 AI 痕迹
**解决**：检查 LLM 是否完整读取了 `deepseek-universal-polish.yaml`，确认 system prompt 正确传递

### 问题：Stage 2 输出段落仍然过长
**解决**：检查 LLM 是否理解了 `max_chars_per_paragraph: 80` 规则，可能需要在 user prompt 中强调

### 问题：Stage 3 终检失败
**解决**：查看具体失败原因，如果是 Anti-AI 规则未通过，回到 Stage 3 重新执行（不回退 Stage 1-2）

### 问题：最终输出改变了剧情
**解决**：这是严重错误，需要回退到 Step 2 输出，重新执行整个 Step 4，并在提示词中强调"保留原意，不添加情节"
