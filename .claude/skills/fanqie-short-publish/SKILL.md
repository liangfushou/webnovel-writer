---
name: fanqie-short-publish
version: 1.0.0
description: "番茄短故事发布自动化。通过 CDP 浏览器自动化将短篇小说推送到番茄小说短故事草稿箱。包括：创建短故事、粘贴正文、智能分章、上传封面、选择分类、存草稿。触发词：番茄发布, 发布短故事, fanqie publish, 推送番茄, 短故事上传, 番茄草稿箱"
metadata:
  openclaw:
    source: local
---

# 番茄短故事发布

通过 CDP 浏览器自动化，将本地短篇小说推送到番茄小说短故事草稿箱。

## 前置条件

- Chrome 已启动 CDP 调试端口（通过 `browser-cdp` skill 启动）
- 已登录番茄作家后台（`fanqienovel.com`）
- `agent-browser` 命令行工具已安装
- Node.js 16+
- 本地有 `ws` 模块可用（用于 CDP 文件上传）

---

## 用法

```bash
/fanqie-short-publish [项目目录]
```

**参数**：
- `项目目录`：小说项目根目录路径（包含 `正文/`、`封面/`、`发布数据/` 等）
- 不传则使用当前 PROJECT_ROOT

**示例**：
```bash
/fanqie-short-publish /Users/xxx/project/小说/new/webnovel-writer/被全队推进S级副本当炮灰
```

---

## 输入数据要求

### 必须存在的文件

| 文件 | 说明 |
|------|------|
| `正文/第{NNNN}章-{title}.md` | 各章节正文文件 |
| `发布数据/publish_metadata.json` | 发布元数据（书名、分类、简介等） |

### 可选文件

| 文件 | 说明 |
|------|------|
| `封面/封面_v1.png` | 自定义封面图片（jpg/png，建议 600x800） |

### publish_metadata.json 格式

```json
{
  "book_info": {
    "title": "书名全称",
    "author": "笔名",
    "genre": "题材",
    "platform": "番茄小说",
    "status": "已完结"
  },
  "synopsis": {
    "one_line": "一句话简介",
    "short": "短简介（100字内）",
    "full": "完整简介"
  },
  "publishing": {
    "main_category": "悬疑惊悚",
    "sub_categories": ["男频脑洞", "玄幻仙侠"],
    "use_ai": "是",
    "tags": ["规则怪谈", "副本流", "身份反转"]
  },
  "chapter_list": [
    {"chapter": 1, "title": "投票送死", "words": 2538},
    {"chapter": 2, "title": "这副本是我写的", "words": 2485}
  ]
}
```

---

## 执行流程

### Step 0：预检

```bash
# 确认 CDP 端口可用
agent-browser --cdp 9222 eval 'window.location.href'

# 确认已登录番茄
agent-browser --cdp 9222 open "https://fanqienovel.com/main/writer/short-manage"
agent-browser --cdp 9222 wait 3000
agent-browser --cdp 9222 eval 'document.body.innerText.includes("创建短故事") ? "logged_in" : "not_logged_in"'
```

如果未登录，提示用户手动登录后重试。

---

### Step 1：创建短故事

```bash
# 点击"创建短故事"按钮
agent-browser --cdp 9222 eval '
var btn = Array.from(document.querySelectorAll("button")).find(function(b){
  return b.innerText.includes("创建短故事");
});
if(btn){ btn.click(); "clicked"; } else { "not_found"; }
'
```

等待页面跳转到编辑页面（URL 包含 `publish-short`）。

---

### Step 2：填写书名

```bash
agent-browser --cdp 9222 eval '
var input = document.querySelector("input[placeholder*=短故事名称]");
if(input){
  var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  nativeInputValueSetter.call(input, "${TITLE}");
  input.dispatchEvent(new Event("input", {bubbles: true}));
  "title_set";
} else { "input_not_found"; }
'
```

---

### Step 3：粘贴正文

**关键点**：番茄使用 ProseMirror 编辑器，直接设置 innerHTML 即可。

```bash
# 读取所有章节正文，拼接为 HTML
# 章节标题必须用 <h1> 标签（番茄识别为"章节标题"格式）
# 正文段落用 <p> 标签
# 空行用 <p><br class="ProseMirror-trailingBreak"></p>

agent-browser --cdp 9222 eval '
var editor = document.querySelector(".ProseMirror");
editor.innerHTML = ${HTML_CONTENT};
editor.dispatchEvent(new Event("input", {bubbles: true}));
"content_set";
'
```

**正文 HTML 拼接规则**：
1. 每章标题：`<h1>第N章 标题</h1>`
2. 空行：`<p><br class="ProseMirror-trailingBreak"></p>`
3. 正文段落：`<p>段落内容</p>`
4. 段落间空行：`<p><br class="ProseMirror-trailingBreak"></p>`

**重要**：章节标题必须用 `<h1>` 标签，不能用 `<h2>` 或 `<p>`。只有 `<h1>` 才会被番茄的智能分章识别为"章节标题"格式。

---

### Step 4：智能分章

粘贴正文后，等待自动保存，然后检查分章是否自动识别：

```bash
# 等待自动保存
agent-browser --cdp 9222 wait 3000

# 检查分章状态
agent-browser --cdp 9222 eval '
var cat = document.querySelector("[class*=catalog]");
cat ? cat.innerText.substring(0, 500) : "no_catalog";
'
```

如果显示"暂未设置章节"，点击"智能分章"按钮：

```bash
agent-browser --cdp 9222 eval '
document.querySelector(".short-catalog-container-switch").click();
"clicked_smart_split";
'
```

**验证**：分章成功后，目录区域应显示所有章节标题列表。

---

### Step 5：选择分类

**重要规则：分类最少选 2 个，最好 3 个。**

番茄短故事分类系统：
- 左侧有分类维度标签页：主分类、情节、角色、情绪、背景
- 每个维度可选 1 个，总共最多 8 个
- 主分类必选（单选替换模式）
- 其他维度可叠加

```bash
# 打开分类下拉
agent-browser --cdp 9222 eval '
var catSelect = document.querySelector(".publish-short-category-select");
catSelect.scrollIntoView({block:"center"});
catSelect.click();
"opened";
'

# 等待下拉展开
agent-browser --cdp 9222 wait 1000

# 选择主分类
agent-browser --cdp 9222 eval '
var dropdown = document.querySelector(".publish-short-category-select-pop");
var items = dropdown.querySelectorAll(".publish-short-category-select-item");
for(var i=0; i<items.length; i++){
  if(items[i].innerText.trim() === "${MAIN_CATEGORY}"){
    items[i].click(); break;
  }
}
"selected_main";
'

# 切换到"情节"维度添加第二个分类
agent-browser --cdp 9222 eval '
var dropdown = document.querySelector(".publish-short-category-select-pop");
var labels = dropdown.querySelectorAll(".publish-short-category-select-label");
for(var i=0; i<labels.length; i++){
  if(labels[i].innerText.includes("情节")){
    labels[i].click(); break;
  }
}
"switched_to_plot";
'

# 选择情节分类
agent-browser --cdp 9222 eval '
var items = document.querySelectorAll(".publish-short-category-select-item");
for(var i=0; i<items.length; i++){
  if(items[i].innerText.trim() === "${SUB_CATEGORY_1}"){
    items[i].click(); break;
  }
}
"selected_sub1";
'

# 关闭下拉
agent-browser --cdp 9222 eval 'document.body.click(); "closed";'
```

**可用主分类列表**：
婚姻家庭、女生生活、男生生活、现言甜宠、虐心婚恋、青春虐恋、男生情感、女性成长、悬疑惊悚、玄幻仙侠、宫斗宅斗、男频衍生、女频衍生、年代、纯爱、其他、古言甜宠、古风世情、都市日常、男频脑洞、女频脑洞、民国旧影、古言虐恋、历史古代

---

### Step 6：设置"是否使用AI"

```bash
agent-browser --cdp 9222 eval '
var radios = document.querySelectorAll(".publish_short_config_use_ai input[type=radio]");
for(var i=0; i<radios.length; i++){
  var label = radios[i].parentElement.querySelector(".arco-radio-text");
  if(label && label.innerText.trim() === "${USE_AI}"){
    radios[i].click(); break;
  }
}
"ai_set";
'
```

---

### Step 7：上传封面

番茄短故事封面上传流程：

```bash
# 1. 点击封面区域打开封面面板
agent-browser --cdp 9222 eval '
var coverBtn = document.querySelector(".publish-short-config-book-cover-content");
coverBtn.click();
"opened_cover_panel";
'

# 2. 切换到"本地上传"标签页
agent-browser --cdp 9222 eval '
var tabs = document.querySelectorAll("[role=tab]");
var uploadTab = Array.from(tabs).find(function(t){ return t.innerText.includes("本地上传"); });
if(uploadTab){ uploadTab.click(); "switched_to_upload"; } else { "tab_not_found"; }
'

# 3. 使用 CDP upload 命令上传文件
agent-browser --cdp 9222 upload "input[type=file]" "${COVER_PATH}"

# 4. 等待上传完成，点击"确定"
agent-browser --cdp 9222 wait 3000
agent-browser --cdp 9222 eval '
var btns = document.querySelectorAll("button");
for(var i=0; i<btns.length; i++){
  if(btns[i].innerText && btns[i].innerText.trim() === "确定" && btns[i].offsetHeight > 0){
    btns[i].click(); break;
  }
}
"confirmed_cover";
'
```

**封面要求**：
- 格式：jpg/png/jpeg
- 建议尺寸：600x800 像素
- 文件大小：不超过 5MB
- 内容：清晰的作品名称和作者笔名，符合作品风格

---

### Step 8：勾选发布协议

```bash
agent-browser --cdp 9222 eval '
var checkboxes = document.querySelectorAll("input[type=checkbox]");
for(var i=0; i<checkboxes.length; i++){
  if(!checkboxes[i].checked){ checkboxes[i].click(); }
}
"agreement_checked";
'
```

---

### Step 9：存草稿

```bash
agent-browser --cdp 9222 eval '
var saveBtn = Array.from(document.querySelectorAll("button")).find(function(b){
  return b.innerText.trim() === "存草稿";
});
if(saveBtn){ saveBtn.click(); "saved"; } else { "save_btn_not_found"; }
'
```

等待保存完成（页面显示"已保存"）。

---

### Step 10：验证

```bash
# 验证保存成功
agent-browser --cdp 9222 eval '
var status = document.body.innerText;
var saved = status.includes("已保存");
var wordCount = status.match(/正文字数\s*(\d+)/);
var chapters = document.querySelectorAll("[class*=catalog] [class*=chapter], [class*=catalog] div").length;
JSON.stringify({saved: saved, wordCount: wordCount ? wordCount[1] : "unknown", url: window.location.href});
'
```

---

## 完成输出

```
✓ 番茄短故事草稿已保存
  书名：${TITLE}
  字数：${WORD_COUNT}
  章节：${CHAPTER_COUNT} 章
  分类：${CATEGORIES}
  封面：${COVER_STATUS}
  草稿链接：${DRAFT_URL}
```

---

## 已知坑点

| 问题 | 解决方案 |
|------|----------|
| 章节标题不被智能分章识别 | 必须用 `<h1>` 标签，`<h2>` 和 `<p>` 都不行 |
| innerHTML 修改后 ProseMirror 状态不同步 | 修改后 dispatch `input` 事件，然后存草稿刷新页面 |
| 分类下拉主分类是单选替换 | 需要从不同维度标签页分别选择才能多选 |
| 封面上传没有直接的 file input | 需要先点击封面区域 → 切换"本地上传"tab → 再 upload |
| `agent-browser upload` 需要 file input 可见 | 确保"本地上传"tab 已激活 |
| "下一步"按钮不跳转 | 番茄短故事是单页面，所有设置在同一页完成 |
| 正文粘贴后空行过多 | 段落间只用一个 `<p><br></p>` 作为空行 |

---

## 注意事项

- **不要自动发布**：只存草稿，发布由用户手动操作
- **分类至少 2 个，最好 3 个**：从不同维度标签页各选一个
- **封面尺寸**：建议 600x800，最大 5MB
- **审核时间**：番茄审核工作时间 7:00-24:00，夜间发文会卡审核
- **正文格式**：使用中文引号「」，段落间留空行
- **字数限制**：番茄短故事无明确上限，但建议 1-5 万字
