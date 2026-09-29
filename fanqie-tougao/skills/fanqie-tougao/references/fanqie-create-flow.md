# 番茄作家后台页面流程参考

> ⚠️ 观察记录（2026-09 编写，来源：番茄官方文档 fanqienovel.com/docs/8231/90699 与公开投稿攻略）。
> 番茄前端改版频繁，**此文档仅作导航起点，一切以现场页面实际元素为准**。找不到就重新观察，不要硬套。

## 入口与登录

1. 打开 https://fanqienovel.com → 顶部「作家专区」→「开始创作」，跳转到作家后台 **write.fanqienk.com**。
2. 登录方式：手机验证码 / 抖音扫码等。未登录时停下让用户手动登录；不要碰登录表单。

## 创建新书

路径：作家后台 → **作品管理** → 点「创建新书」（或 + 图标）→ 进入作品编辑页。
（2026-09-29 实测直链：`https://fanqienovel.com/main/writer/create?enter_from=book_manage`；表单域 class 为 `category-choose-section` 的是标签面板分组。）

表单字段（2026-09-29 实测）：

| 字段 | 约束 | 备注 |
|------|------|------|
| 书本名称 | ≤15 字 | **只允许中英文、数字及符号 ，：！？【】**，半角标点须转全角；签约前可改 |
| 签约模式 | 连载模式 / 完本模式 | 单选 |
| 目标读者 | 男频 / 女频 | 单选 |
| 阅读标签 | 主分类必选1个；主题/角色/情节各≤2 | 签约后不能修改；全量选项见 `fanqie-tags.md` |
| 内容标签 | 情节/人设各≤4；情感≤2；世界观≤1 | 全量选项见 `fanqie-tags.md` |
| 主角名 | 2 个输入框，各 ≤5 字 | 填男女主姓名 |
| 作品简介 | 50–500 字 | 低于 50 字不能提交；要**读者向书城文案**（钩子+卖点+悬念），不剧透结局/反转，不照贴剧情梗概 |
| 封面 | 图片上传 | 填书名后自动生成预览封面；可创建后再传自定义封面 |

注意：新版表单**没有独立的"分类"字段**——题材定位由阅读标签的主分类承担。填完确认再点「立即创建」，成功后回到作品管理能看到这本书。

## 封面上传流程（2026-09-29 实测）

1. 表单左侧「选择封面」按钮 → 弹窗两个页签：**本地上传 / 模板封面**。
2. 本地上传：隐藏 `input[type=file]`（accept=image/png,image/jpeg）在点开弹窗后才注入 DOM，用自动化上传命令对准它塞文件即可。
3. 规格校验：建议 600×800（2:3），jpg/png/jpeg，≤5MB。1024×1536 的 PNG 实测通过。
4. 上传完成后弹窗内出预览图 +「重新上传」按钮，「确定」激活，点确定应用回表单。
5. 封面来源：墨语平台的书用 `get_export_links` 返回的 `cover_url`（免登录签名直链，24h 有效）curl 下载后直接传。

## 标签面板交互 playbook（2026-09-29 双会话实测教训，照此执行）

标签面板是 React 组件，点击交互有明确的坑，按下面顺序做：

1. **打开弹层**：必须用真实鼠标事件（agent-browser 的 click 命令）点标签输入框；JS `el.click()` 打不开弹层。
2. **弃用 `@eXX` ref**：面板每点一下就重渲染，snapshot 拿的 ref 立刻失效（报 `Could not locate element`），还可能误点关闭面板。点芯片一律用 JS 按文本定位。
3. **点芯片的正确姿势**：按标签文本找**最内层** `.category-choose-item-title` 元素（同名多节点取最后一个），在其上派发完整指针事件序列 `pointerdown→mousedown→pointerup→mouseup→click`，事件带 `clientX/clientY`（从 `getBoundingClientRect()` 中心取）。**不要派发到外层 `.category-choose-item`**——实测只有部分分组留存（主分类/情节上了，主题/角色静默丢失）。
4. **一次只点一个，间隔 1~1.5 秒**：React 状态异步提交，连续批量点会丢标签；点完立刻查选中态拿到的也可能是旧状态（实测"当场查=未选中、1秒后查=已选中"）。节奏：点击 → sleep 1.2s → 验证该芯片选中态 → 丢了补点 → 下一个。
5. **每点一个验证一个**：验证方式=该芯片元素 class 出现选中态，或顶部已选芯片区出现对应文本芯片。
6. **面板没点「确认」就关闭 = 全部作废**：重开后从零重选。误关后先重新打开再继续，别假设之前点的还在。
7. 全部点完后，顶部已选芯片逐个与预期清单核对再点「确认」；确认后回读表单字段回显给用户。

### 稳健点选脚本模板

```js
async function pickTag(text) {
  const titles = [...document.querySelectorAll(".category-choose-item-title")]
    .filter(e => e.textContent.trim() === text);
  const el = titles[titles.length - 1];
  if (!el) return "not-found";
  const r = el.getBoundingClientRect();
  const x = r.x + r.width / 2, y = r.y + r.height / 2;
  const opts = { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window };
  for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
    el.dispatchEvent(new PointerEvent(type, opts));
    await new Promise(res => setTimeout(res, 60));
  }
  await new Promise(res => setTimeout(res, 1200));          // React 异步提交
  const done = [...document.querySelectorAll(".category-choose-item-title")]
    .some(e => e.textContent.trim() === text && /select|active|check/i.test(e.className + (e.parentElement?.className ?? "")));
  return done ? "selected" : "unverified";                   // unverified 也要补验，别跳过
}
// 逐个调用：await pickTag("古言脑洞"); 每个之间再额外 sleep；全部完成后顶部芯片核对 → 点确认
```

## 章节发布

路径：作品管理 → 进入该书 → **章节管理** → 新建章节。

- 字段：章节标题 + 正文（纯文本，段落用换行分隔）。
- 操作选项：存草稿 / 定时发布 / 直接发布。**默认只存草稿**。
- 平台侧：发布需通过审核，有敏感词检测；草稿发布由用户人工进行，所以敏感词风险天然后移，无需本地建词表。
- 长正文粘贴可能触发前端卡顿，必要时分段粘贴再核对首尾。

## 风控信号（出现即停）

- 验证码 / 安全验证弹窗
- 操作被拒绝、频繁报错、页面反复刷新
- 账号异常提示

一律停下，让用户手动处理后再继续。
