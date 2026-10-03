---
name: lofter-short-publish
description: 把墨语短篇（单章成篇）发布到 LOFTER 博客单发文章，带标签+回礼（赠礼解锁后段）+关允许转载。触发：/lofter-short-publish、「发短篇到老福特」「LOFTER 单发」「发回礼」。与 lofter-publish（长篇连载合集发章）是两条独立流程，勿混用。
---

# LOFTER 短篇单发技能（文字帖+回礼）

单篇一次性发出：正文前 60-70% 进主帖，情感后段进「回礼」（读者送粮票/看广告解锁）。2026-10-03 双篇实测（P161/P162）。

## 常量（20261003 实测）

| 项 | 值 |
|---|---|
| 入口页 | `https://www.lofter.com/dashboard/`（须已登录；博客=yooyol） |
| 发文字入口 | `a.publishlink.n21`（href=#publish=text），点击后 URL 变 `#publish=text`、弹 rc-dialog，页面不跳转 |
| 弹窗 | `.lfc-modal`（rc-dialog-wrap 内）；字段：标题 input / 正文 iframe / 标签 input / 底部 取消·预览·发布 |
| 编辑器 | 跨域 iframe（lofter.lf127.net），切不进 frame，交互=真鼠标点击+inserttext |
| 标准标签配方 | 同人 tag 6 个：`作品名,CP名,主角名,别名,甜文,HE`（逗号串一次输入+Enter） |

## 硬规则（先读）

1. **顺序铁律：先填编辑器正文 → 再打标签 → 再关转载 → 最后开回礼弹窗填回礼。** 回礼弹窗的 textarea 是焦点黑洞：一旦聚焦，会抢回所有后续点击/键盘的焦点（连 blur 都拦不住），必须关掉弹窗才解除。顺序反了 = inserttext 灌进回礼框（P161 实录：正文 6995 字灌进了回礼框）。
2. **iframe 焦点必须验证**：真鼠标点击 iframe 中心后，eval `document.activeElement.tagName` 必须返回 `"IFRAME"` 才准 inserttext。不是就重试点击。
3. **所有坐标现测现用**：标签联想下拉每开合一次，弹窗内所有行都漂移（回礼设置行曾从 y=550 漂到 y=570 再漂走）。禁止缓存坐标；scrollIntoView({block:"center"}) → 量中心 → 同一命令内点。
4. **弹窗会堆僵尸副本**：同一弹窗在 DOM 里可能有 2-3 份实例（旧的 display:none/零尺寸）。一切查询先按 `getBoundingClientRect().width>0` 过滤出活的实例，按钮点击前必须 elementFromPoint 命中测试（命中的不是按钮本体=被盖住，换下一个）。
5. **回礼确定要点两次**：第一次点=异步校验，弹窗不动；第二次点才真关。点完校验 textarea 不可见才算关。
6. **发布按钮要点叶子**：底部「发布」是组合按钮（发布｜现在发布｜自动发布下拉），点 `children.length===0` 且 text==="发布" 的叶子节点（约 83×18，组合按钮右半），ref/CSS 点中心会点偏。
7. eval 输出带引号，进 bash 字符串比较前必须 `tr -d '"'` 剥引号（吃过亏：`"[\"none\"]"` != `none` 导致条件守卫误触发点击）。

## 第一步：取正文+切分（墨语库）

```bash
# MCP 直调（MCP fetch failed 时走 /tmp/mcp_call.py；输出第一行=JSON）
python3 /tmp/mcp_call.py get_chapter_content '{"chapter_number":1,"project_id":<PID>}' > /tmp/lofter3/p<N>_raw.json
python3 - <<'PY'
import json
d=json.loads(open('/tmp/lofter3/p<N>_raw.json').read().splitlines()[0])
paras=[x.strip() for x in d['content'].replace('\r\n','\n').split('\n') if x.strip()]
open('/tmp/lofter3/p<N>_paras.txt','w').write('\n'.join(paras))
total=sum(len(p) for p in paras); run=0
for i,p in enumerate(paras):   # 找切分点：55%-70% 之间的短段（<60字=场景断口）
    run+=len(p)
    if 0.55<=run/total<=0.70 and len(p)<60: print(i, f'{run/total:.0%}', len(p), p[:40])
PY
```

**切分口径**：主线=铺垫+破案/战斗主体，收在 62-67% 处的一个钩子短句上（如「把他带过来。」「待会儿，射准一点。」）；回礼=对峙+情感高光+收尾（约 2300-2400 字）。切完落 `p<N>_main.txt` / `p<N>_gift.txt`。

## 第二步：开弹窗填标题+正文

```bash
agent-browser --cdp 9222 click 'a.publishlink.n21' && agent-browser --cdp 9222 wait 2500
agent-browser --cdp 9222 fill 'input[placeholder*="请输入标题"]' "<书名>"   # 首次 fill 若 Element not found=弹窗渲染竞态，直接重跑
# 正文：真鼠标点 iframe 中心（坐标 eval .lfc-modal iframe 的 rect 现算）
agent-browser --cdp 9222 mouse move <cx> <cy> && agent-browser --cdp 9222 mouse down && agent-browser --cdp 9222 mouse up && agent-browser --cdp 9222 wait 700
agent-browser --cdp 9222 eval 'JSON.stringify(document.activeElement.tagName)'   # 必须=="IFRAME"
agent-browser --cdp 9222 keyboard inserttext "$(cat /tmp/lofter3/p<N>_main.txt)"
```

**字数验证**：弹窗内裸数字元素=编辑器字数（=段落字符和，不含换行）。必须与 main.txt 的字符总数逐字相等。inserttext 按 `\n` 分段成 `<p>`。清空重灌：焦点在 iframe 时 `press Meta+a` + `press Backspace`，验字数=0 再灌。

## 第三步：标签（逗号一次成型）

```bash
agent-browser --cdp 9222 click 'input[placeholder*="添加相关标签"]'
agent-browser --cdp 9222 type 'input[placeholder*="添加相关标签"]' "犬夜叉,犬薇,日暮戈薇,阿篱,甜文,HE"
agent-browser --cdp 9222 press Enter && agent-browser --cdp 9222 wait 800
```

- **坑**：输入后该 input 的 placeholder 被清空，二次定位用 `input[placeholder=""]`（弹窗内另一个空 placeholder 的就是它）。
- **chip 验证**：已挂标签=`.lfc-modal div[role="button"]`、文本 `#xxx`、位于输入框容器内；联想推荐词同样式混在后面——按顺序核对前 N 个等于所填即可（或按容器层级：chip 容器内含 input）。

## 第四步：取消勾选「允许他人转载至LOFTER」

**目标态=不勾选。这个开关只允许「从勾选点成不勾」，绝不反向；已关闭时一个字都不要碰。**

```bash
# 读状态：svg fill，currentColor=勾选（实心圆白勾），none=不勾（空心）
# ⚠️ eval 输出自带引号，必须 tr -d '"' 剥掉再比较——"none" != none 会让守卫误触发反向点击（P162 实录）
S=$(agent-browser --cdp 9222 eval '(()=>{const l=[...document.querySelectorAll(".lfc-modal span")].find(e=>e.offsetParent&&e.textContent.trim()==="允许他人转载至LOFTER");return l.parentElement.querySelector("svg").getAttribute("fill")})()' | tr -d '"')
if [ "$S" = "currentColor" ]; then
  # scrollIntoView 行居中 → 量中心 → 真鼠标点行（同一命令内完成）
fi
# 点完立刻用同一 eval 复验，必须=none；不等就再查（防点到僵尸实例）
```

每次新弹窗默认值都可能重置，发前必查；且**发布前终验清单里还要再查一次**（点后的即时复验可能读到旧实例，终验才算数）。

## 第五步：回礼（后段+解锁提示+全选礼物）

```bash
# 开回礼弹窗：行= .lfc-modal div[role=button] 文本"回礼设置"。有异步校验门：
#   r.click() → 等1.6s → 未开则再 r.click() → 轮询3s（dispatchEvent 指针序列不足以开门，el.click() 才行）
# 弹窗字段：
#   回礼正文 textarea[placeholder*="输入回礼内容"]   ← 用 fill（此框 inserttext 会叠加不替换！）
#   解锁提示 input[placeholder*="礼物即可解锁"]      ← fill，一句话钩子（如「破晓之后：雾墙、破魔箭，和那句迟到的晚安」）
#   回礼类型：彩蛋（默认选中，青绿色）/隐藏结局，短篇后段用彩蛋即可
#   适用礼物卡片 div[class^="ZOuLB"] → el.click() 开「选择礼物」子弹窗
```

选择礼物子弹窗内：
1. **全选**：点 `input[type=checkbox]`（全选行），验证出现 `.rc-checkbox-checked`。
2. **确定**：活实例=rc-dialog-wrap 宽>0 且含「选择礼物」；按钮命中测试后真鼠标点（约 797,568，但必现测）。
3. 回到回礼弹窗，验 `适用礼物` 行 UL 内 = 全部礼物（粮票+看广告解锁）。解锁提示 input 的 placeholder 会自动变成「赠送『看广告解锁』等礼物即可解锁」=全选生效旁证。
4. **回礼弹窗确定**：所有 text=确定 的按钮里找 elementFromPoint 命中本体的那个真鼠标点（僵尸副本的确定在 z 下层，点了没反应）；**关不上就再点一次**（第5条硬规则），验 textarea 不可见。

## 第六步：发布前终验（一个 eval 查四样，全对才点发布）

```bash
agent-browser --cdp 9222 eval '(()=>{const m=document.querySelector(".lfc-modal");
  const title=m.querySelector("input[placeholder*=\"请输入标题\"]").value;
  const num=[...m.querySelectorAll("span,div")].filter(e=>e.children.length===0&&/^[0-9]+$/.test(e.textContent.trim())&&e.offsetParent).map(e=>e.textContent.trim());
  const repost=[...m.querySelectorAll("span")].find(e=>e.offsetParent&&e.textContent.trim()==="允许他人转载至LOFTER").parentElement.querySelector("svg").getAttribute("fill");
  const chips=[...m.querySelectorAll("div[role=button]")].filter(e=>e.offsetParent&&/^#/.test(e.textContent.trim())).length;
  return JSON.stringify({title,num,repost,chips});})()'
```

- title=书名 ✓ / num=main.txt 字符数 ✓ / **repost="none"（不勾选）** ✓ / chips=预期标签数 ✓
- 终验是唯一可信状态（各步的即时复验都可能读到僵尸实例/未重渲染的旧值）。

## 第七步：发布+验证

```bash
agent-browser --cdp 9222 console --clear
# 发布叶子：.lfc-modal 内 button 的子元素、children.length===0、text==="发布"，命中测试后真鼠标点
agent-browser --cdp 9222 mouse move <cx> <cy> && agent-browser --cdp 9222 mouse down && agent-browser --cdp 9222 mouse up && agent-browser --cdp 9222 wait 4000
agent-browser --cdp 9222 console 2>/dev/null | grep -oE '"isPublished":(true|false)|VALIDATION_FAILED' | sort | uniq -c
# 成功=isPublished":true；弹窗变成功视图后数秒内自动关闭（无需手动关）
```

## 坑位速查

- **焦点黑洞**：回礼 textarea 一旦聚焦，blur 后任何点击焦点都弹回它。解法只有按顺序（正文→标签→转载→回礼）+ 万一中招就关回礼弹窗重来。
- **inserttext vs fill**：主文档 input/textarea 用 fill（直接覆盖 value，React 受控也吃）；iframe 编辑器只能真点击+inserttext；对已聚焦的 textarea 用 inserttext=追加不是替换。
- **不用视觉模型**：一切判定走 DOM（svg fill、checkbox class、elementFromPoint、编辑器裸数字）。回礼弹窗的「确定没反应」八成是点到僵尸副本，命中测试解决。
- **联想下拉=漂移源**：打标签后下拉常驻会顶高弹窗；做完标签步骤后点一下空白处收起下拉再继续。
- **1500 字下限**：长篇合集那套的 VALIDATION_FAILED 规则在本弹窗未复现（4653 字发布过）；短于 1500 未测。
- 同一浏览器会话连发多篇：发布成功后弹窗自动关，回 dashboard 重新点「文字」开新弹窗即可；**上一篇没发布完绝不开下一篇的弹窗**（会顶掉未保存内容）。
