# 两阶段润色集成总结

## 修改概览

本次集成为 webnovel-writer 的 Step 4 添加了两阶段润色流程，用于消除 AI 写作痕迹并优化手机阅读体验。

## 新增文件

### 1. deepseek-universal-polish.yaml
- **路径**: `references/deepseek-universal-polish.yaml`
- **大小**: 2.9 KB
- **用途**: DeepSeek 中文小说通用去AI润色提示词
- **功能**:
  - 删除 23 条 AI 填充词
  - 删除 18 种 AI 模板段落
  - 格式规范（引号、省略号、破折号、数字汉字化）
  - 字典替换（148 短语 + 105 词汇 + 25 口语）
  - LLM 语义重写（消除 AI 腔、增强文学质感）

### 2. tomato-mobile-formatting.yaml
- **路径**: `references/tomato-mobile-formatting.yaml`
- **大小**: 5.3 KB
- **用途**: 番茄小说平台专属排版优化提示词
- **功能**:
  - 对话孤立（前后双换行）
  - 文字墙粉碎（40 字强制换行）
  - 删除冗余描写和番茄禁忌词
  - 节奏提速字典（11 条）
  - 视觉动作字典（7 条）

### 3. polish-orchestrator.md
- **路径**: `references/polish-orchestrator.md`
- **大小**: 7.3 KB
- **用途**: 润色编排器文档，说明两阶段润色的协调逻辑
- **内容**:
  - 阶段详解
  - Python 实现示例
  - 模式差异（默认/fast/minimal）
  - 质量检查清单
  - 故障排查

### 4. POLISH_USAGE.md
- **路径**: `references/POLISH_USAGE.md`
- **大小**: 6.5 KB
- **用途**: 快速使用指南
- **内容**:
  - 快速开始
  - 手动使用方法（Claude Code / DeepSeek API / Claude API）
  - 验证输出质量
  - 常见问题
  - 性能优化

## 修改文件

### SKILL.md
- **路径**: `webnovel-writer/skills/webnovel-write/SKILL.md`
- **修改位置**: Step 4（第 149-157 行）
- **修改内容**:
  - 原来：单一的 "NCS 复查与轻润色"
  - 现在：三个子步骤
    - Step 4.1: DeepSeek 通用去AI润色（必选）
    - Step 4.2: 番茄版排版优化（必选）
    - Step 4.3: NCS 终检与问题修复（必选）
  - 新增模式差异说明（默认/fast/minimal）

## 工作流程变化

### 修改前
```
Step 2: NCS 主写作
  ↓
Step 3: 审查
  ↓
Step 4: NCS 复查与轻润色
  ↓
Step 5: 提交
```

### 修改后
```
Step 2: NCS 主写作
  ↓
Step 3: 审查
  ↓
Step 4.1: DeepSeek 通用去AI润色
  ↓
Step 4.2: 番茄版排版优化
  ↓
Step 4.3: NCS 终检与问题修复
  ↓
Step 5: 提交
```

## 使用方式

### 自动使用（推荐）
运行 `/webnovel-writer:webnovel-write [章节号]` 时，Step 4 会自动执行两阶段润色。

### 手动使用（调试）
```bash
# 进入 references 目录
cd webnovel-writer/skills/webnovel-write/references

# 查看提示词
cat deepseek-universal-polish.yaml
cat tomato-mobile-formatting.yaml

# 在 Claude Code 中使用
# 1. 读取提示词内容
# 2. 在对话中说："请使用上面的提示词润色以下章节：[粘贴章节]"
```

## 技术细节

### 提示词格式
- **格式**: YAML
- **编码**: UTF-8
- **用途**: 作为 LLM 的 system prompt 或 user prompt 前置部分

### LLM 选择
- **推荐**: DeepSeek-V3、Claude Opus 4
- **可用**: Claude Sonnet 4、GPT-4o
- **不推荐**: 小模型（< 70B）

### 中间文件
- `.webnovel/tmp/polish_stage1.md`: Stage 1 输出（文学化底稿）
- 最终输出覆盖原文件: `正文/第{NNNN}章-{title}.md`

## 质量保证

### Stage 1 输出检查
- ✓ 无 AI 填充词（综上所述、值得注意的是等）
- ✓ 无 AI 模板段落（首先其次最后等）
- ✓ 引号统一为「」『』
- ✓ 数字已汉字化

### Stage 2 输出检查
- ✓ 对话独立成段
- ✓ 段落长度 ≤ 80 字
- ✓ 无番茄禁忌词（不知不觉间等）
- ✓ 节奏明快

### Stage 3 输出检查
- ✓ `anti_ai_force_check=pass`
- ✓ 所有 critical issue 已修复
- ✓ 未触碰润色红线

## 兼容性

### 与现有流程兼容
- ✓ 不影响 Step 1-3 和 Step 5-6
- ✓ 保留原有的 `polish-guide.md` 用于 Step 4.3
- ✓ 保留原有的 NCS 集成

### 模式支持
- ✓ 默认模式：完整执行 4.1 → 4.2 → 4.3
- ✓ `--fast` 模式：4.1 和 4.2 正常，4.3 简化
- ✓ `--minimal` 模式：跳过 4.1 和 4.2，仅 4.3

## 性能影响

### 时间成本
- Stage 1: ~30-60 秒（取决于 LLM 速度）
- Stage 2: ~30-60 秒
- Stage 3: ~30-60 秒（原有流程）
- **总增加**: ~60-120 秒 / 章

### 经济成本
- DeepSeek API: ~$0.002 / 章（Stage 1 + Stage 2）
- Claude API: ~$0.02 / 章（Stage 1 + Stage 2）

## 后续优化建议

1. **批量处理**: 实现多章节并行润色
2. **缓存机制**: 对相同内容避免重复润色
3. **A/B 测试**: 对比润色前后的读者反馈
4. **自定义配置**: 允许用户调整段落长度、替换概率等参数
5. **平台适配**: 为其他平台（起点、晋江等）创建专属排版规则

## 回滚方案

如果需要回退到原有流程：

```bash
# 1. 恢复 SKILL.md
git checkout HEAD -- webnovel-writer/skills/webnovel-write/SKILL.md

# 2. 删除新增文件
rm references/deepseek-universal-polish.yaml
rm references/tomato-mobile-formatting.yaml
rm references/polish-orchestrator.md
rm references/POLISH_USAGE.md
rm references/INTEGRATION_SUMMARY.md
```

## 联系与反馈

如有问题或建议，请：
1. 查看 `POLISH_USAGE.md` 的常见问题部分
2. 查看 `polish-orchestrator.md` 的故障排查部分
3. 检查 `.webnovel/tmp/` 中的中间文件进行调试

---

**集成完成时间**: 2026-05-10  
**版本**: v1.0  
**状态**: ✓ 已完成
