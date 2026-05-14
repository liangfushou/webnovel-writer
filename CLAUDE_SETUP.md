# Claude Code 权限配置说明

本项目使用 Claude Code CLI 执行小说马拉松写作流水线。为避免每条命令都弹出授权提示，需要配置权限白名单。

## 快速配置

项目根目录已包含 `.claude/settings.json`，克隆仓库后 Claude Code 会自动读取。无需额外操作。

如果你的环境没有自动加载，手动创建：

```bash
mkdir -p .claude
cp .claude/settings.json .claude/settings.json
```

## 权限内容

`.claude/settings.json` 中的 `permissions.allow` 包含以下模式：

| 模式 | 用途 |
|------|------|
| `Bash(python3 -X utf8 *)` | 运行写作流水线脚本（review-pipeline、chapter-commit 等） |
| `Bash(PYTHONPATH=* python3 -X utf8 *)` | 带模块路径的脚本调用 |
| `Bash(wc -m *)` | 字数统计校验（强制 >= 2000 字） |
| `Bash(git add *)` | 暂存章节文件 |
| `Bash(git commit *)` | 提交章节 |
| `Bash(git push *)` | 推送到远程 |
| `Bash(sqlite3 *)` | 数据库操作 |

## 马拉松流水线步骤

每章执行顺序：

1. 写初稿 → `wc -m` 校验 >= 2000 字
2. DS 润色
3. 生成数据文件（extraction / fulfillment / disambiguation / review）
4. `review-pipeline.py --project-root X --chapter N --review-results X`
5. `chapter-commit.py --project-root X --chapter N --review-result X --fulfillment-result X --disambiguation-result X --extraction-result X`
6. git commit

## 脚本调用格式

```bash
PYTHONPATH="/path/to/webnovel-writer/webnovel-writer/scripts" python3 -X utf8 /path/to/script.py [args]
```

## 注意事项

- 所有 Python 脚本必须带 `-X utf8` 参数（中文编码）
- 章节字数硬性要求 >= 2000 字符，不达标不进入下一步
- `.claude/settings.json` 是项目级配置，不会影响其他项目
