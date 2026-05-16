# 两阶段润色使用指南

## 快速开始

在 `/webnovel-writer:webnovel-write` 的 Step 4 中，系统会自动执行两阶段润色：

```
章节正文 → DeepSeek 通用润色 → 番茄版排版 → NCS 终检 → 最终输出
```

## 文件说明

| 文件 | 用途 | 何时使用 |
|------|------|---------|
| `deepseek-universal-polish.yaml` | 通用去AI润色 | Step 4.1（必选） |
| `tomato-mobile-formatting.yaml` | 番茄平台排版 | Step 4.2（必选） |
| `polish-orchestrator.md` | 编排器文档 | 开发参考 |
| `polish-guide.md` | 原有润色指南 | Step 4.3 NCS 终检 |

## 手动使用（调试/测试）

### 方法 1：使用 Claude Code

```bash
# 读取提示词
cat references/deepseek-universal-polish.yaml

# 然后在对话中：
# "请使用上面的提示词润色以下章节：[粘贴章节内容]"
```

### 方法 2：使用 DeepSeek API

```python
import requests

# 读取提示词
with open('references/deepseek-universal-polish.yaml', 'r', encoding='utf-8') as f:
    system_prompt = f.read()

# 读取章节
with open('正文/第0001章-标题.md', 'r', encoding='utf-8') as f:
    chapter_text = f.read()

# 调用 API
response = requests.post(
    'https://api.deepseek.com/v1/chat/completions',
    headers={'Authorization': 'Bearer YOUR_API_KEY'},
    json={
        'model': 'deepseek-chat',
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': chapter_text}
        ]
    }
)

polished_text = response.json()['choices'][0]['message']['content']
print(polished_text)
```

### 方法 3：使用 Claude API

```python
import anthropic

client = anthropic.Anthropic(api_key="YOUR_API_KEY")

# 读取提示词
with open('references/deepseek-universal-polish.yaml', 'r', encoding='utf-8') as f:
    system_prompt = f.read()

# 读取章节
with open('正文/第0001章-标题.md', 'r', encoding='utf-8') as f:
    chapter_text = f.read()

# 调用 API
message = client.messages.create(
    model="claude-opus-4",
    max_tokens=8000,
    system=system_prompt,
    messages=[
        {"role": "user", "content": chapter_text}
    ]
)

polished_text = message.content[0].text
print(polished_text)
```

## 验证输出质量

### Stage 1 检查清单（DeepSeek 通用润色）

```bash
# 检查是否还有 AI 填充词
grep -E "综上所述|值得注意的是|不难发现|总而言之" 正文/第0001章-标题.md

# 检查引号是否统一
grep -E '"|"' 正文/第0001章-标题.md  # 应该没有输出

# 检查是否有「」
grep -E '「|」' 正文/第0001章-标题.md  # 应该有输出
```

### Stage 2 检查清单（番茄版排版）

```bash
# 检查段落长度（应该大部分 ≤ 80 字）
awk 'BEGIN{RS="\n\n"} {if(length($0)>80) print NR": "length($0)" chars"}' 正文/第0001章-标题.md

# 检查对话是否独立成段
grep -B1 -A1 '「' 正文/第0001章-标题.md | head -20

# 检查是否还有番茄禁忌词
grep -E "不知不觉间|时间一分一秒地过去|经过漫长的等待" 正文/第0001章-标题.md
```

## 常见问题

### Q: 两个提示词可以单独使用吗？

A: 可以，但建议按顺序使用：
- **只用 Stage 1**：适合非番茄平台，需要文学质感但不需要极短段落
- **只用 Stage 2**：不推荐，因为 Stage 2 假设已经过 Stage 1 去AI处理
- **两个都用**：推荐，适合番茄平台发布

### Q: 可以调整番茄版的段落长度吗？

A: 可以，修改 `tomato-mobile-formatting.yaml` 中的：
```yaml
config:
  max_chars_per_paragraph: 80  # 改为你想要的长度
```

### Q: 如果 LLM 输出包含"润色完成"等元说明怎么办？

A: 这说明 LLM 没有完全遵循提示词。解决方法：
1. 确认 system prompt 正确传递
2. 在 user prompt 末尾强调："直接输出润色后正文，不要任何说明"
3. 使用更强的模型（如 Claude Opus 4 或 DeepSeek-V3）

### Q: 润色后剧情改变了怎么办？

A: 这是严重错误。检查：
1. 提示词中的"保留原意"规则是否被 LLM 理解
2. 是否使用了过于激进的模型
3. 考虑在 user prompt 中明确列出关键情节点，要求不得改动

### Q: 可以用其他 LLM 吗？

A: 可以，但效果可能不同：
- **推荐**：DeepSeek-V3、Claude Opus 4、GPT-4
- **可用**：Claude Sonnet 4、GPT-4o、Qwen-Max
- **不推荐**：小模型（< 70B）可能无法完全理解复杂规则

## 性能优化

### 批量处理

```python
from pathlib import Path
import concurrent.futures

def polish_chapter(chapter_file):
    """润色单个章节"""
    # Stage 1
    stage1_output = polish_stage_1(chapter_file)
    # Stage 2
    polish_stage_2(stage1_output, chapter_file)
    return chapter_file

# 并行处理多个章节
chapter_files = list(Path("正文").glob("第*.md"))
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    results = list(executor.map(polish_chapter, chapter_files))
```

### 成本估算

假设使用 DeepSeek API：
- 输入：2500 字章节 ≈ 1250 tokens
- 输出：2500 字章节 ≈ 1250 tokens
- 成本：约 $0.002 / 章（Stage 1 + Stage 2）

## 集成到自动化流程

在 `webnovel.py` 中添加：

```python
def run_two_stage_polish(chapter_num: int, project_root: Path):
    """执行两阶段润色"""
    chapter_file = get_chapter_file(project_root, chapter_num)
    
    # Stage 1: DeepSeek 通用润色
    logger.info(f"Stage 1: DeepSeek 通用润色 - 第{chapter_num}章")
    stage1_output = call_polish_stage_1(chapter_file)
    
    # Stage 2: 番茄版排版
    logger.info(f"Stage 2: 番茄版排版 - 第{chapter_num}章")
    call_polish_stage_2(stage1_output, chapter_file)
    
    logger.info(f"✓ 两阶段润色完成 - 第{chapter_num}章")
    return chapter_file
```

## 更多信息

- 详细实现：参见 `polish-orchestrator.md`
- 原有润色规则：参见 `polish-guide.md`
- NCS 集成：参见 `../novel-station-adapter/SKILL.md`
