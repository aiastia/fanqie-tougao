---
name: lofter-publish
description: 把墨语项目的小说章节发布到 LOFTER（老福特）长篇连载合集。触发方式：/lofter-publish、「发章到老福特」「发到LOFTER」「老福特更新章节」。全流程 DOM 定位+直接点击，不用截图/视觉模型。
---

# LOFTER 章节发布技能

把墨语（moyu）项目章节发布到 LOFTER 长篇连载合集。排版=每段一个 `<p>`，与已发章节一致。

## 已知上下文（2026-08-22 实测）

| 项 | 值 |
|---|---|
| 合集 | 先婚厚爱是违约行为｜夜幕之下（collectionId=30497742） |
| 墨语项目 ID | 28 |
| 章节管理页 | `https://www.lofter.com/front/blog/long-series/chapters?collectionId=30497742` |
| 标准标签 | `夜幕之下,夜幕之下游戏,红手套bg,先婚厚爱是违约行为`（逗号串一次输入） |
| 发布按钮稳定坐标 | (994, 781)（多章实测一致；仍建议每章 eval 复核） |
| **硬规则** | **正文 <1500 字（编辑器计数含标点）发布必报 VALIDATION_FAILED，且无任何界面提示** |

## 硬规则与对策

- **1500字下限**：发布失败 console 只有 `发布失败: VALIDATION_FAILED`、无请求发出、无红字 = 字数不够。对策=文末加「作者的话」段补足（第6章1426字+88字作者的话=1514过线）。墨语 word_count 与 LOFTER 计数口径不同，**以编辑器字数按钮为准**。
- **草稿占坑**：存在草稿/已删除行的章时，「更新章节」开出来的序号会跳过被占的号。**填内容前先核对序号**；若要发被草稿占的章，点该章行内的「发布章节」按钮（打开 chapterId 编辑页，编辑器是空的、可正常输入，直接填全套）。

## 第一步：下载章节正文（勿手敲转录）

```bash
# MCP get_chapter_content(chapter_number) 拿 chapter_id；
# token 从墨语标签页取：eval 'localStorage.getItem("moyu_token")'
TOKEN="..."; C=/usr/bin/curl
$C -s -H "Authorization: Bearer $TOKEN" \
  "https://mybook.124678.xyz/api/projects/28/chapters/<chapter_id>" -o /tmp/lofter/raw.json
python3 - <<'PY'
import json
d = json.load(open("/tmp/lofter/raw.json"))
paras = [x.strip() for x in d["content"].replace("\r\n","\n").split("\n") if x.strip()]
open("/tmp/lofter/ch<N>.txt","w").write("\n".join(paras))
print(d["title"], "chars:", len("".join(paras)))   # 记住这个数=编辑器字数
PY
```

单换行=一个 `<p>`（墨语的 \n\n 已在上面压成 \n）。字数 <1500 时在此步就拼作者的话。

## 第二步：逐章发布（每章3个命令块，全 DOM 验证）

**块1 开发布页并核对序号**（tab t55=章节管理页）：

```bash
agent-browser --cdp 9222 tab t55 && agent-browser --cdp 9222 wait 500
agent-browser --cdp 9222 find text "更新章节" click && agent-browser --cdp 9222 wait 3500
agent-browser --cdp 9222 eval '(()=>(document.body.innerText.match(/章节序号[0-9]+ ?[^0-9\s]*/)||["无"])[0])()'
# 序号不对=有草稿占坑，见上「硬规则与对策」
```

**块2 填标题+正文+标签（逗号一次成型），DOM 验证**：

```bash
agent-browser --cdp 9222 fill 'input[placeholder*="标题"]' "<标题>"
agent-browser --cdp 9222 click 'iframe' && agent-browser --cdp 9222 keyboard inserttext "$(cat /tmp/lofter/ch<N>.txt)"
agent-browser --cdp 9222 click 'input[placeholder*="标签"]' && agent-browser --cdp 9222 type 'input[placeholder*="标签"]' "夜幕之下,夜幕之下游戏,红手套bg,先婚厚爱是违约行为" && agent-browser --cdp 9222 press "Enter" && agent-browser --cdp 9222 wait 700
# 一条 eval 同时验证字数+4个chip：
agent-browser --cdp 9222 eval '(()=>({count:[...document.querySelectorAll("button,span,div")].filter(el=>el.children.length===0&&/^[0-9]{4}$/.test(el.textContent.trim())&&el.offsetParent).map(e=>e.textContent.trim())[0], chips:[...new Set(document.body.innerText.match(/#[^\s#]{1,20}/g)||[])].slice(0,4)}))()'
# count 必须=第一步打印的chars；chips 必须4个都在。不对就别发。
```

**块3 坐标发布+console验证**（发布是带隐藏下拉的组合按钮，ref点击/CSS点击都会点偏中心静默存草稿，必须点可见「发布」叶子）：

```bash
agent-browser --cdp 9222 eval '(()=>{const b=[...document.querySelectorAll("button")].find(x=>x.textContent.trim().startsWith("发布")||x.textContent.includes("现在发布")); const v=[...b.querySelectorAll("*")].filter(el=>el.children.length===0&&el.textContent.trim()==="发布"&&el.getBoundingClientRect().width>0); const r=(v[0]||b).getBoundingClientRect(); return Math.round(r.x+r.width/2)+" "+Math.round(r.y+r.height/2)})()'
agent-browser --cdp 9222 console --clear; agent-browser --cdp 9222 mouse move 994 781 && agent-browser --cdp 9222 mouse down && agent-browser --cdp 9222 mouse up && agent-browser --cdp 9222 wait 4000
agent-browser --cdp 9222 console | grep -oE '"isPublished":(true|false)|"allowView":50|VALIDATION_FAILED|closeWindow' | sort | uniq -c
# 成功=isPublished:true + allowView:50 + closeWindow；VALIDATION_FAILED=字数<1500
```

## 第三步：全部发完后核验

```bash
agent-browser --cdp 9222 tab t55 && agent-browser --cdp 9222 reload && agent-browser --cdp 9222 wait 3000
agent-browser --cdp 9222 eval 'document.body.innerText.substring(120,900)'
# 每章「已发布」、字数≈chars（LOFTER列表口径略有出入正常）
```

## 坑位速查

- **不用视觉模型**：截图判读慢且有误判（把正常表单读成报错）；一切验证走 DOM（上表 eval）。
- tab 切换后 snapshot refs 全失效；优先 `find text "<文本>" click`（实测可用）或 CSS 选择器，最后才 snapshot。
- eval 的 `const` 跨调用残留 → IIFE；bash 里嵌 agent-browser 输出取坐标要 `tr -d '"'`，不稳，坐标直接写死两步走。
- 标签逗号串+一次 Enter=4个chip一次成型（实测6+章）；联想下拉项不是chip，以上面 chips eval 为准。
- 「预览」会开新标签页切走上下文，流程已验证不需要预览。
- 跨域编辑器 iframe 切不进 frame 上下文，交互=click 'iframe'+keyboard。
- 每章从管理页重新开发布页，不复用旧页；发布成功页面自动关闭（closeWindow）。
- 清空编辑器：click 'iframe' → press "Meta+a" → press "Delete"（macOS）。
