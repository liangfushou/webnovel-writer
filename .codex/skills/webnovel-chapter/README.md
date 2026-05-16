# /webnovel-chapter 使用说明

## 快速开始

```bash
# 写第 1 章
/webnovel-chapter 1

# 写第 12 章
/webnovel-chapter 12

# 自动写下一章（从 state.json 读取）
/webnovel-chapter
```

## 完整流程（自动执行）

| 步骤 | 说明 | 时间 |
|------|------|------|
| 📋 准备合同 | 刷新章节合同树 | ~10秒 |
| 🔧 生成上下文 | NCS 桥接包（00-09 文件） | ~20秒 |
| ✍️ NCS 写作 | 生成章节初稿 | ~2-3分钟 |
| 🔍 审查 | 检查设定/时间线/连续性 | ~1分钟 |
| 🎨 **去AI润色** | 删除 AI 痕迹、格式规范 | ~1-2分钟 |
| 📱 **番茄排版** | 对话独立、段落切分 | ~1分钟 |
| ~~✅ 终检~~ | ~~Anti-AI 检查~~ ⚠️ **暂时禁用** | ~~0秒~~ |
| 💾 提交备份 | 数据提取、投影、Git | ~30秒 |

**总时间**：约 3-5 分钟/章

**注意**：NCS 终检暂时禁用，两阶段润色已足够。

## 两阶段润色详解

### 🎨 Stage 1: 去AI润色

**目标**：让文字更像人写的

**做什么**：
- ❌ 删除 AI 填充词（综上所述、值得注意的是等 23 条）
- ❌ 删除 AI 模板段落（首先其次最后等 18 种）
- ✅ 引号统一为「」『』
- ✅ 数字汉字化（1987年 → 一九八七年）
- ✅ 字典替换（278 条规则）
- ✅ 语义重写（消除 AI 腔、增强文学质感）

**效果**：
- 删除前：`综上所述，他需要做三件事：首先，拿到证据；其次，稳住队友；最后，公开反击。`
- 删除后：`他先把证据攥在手里，转身去找队友。人得先稳住，反击才能一刀见血。`

### 📱 Stage 2: 番茄排版

**目标**：适配手机阅读，短平快节奏

**做什么**：
- ✅ 对话独立成段（前后双换行）
- ✅ 段落最多 80 字、2 句话
- ✅ 删除番茄禁忌词（不知不觉间等 9 条）
- ✅ 节奏提速（"他想了想" → "他眼珠一转"）
- ✅ 动作强化（"拿" → "一把抓过"）

**效果**：
- 优化前：`他走过去说「你好」然后继续前进。`
- 优化后：
  ```
  他大步上前。
  
  「你好。」
  
  话音刚落，他闪身逼近。
  ```

## 模式选择

### 默认模式（推荐）
```bash
/webnovel-chapter 1
```
完整执行所有步骤，包含两阶段润色

### Fast 模式
```bash
/webnovel-chapter 1 --fast
```
润色正常，终检简化

### Minimal 模式
```bash
/webnovel-chapter 1 --minimal
```
跳过两阶段润色，仅排版和终检

## 验证输出质量

```bash
# 查看生成的章节
cat 正文/第0001章-*.md

# 检查是否还有 AI 填充词
grep -E "综上所述|值得注意的是" 正文/第0001章-*.md

# 检查引号格式
grep -E '「|」' 正文/第0001章-*.md

# 检查段落长度
awk 'BEGIN{RS="\n\n"} {if(length($0)>80) print NR": "length($0)}' 正文/第0001章-*.md
```

## 常见问题

### Q: 命令列表中看不到 /webnovel-chapter？
A: 重启 Claude Code，或者直接输入命令也能用。

### Q: 可以关闭两阶段润色吗？
A: 使用 `--minimal` 模式，或者用 `/webnovel-writer:webnovel-write`。

### Q: 段落太短/太长怎么办？
A: 编辑 `webnovel-writer/skills/webnovel-write/references/tomato-mobile-formatting.yaml`，修改 `max_chars_per_paragraph: 80`。

### Q: 润色改变了剧情怎么办？
A: 这是严重错误，立即停止。检查提示词中的"保留原意"规则是否生效。

### Q: 可以只用 Stage 1 不用 Stage 2 吗？
A: 目前不支持，但可以修改 SKILL.md 的 Step 4 来实现。

## 调整配置

编辑配置文件：
```bash
vim webnovel-writer/skills/webnovel-write/references/tomato-mobile-formatting.yaml
```

可调整参数：
```yaml
config:
  max_chars_per_paragraph: 80      # 段落最大字数
  max_sentences_per_paragraph: 2   # 段落最多句子数
  dialogue_isolation_enforced: true # 对话是否独立
  pacing_accelerate_rate: 0.85     # 节奏提速概率
```

## 文档索引

- **本文件**: `.codex/skills/webnovel-chapter/SKILL.md`
- **提示词 1**: `webnovel-writer/skills/webnovel-write/references/deepseek-universal-polish.yaml`
- **提示词 2**: `webnovel-writer/skills/webnovel-write/references/tomato-mobile-formatting.yaml`
- **详细文档**: `webnovel-writer/skills/webnovel-write/references/README_POLISH.md`

---

**版本**: v1.0  
**更新时间**: 2026-05-10  
**状态**: ✅ 可用
