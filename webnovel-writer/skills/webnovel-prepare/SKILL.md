---
name: webnovel-prepare
description: 为指定章节生成写作合同（story-system），准备好写章所需的全部元数据。
allowed-tools: Read Bash Grep
---

# 章节准备流程

## 目标

为指定章节生成完整的 story-system 合同树，包括：
- MASTER_SETTING.json（主设定合同）
- volume_{NNN}.json（卷级合同）
- chapter_{NNN}.json（章节合同）
- chapter_{NNN}.review.json（审查合同）

## 用法

```
/webnovel-writer:webnovel-prepare [章节号]
```

**章节号可选**：
- 如果不提供章节号，自动从 `state.json` 读取 `current_chapter + 1`
- 例如：当前写完第 1 章，直接运行 `/webnovel-writer:webnovel-prepare` 会自动准备第 2 章

例如：
```
/webnovel-writer:webnovel-prepare      # 自动检测下一章
/webnovel-writer:webnovel-prepare 1    # 明确指定第 1 章
/webnovel-writer:webnovel-prepare 5    # 明确指定第 5 章
```

## 执行流程

### Step 1：环境检查

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:?}/scripts"

python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" preflight
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
```

验证：
- scripts_dir 存在
- project_root 正确
- state.json 存在

### Step 2：读取章节信息

从大纲文件中提取章节信息：

1. 读取 `state.json` 获取 genre 和 current_volume
2. 根据章节号确定卷号（1-50章→卷1，51-100章→卷2，以此类推）
3. 读取 `大纲/第{N}卷-详细大纲.md` 获取章节目标

**章节目标提取规则**：
- 查找 `### 第 {章节号} 章：` 开头的章节
- 提取 `- 目标:` 后面的内容作为 query
- 如果没有明确目标，使用章节标题

### Step 3：生成合同

```bash
GENRE="$(python -X utf8 -c "import json,sys; s=json.load(open('${PROJECT_ROOT}/.webnovel/state.json',encoding='utf-8')); print(s.get('project_info',{}).get('genre',''))")"

python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" \
  story-system "{章节目标}" \
  --genre "${GENRE}" \
  --chapter {章节号} \
  --persist \
  --emit-runtime-contracts \
  --format json
```

### Step 4：验证输出

检查以下文件是否生成：

```bash
ls -la "${PROJECT_ROOT}/.story-system/MASTER_SETTING.json"
ls -la "${PROJECT_ROOT}/.story-system/volumes/volume_{NNN}.json"
ls -la "${PROJECT_ROOT}/.story-system/chapters/chapter_{NNNN}.json"
ls -la "${PROJECT_ROOT}/.story-system/reviews/chapter_{NNNN}.review.json"
```

### Step 5：输出摘要

向用户报告：
- 生成的合同文件路径
- 章节目标
- 题材类型
- 下一步操作提示：`/webnovel-writer:webnovel-write {章节号}`

## 错误处理

| 错误场景 | 处理方式 |
|---------|---------|
| 大纲文件不存在 | 提示用户先运行 `/webnovel-writer:webnovel-plan` |
| 章节信息缺失 | 提示用户补充大纲中的章节目标 |
| state.json 缺失 genre | 提示用户先运行 `/webnovel-writer:webnovel-init` |
| story-system 命令失败 | 显示完整错误信息，提示检查 CSV 数据 |

## 输出格式

成功时输出：

```
✓ 章节合同已生成

章节：第 1 章
目标：从灵堂脱身，看穿自己被当成死人
题材：规则怪谈+末世

生成文件：
  - .story-system/MASTER_SETTING.json
  - .story-system/volumes/volume_001.json
  - .story-system/chapters/chapter_001.json
  - .story-system/reviews/chapter_001.review.json

下一步：运行 /webnovel-writer:webnovel-write 1
```

## 批量准备

如果用户传入章节范围，例如 `1-5`，则依次为每章生成合同：

```
/webnovel-writer:webnovel-prepare 1-5
```

会依次执行：
- prepare 1
- prepare 2
- prepare 3
- prepare 4
- prepare 5

## 注意事项

- 如果合同文件已存在，默认会覆盖（story-system 会备份旧文件为 .bak）
- 章节号必须在大纲规划范围内
- 首次运行会生成 MASTER_SETTING，后续章节会复用
- volume 合同只在该卷首章时生成，后续章节复用
