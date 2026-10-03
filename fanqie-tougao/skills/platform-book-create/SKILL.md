# Skill: platform-book-create
# 新书双平台创建（番茄 + 书旗）——从墨鱼项目到两平台书卡一条龙

把墨语系统里的项目建到番茄小说和书旗中文网的作家后台。**只做建书**（材料收集+填表+传封面），
不拆章、不发正文、不扫描——发章节走番茄发文助手扩展，扫描修库按需另起。

## 任务线（硬性顺序）

```
0. 前置：CDP 调试 Chrome 就绪（agent-browser --cdp 9222），
   node ~/.agents/skills/browser-cdp/scripts/setup-cdp-chrome.js 9222 --detect-only
   → ready 直接用；needs-setup 且 Chrome 在跑 = 先问用户（会杀进程）
1. 材料定稿：从墨鱼 MCP 拉项目信息，生成双平台材料单（下方「材料单」）
2. 番茄建书：填表 → 截图回显 → 用户点头 → 点「立即创建」→ 抓 bookId
3. 书旗建书：write.shuqi.com（登录卡住=用户手动登，绝不碰账号密码）
   → 填表 → 截图回显 → 用户点头 → 点「确认创建」
4. 收尾：两平台 bookId/链接 + 标签清单汇报；墨鱼侧 memory 记账
```

## 材料单（从墨鱼拉，三步拿全）

```bash
python3 /tmp/mcp_call.py get_project '{"project_id": N}'          # 书名/简介/题材
python3 /tmp/mcp_call.py query_character '{"project_id": N, "name": "X"}'  # 主角名核对
python3 /tmp/mcp_call.py get_export_links '{"project_id": N}'     # cover_url（签名直链）
URL=$(...grep -o '"cover_url": "[^"]*"' | cut -d'"' -f4)
curl -skL "$URL" -o ~/Desktop/<书名>_封面.png                      # 下载到本地，书旗上传用
```

- **简介必须读者向**：内部梗概含结局/反转/设计语的要改写（前两句人设+反差钩子，中段卖点，结尾悬念钩；
  不剧透结局）。用户已确认过的读者向文案原样用，不擅自改。
- **书名 ≤15 字**（番茄），半角标点转全角；两平台同一书名。
- **封面**：番茄创建可不传（自动按书名生成预览）；书旗建议传墨鱼封面（1024×1536 PNG 实测过）。
- 目标平台字段：建书前在墨鱼侧确认 `target_platform`（用户可手动改，别替他拍板）。

## 番茄建书（简版——详细 playbook 见 fanqie-tougao 技能）

1. CDP Chrome 打开 `https://fanqienovel.com/main/writer/create?enter_from=book_manage`
   （跳登录页=停下让用户登录）。
2. 填表（2026-10-03 P164 实测）：
   - 文本框用 **JS native setter + input/change 事件**（type 命令会叠字）。placeholder 对号：
     「请输入作品名称」「请输入主角名1/2」「50-500字」。
   - 单选：agent-browser click @ref 可用（连载模式/女频）。
   - 标签面板 playbook 照 fanqie-tougao 技能（真实点击开面板→芯片指针序列→逐个验证→点确认）。
     固定值库=其 references/fanqie-tags.md。
   - **「立即创建」按钮普通 click 不触发 React**——必须完整指针序列（见下方通用片段），点完看
     location.href 跳 `/main/writer/book-info/<bookId>` 即成功，bookId 从 URL 抓。
3. 番茄标签选型实例（古言围城 BE）：阅读=古风世情+虐恋情深+日久生情+女强+将军+虐文+双向奔赴；
   内容=绝症+保家卫国+异族入侵+群像+1v1+久别重逢+商女+孤儿；世界观留空（架空无对应）。
4. ⚠️ 番茄发文助手扩展运行期间**绝不碰番茄标签页**（不导航不注入不截图）。多标签操作先
   `agent-browser --cdp 9222 tab list` → `tab t<n>` 切换。

## 书旗建书（write.shuqi.com，全量 playbook）

入口 `https://write.shuqi.com/`（主站「作者专区」）→ 登录（手机号+密码，**用户手动**；调试
profile 账号=琼台故人，与番茄 yooyol 不同）→ 作者后台 /author → 建书表单
`/bookInfoCreate?category=1`。

### 字段填法（2026-10-03 P164 实测）

| 字段 | 填法 |
|---|---|
| 书籍名称 | native setter，placeholder=「请输入作品名称」 |
| 编辑代码 | **留空**（无编辑代码则无需填——P155 定案） |
| 目标读者 | radio 点「女生」 |
| 作品分类 | 级联：点输入框 → 古代言情 → **古典架空**（架空古言；穿越重生/经商种田/宫斗宅斗按书选） |
| 作品标签 | ant-select 弹层，**mousedown 触发**（click 不开）；选法见下方「书旗标签」 |
| 主角名 | 「添加角色」每次加一行，combobox 默认「男主」，第二行点开下拉切「女主」再填名 |
| 作品状态/征文 | 连载中（默认）/ 不参加（默认） |
| 作品简介 | native setter，textarea placeholder=「作品简介」 |
| 封面 | 点「本地上传」→ 隐藏 `input[type=file]` 注入 → `agent-browser upload "input[type=file]" <本地封面>` → 弹层「确定」 |
| 确认创建 | **用户点头后**再点 |

### 书旗标签（值库=references/shuqi-tags.md）

- 弹层结构：10 个分组 tab（主题-主线 / *主题-题材 / 角色男女主人设·职业 / *情节-主要剧情 /
  情节-背景年代 / 风格-文风 / 风格-情感感受）。**主题-题材、情节-主要剧情必填；总数 ≤20**。
- ⚠️ **书旗芯片单击即切换**——番茄式完整指针序列（pointerdown+click）会选中又取消来回跳！
  正确姿势：每组芯片**只发一次点击**，点完用「绿色内联样式」验证。
- **选中态标记 = 芯片内联 style 含 `rgb(35, 179, 131)`**（类名无选中修饰，别按 class 判）。
- **纠偏法（实测可靠）**：枚举全部绿色芯片 → 与计划集 diff → 绿了不该绿的再点取消、该绿没绿的
  补点 → 重读绿色集核对。同名词跨组（厨师/医生/将军等男女职业重复）按元素逐个处理。
- 选型实例（古言围城 BE，16/20）：主线=权谋；题材=古言；男主=冷酷+美强惨+将军；女主=厨师+
  女强+大女主；情节=双向奔赴+BE+1V1+日久生情；背景=架空；文风=正剧；情感=虐恋+温馨。

## 通用代码片段（两平台通吃，agent-browser eval 硬约束）

**agent-browser eval 只吃表达式**——多语句必须包 `(async () => { ... })()` 且走 base64：
```bash
cat > /tmp/x.js <<'EOF' (async () => { ... return "..."; })() EOF
agent-browser --cdp 9222 eval -b "$(base64 < /tmp/x.js)"
```

**React 受控组件/按钮统一武器**——native setter + 完整指针序列：
```js
function setVal(el, v) {  // input/textarea 通吃
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
  el.dispatchEvent(new Event('input', { bubbles: true }));
}
async function fire(el) {  // 按钮/芯片/单选通用：普通 click 对 React 无效时的解
  const r = el.getBoundingClientRect();
  const o = { bubbles: true, cancelable: true, clientX: r.x + r.width/2, clientY: r.y + r.height/2, view: window };
  for (const t of ["pointerdown","mousedown","pointerup","mouseup","click"]) {
    el.dispatchEvent(new PointerEvent(t, o));
    await new Promise(res => setTimeout(res, 50));
  }
}
```
⚠️ 例外即书旗标签芯片（见上）：单击切换，fire 全序列=双切换。新组件先试单击，观察是否双切，
再决定用单击还是全序列。

## 已知坑（全部实测踩过）

| 坑 | 解法 |
|---|---|
| IAB 内置浏览器无登录态、无文件上传能力 | 建书一律走 CDP 调试 Chrome（9222） |
| agent-browser eval 报 SyntaxError | 只吃表达式：IIFE 包裹 + base64（-b） |
| 番茄「立即创建」点了没反应 | 普通 click 不触发 React，用 fire() 全序列 |
| 书旗标签芯片选中又取消循环 | 全序列=双切换；单击+绿色样式验证+diff 纠偏 |
| 番茄/书旗同名词标签跨面板 | 词放读者搜索用的面板，另一面板腾位（番茄 P150 教训） |
| 番茄每日创建上限 | 次日重放即建（0929 实录），材料存档别重配 |
| 扩展发章节运行中 | 不碰番茄标签页；完成后按「已发记录」口径汇报 |
| 验证码/风控弹窗 | 立刻停，交用户手动 |

## 收尾

- 番茄：bookId（URL 抓）+ 书卡链接；书旗：创建成功页/作品管理可见。
- 墨鱼侧：project 记账（bookId、两平台标签、封面文件路径）写进 memory。
- 待办提醒：番茄封面默认是书名预览图，要换自定义封面走后台「选择封面」。
