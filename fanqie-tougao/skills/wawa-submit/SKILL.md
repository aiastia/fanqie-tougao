# Skill: wawa-submit
# 蛙蛙写作投稿技能（脚本化流水线版）

把小说批量投稿到 wawawriter.com 投稿中心。**2026-09-02 起走 prepare_batch.py 脚本流水线**：
固定数据全部固化、下载/体检/封包全部脚本处理，浏览器只剩按序执行预生成的注入代码。
**6 本书全程 ≈15 次浏览器调用**（20260902 实测从旧版 70+ 次降下来）。

## 快速流程

```
新投稿：
1. python3 prepare_batch.py list                    # 线上挑书（ID/字数/已投状态一屏）
2. 写 batch.json（简介必须用户过目确认后才填入）      # 见下文格式
3. python3 prepare_batch.py prep batch.json -o /tmp/wawa_batch
   → evals.json + report.md（体检在这做，⚠️项先解决再投）
4. 浏览器打开 wawawriter.com/app/ → 按序执行 evals.json（模板见「浏览器执行段」）
5. 全部 reviewing → 投后回执（record_submission MCP 或用户手动）

签约书更新章节（0903 下午起同样脚本化，详见「已签约作品更新章节」节）：
A. 浏览器 dump mylist.json（页内 POST my_list，一条固定 eval）
B. python3 prepare_batch.py updates_list -m mylist.json [-o updates.json]   # 盘点可推
C. python3 prepare_batch.py updates_prep updates.json -o /tmp/wawa_batch    # 下载+补丁+体检+产evals
D. 浏览器按序执行 evals（precheck→逐本 update_submit→verify），全程 ≈每本 1 条
```

## 定论（实测过，勿再试/再拉）

- **CORS**：页内 fetch 跨源拉墨鱼签名直链必被拦。不要试，数据一律走 base64 注入。
- **标签**：一律查本目录 `labels.json`（158 系统标签 + 自定义，20260902 固化；系统标签
  ObjectId 是平台级稳定数据）。脚本自动转 id。页内新建自定义标签：
  `POST /wrhp-api/api/v1/label/ {name, category:"custom"}`（缺 category 报 422），
  建完把 id 塞 label_ids 即可。已建：志怪=`6a930e1ee33e2c1caad4e29b`、民俗=`6a967bce9dd80ec6d642fff1`、
  出马仙=`6a967bcfae02c7c79bc25409`、后宫=`6a97e45d4620f5c7223e9bf0`、女扮男装=`6a97e45d477c66e65ea230bb`。
  刷新 labels.json（平台加了新标签时）：页内 `POST /label/list {page:1,page_size:9999,scope:"system"}`
  + `GET /submission/custom_labels?limit=2000`，落盘成 `{system:{名:{id,cat}},custom:{名:id}}`。
- **evaluate 只吃表达式**：裸语句串报 `Unexpected token ';'`，一律包 IIFE `(() => {...})()`。
  顶层带 `return` 的调用会「无输出」但**实际执行完了**——先查状态再决定重跑。
  **0922 新坑：分块注入的 250KB 单块也会间歇 `Unexpected token ';'`**（121 书 251KB 首块必死，
  小书 22-158KB 同日全过）——治法用 0921 的本地 HTTP 绕行：js 调用内起 `http.createServer`
  （127.0.0.1:8899，`Access-Control-Allow-Origin: *`），eval 里 b64 行替换为
  `const b64 = await (await fetch("http://127.0.0.1:8899/e0")).text();`（长度校验模板自带），
  evaluate 只传 ~1KB 壳。0922 四本大书 251-415KB 全绿。⚠️ kernel 不跨调用，server 须与
  evaluate 同一 js 调用内起停；try/finally 收尾时返回值会「无输出」，先查 my_list 章数再决定重跑。
- **单条 evaluate 代码容量：>250KB 一律分块注入**（`window.__pushB64` 法，见
  「20260907 批」节；旧口径「单条 ≥300KB 可靠」已废，脚本产出的每条控制在 ≤220KB）。
- md5 在 bash/脚本侧算 hex 传入（file_secret），页内不用实现 md5。
- **my_list 必须 POST {}**：GET 带不带参数都 422「submission_id 异常」。
- parse_file 不用：它会把正文行首「第X节」误切章。脚本用页内同款切法（只认 `^第\d+章`）直传 chapters。
- 平台计字比墨鱼少约 5%（46314→44019 / 51424→48506 / 44101→41905 三批一致）。
- **建稿响应丢失 ≠ 失败**：大 payload 时 evaluate 可能吞响应，但服务端已完整落库
  （draft 存在 = 完整 JSON 已被处理，章节已存）。草稿态 0 章 / 0 字是**正常态**
  （章节在 submit 时才挂上并回传字数）。正确处理：POST my_list 按 title 找
  draft 拿 submission_id 直接 submit；**勿重建（会重名双稿）**。
- **投稿后改不了**：reviewing 状态调 `PUT /submission/novel/{id}` 被拒「当前状态不允许修改」。
- IAB 登录态持久；会话释放后重开 `wawawriter.com/app/` 即恢复（DOM 右上角出现
  `Hi，<昵称>` 即登录态；**0921 终局：投稿流水线禁止默认笔名——唯一真相源=墨鱼侧项目
  pen_name 字段，prepare_batch prep 自动逐本拉取对账，batch.json 顶层字段废弃、书级字段
  仅作核对（不一致停线）；永久弃用=yooyol / 在在暴打暖暖小拉在旁边劝架 /
  无聊大师**，脚本 precheck 按历史昵称双兼容）。
- 站点渲染滞后/点击超时等 UI 坑只影响 UI 路线；本流水线全走 API，不碰表单。

## 浏览器执行段

control-browser 打开 `https://wawawriter.com/app/`，取 tab 后按 evals.json 顺序执行
（每个 js 调用串 2~4 条 eval，timeout_ms 给 120000）：

```js
const evals = JSON.parse(fs.readFileSync("/tmp/wawa_batch/evals.json", "utf8"));
// 先单独跑 precheck（决策点），再循环书
const r = await tab.playwright.evaluate(evals[0].code);
// r.loggedIn=false → 走登录流程; r.existing 非空 → 停！同名 draft/reviewing 已存在，人工判断
// 之后逐条: cover 返回 {code,url}; create_submit 返回 {create:{sid}, submit:{status,words,chapters}}
```

分支处理：

| 情况 | 处理 |
|---|---|
| precheck 未登录 | 用户自输密码登录（见下），登录后重跑 precheck |
| precheck 有同名 existing | 停。draft=补 submit；reviewing=本书已投过，从 evals 剔除 |
| cover 无 url | 直接重跑该条（同 md5 幂等，COS 同名覆盖） |
| create_submit 吞响应/超时 | POST my_list 查该 title：有 reviewing=成了；有 draft=拿 sid 补 submit；都没有=重跑本条 |
| create 报章数不符/短章 | 数据问题，回 report.md 排查，勿带病硬投 |

收尾验证（一条 eval）：POST my_list → 过滤本批 title → 六个全 `reviewing` 且字数合理即收工。

## batch.json 格式与脚本产线

```json
{
  # ⚠️ 笔名不要填（0921事故后删除本字段）：唯一真相源=墨鱼侧项目 pen_name，
  # prep 自动逐本拉取；书级若填只作核对，与墨鱼侧不一致直接停线
  "campaign": {"entry_type": "campaign", "campaign_code": "xxx"},
  "books": [
    {"project_id": 41,
     "intro": "……用户确认过的定稿简介……",
     "channel": "女频",
     "cate": ["女频", "浪漫青春", "青春校园"],
     "labels": ["言情", "打脸", "黑莲花", "现代"]}
  ]
}
```

- `labels` 传**名称**，脚本查 labels.json 转 id（系统+自定义通吃，缺名会报错并列出）。
- `campaign` 仅征文投稿填；普通投稿删掉。
- 脚本做完全部固定处理：MCP get_export_links → curl 下载 txt+封面（带重试）→
  sips 转 jpg(q75, 1024) → md5 → base64 → 体检 → 生成每条 eval 代码。
- 体检项：切章数与平台 links 对账、<200 字短章、中文数字章头、泄漏扫描
  （提纲/大纲/梗概/本章目标/剧情点/写作要求/字数要求/爽点/`要求：`/`基调：`；
  「形制」在民俗古物文正文是正常用词，不放正文扫描）。
- 产物：`evals.json`（1 条 precheck + 每本书 2 条）+ `report.md` + `work/` 原料。
  每本书固定 2 条：`cover`（上传+URL 存 `window.__covURL{pid}`）、`create_submit`
  （解正文→切章→校验→建稿→提交，一气呵成）。

## 简介铁律（用户拍板，不可跳）

1. **系统的（墨鱼）简介不等于成品**——提取后必须润色成纯读者向文案：删掉
   「基调：…」「单元形制」「暧昧要求：…」等内部设计语言尾巴（41 就带了一整段
   生成指令泄漏被拦下重写）。
2. **投稿前把定稿简介给用户过目确认**，确认后才能填进 batch.json。
3. 投稿后改不了，没有后悔药。

## 分类速查（历史用过的三级路径）

| 书 | 路径 |
|---|---|
| 民俗灵异(男) | 男频 / 悬疑小说 / 灵异奇谈 |
| 悬疑灵异(女) | 女频 / 悬疑小说 / 悬疑灵异 |
| 末世经营(女,无CP) | 女频 / 科幻空间 / 末世危机 |
| 后宫团宠(男) | 男频 / 玄幻奇幻 / 东方玄幻 |
| 校园财斗(女) | 女频 / 浪漫青春 / 青春校园 |
| 娱乐圈恶女(女) | 女频 / 都市言情 / 娱乐明星 |
| 朝堂权谋(女) | 女频 / 古装言情 / 权谋天下 |
| 情感短篇 | 女频 / 情感小说 / {婚恋情感|婆媳关系} |

标签一类别限一（题材/情节/情绪/角色/时空各一）+ 自定义若干。
整棵分类树在前端 chunk（无接口，备用抓法）：`/app/` HTML → `index.*.js` 里 grep
`CreateSubmission.*\.js` → fetch 该 chunk 搜「女频」。

## 登录（仅 precheck 报未登录时）

首页右上角「登录」→ 点「密码登录」→ 手机号+密码（**用户自输，AI 不碰**）→
勾「我已阅读并同意」→「登录」。成功标志：右上角 `Hi，<昵称>`（历史昵称 yooyol /
不关夜灯的小水母，两者都算登录态；笔名选择纪律见上方 0920 条）。
投稿中心的弹窗三连（投稿提示/征文/绿色通道）只影响 UI 路线，API 路线无视。

## 原料下载（脚本内部实现，备用手动法）

`mcp__moyuonlin__get_export_links(project_id)` 返回整书 TXT + 封面的免登录签名直链
（24h 有效）：`curl -L -o 书名.txt "<txt_url>"`（只支持 GET，HEAD 会 405）。
txt 格式=「第N章 标题\n\n正文」，空壳章自动跳过。
备用：IAB 开 mybook.124678.xyz → localStorage `moyu_token` → Bearer 调
`/api/projects/{id}/export?format=txt` 与 `/api/projects/{id}/cover/image`。

## API 速查（边缘场景）

```
POST /wrhp-api/api/v1/submission/novel/create_from_file   # 建稿(不提交)；body见脚本payload
POST /wrhp-api/api/v1/submission/novel/{id}/submit        # 真正投稿，回执含 status/total_word_count
POST /wrhp-api/api/v1/submission/novel/my_list {}         # 全量投稿列表(注意POST,含base_novel_id)
POST /wrhp-api/api/v1/file/simpleupload                   # 封面≤5M；>8M走chunkupload三段
GET  /submission/novel/{id}                               # 草稿详情
GET  /submission/campaigns/active                         # 征文(普通投稿不用查)
GET  /label/category                                      # 标签类别mode
PUT  /submission/novel/{id}                               # 改稿(仅draft/rejected可改)
GET  /wrhp-api/api/v1/novel/{base_novel_id}/chapter/{node_id}   # 章节详情: text正文/name/word_count
PUT  /wrhp-api/api/v1/novel/{base_novel_id}/chapter/{node_id}   # 章节编辑:{text}/{name}任传,200即落库
                                                            # **已提交/已上线章节也能改**(20260907
                                                            # 实测修 P34 第61章拼接坏章+P39 21处双前缀
                                                            # 章名)——平台侧修正不需求删重导
```

## 已签约作品更新章节（20260903 批量 62 章实测，含接口版本修正）

语义（用户拍板）：**只传本次新章**，不用重传已投稿章节。签约后作品是站内作品，
`POST /submission/update/create_file`（文件路线）会报 **「站内作品不支持文件更新」**。

### 范围规则（20260905 用户拍板，updates_list 已内置）

- **墨鱼已归档书不查不推**：updates_list 默认 `--archived false`，调
  `list_projects(archived=false)`（未部署前靠条目级兜底：archived 字段或
  status=='archived'——归档与连载共用 status 列），归档书连 get_export_links 都不调。
  例外开关：要盘蛙蛙在架的归档书（0914 全池体检批 P22/P23/P36 那类）传
  `--archived all`（全池都盘）或 `--archived true`（只盘归档）。
- **蛙蛙已完结书不处理**：mylist.json dump 必带 is_finished 字段，updates_list
  见 is_finished=true 直接跳过（打印提示，不进表格不进草稿）。

### 脚本产线（默认走这条，0903 下午批 10 本 43 章 + 48 追推已实战验证）

**MCP 口径**：墨鱼侧三步（清单/有效章数/范围导出）全有现成 MCP 工具
（`list_projects` / `list_outlines` / `get_export_links`），**不需要新增 MCP**；
会话里没挂 MCP 工具也**不要抓浏览器 token 走 REST**（本机 curl 连 mybook 会被
CF 掐断）——prepare_batch.py 自带 `mcp_call()` 直连（key 读 config.json 的
`mcp.servers.moyuonlin`）。蛙蛙侧登录态只在浏览器里，MCP 化既不可能也没必要，
保持 eval 注入。**墨鱼侧永远走脚本，浏览器只碰 wawawriter 域。**

```
A. 浏览器（wawawriter.com/app/）dump 蛙蛙侧：
   (async () => { const j = await fetch("/wrhp-api/api/v1/submission/novel/my_list",
     {method:"POST", credentials:"include", headers:{"Content-Type":"application/json"}, body:"{}"}).then(x=>x.json());
     const arr = (j.data&&(j.data.items||j.data.list)) || (Array.isArray(j.data)?j.data:[]);
     return arr.map(x=>({sid:x.submission_id, title:x.title, status:x.status,
       chapters:(x.submitted_chapter_ids||[]).length, words:x.total_word_count,
       base_novel_id:x.base_novel_id, is_finished:x.is_finished,
       finish_status:x.finish_status})); })()
   → 结果存 mylist.json（is_finished/finish_status 必带：updates_list 靠它跳过
     蛙蛙已完结的书——20260905 用户拍板已完结不处理）
   → 结果存 mylist.json（这份数据顺带就是平台侧状态源：status=contracted/reviewing、
     contract_status、is_finished+finish_status完结审核流、meituan_shelf_status上架状态、
     meituan_latest_online_chapter_id最新上线章、update_time最近过审更新时间——
     「是否太监」没有专门字段，= update_time 距今天数；配合墨鱼侧
     list_projects.status(active/paused/abandoned) 一拼即完整状态）
B. python3 prepare_batch.py updates_list -m mylist.json -o updates.json [--pid 37,38] [--archived false|true|all]
   → 墨鱼有效章数 vs 蛙蛙已推，一屏可推数；-o 直接写 updates.json 草稿
   （updates.json 每本={project_id, submission_id, base_novel_id, wawa_chapters}；
   --archived 默认 false=只盘未归档，盘在架归档书传 all）
C. python3 prepare_batch.py updates_prep updates.json -o /tmp/wawa_batch
   → 脚本做完全部固定处理：MCP get_export_links(from_chapter=已推+1) 签名直链下载
     → 尾随半成品章(<200字)自动截掉留下批 → 正文补丁(切章器坑见下)
     → 泄漏体检+章数/章号守卫 → 产 evals.json（precheck + 每本 1 条 + verify）+ report.md
D. 浏览器按序执行 evals；precheck drift=true / 某本报 parse_mismatch、pending_mismatch
   即停人工看。verify 全 ok 才收工。
```

### 手工四步（边缘场景备用）

```
1. GET  /wrhp-api/api/v2/novel/{base_novel_id}/structure
   → volumes[].chapters[]，字段 node_id/name/is_locked/is_submitted
   （注意：卷 id 字段=volume_id 非 id，章标题=name 非 title；chapters 按 index
   倒序排列——第 1 章在数组尾部，slice(-3) 看到的是开头章别误判！
   已提交章 locked 不恒为 true（37 全部 locked=false）——识别新章用
   is_submitted=false 或 import 前后 node_id/章数差集，别信 locked）
2. POST /wrhp-api/api/v2/novel/parse_chapters  body:{text}
   → 服务端切章返回 chapters[]（勿自己切，用它的输出）
3. POST /wrhp-api/api/{v1|v2}/novel/{base_novel_id}/import_chapters
   body:{chapters, volume_id:structure里的volume_id}
   ⚠️ 版本因书而异（20260903 实测推翻"必须v2"旧结论）：37(0831老稿)只有 v1 落章，
   38/39/40/44/45 只有 v2 落章；不兼容版本返回 200+作品回显=纯空操作（无污染）。
   实操：先 v2 → 重拉 structure 查章数，没涨再试 v1，章数变化判真伪。
4. POST /wrhp-api/api/v1/submission/update/submit_chapters
   body:{submission_id, chapter_ids:[import后重拉structure里 is_submitted=false 的 node_id]}
   → 回执 {success_count, failed_count, created_update_ids}，进平台「更新审核」
```

新章范围：墨鱼 `get_export_links(project_id, from_chapter=签约章数+1)` 导出；
**to_chapter 别传 0**（会变成空范围），传 99 即可；返回的 `chapters` 字段是全书
有效章数（非范围数），待推数=全书有效章−平台已提交章（my_list 的
submitted_chapter_ids.length）。**平台投稿页面 UI 本身就展示「章节：N章/总字数：
X.XX万字/状态：已签约」——核对状态与章数直接看页面即可，不必拉 API；章节倒序
排列（页面看到 3、2、1）是平台一贯设计，structure API 同款倒序，不是异常**。
导出为空 = 那些章是空壳大纲（list_projects 的
chapter_count 含空壳，虚高，勿当可推新章）。
更新审核记录在管理端 `/submission/update`（UpdateReview 页）。
**未签约（reviewing）作品不能推更新**（20260906 P49 实录）：submit_chapters 400
「只有签约成功的作品才能更新连载」——且 import 已落 structure（is_submitted=false
11 章挂在那里），**签约过审后只补 submit 现有 !submitted 节点，勿重跑整条 import
（章节会翻倍）**。P46 第49章 306 字断头残章（「封」字悬空）夹在满章之间=中段半成品，
尾随截断守卫管不到，整本押后留下一批（41 第17章先例）。各批实测回执见记忆总账
（0903 批量六本 62 章 0 失败起逐批全绿；旧手动逐本流程模板已废，现走 updates_prep）。

### 切章器规则与正文补丁（20260903 下午批 10 本 43 章实测；补丁已内置 updates_prep）

平台 parse_chapters 的隐藏切章规则（合成样本探测+实战坐实）：

- **行首** `第[中文数字]+回` 会切（47 第15章正文一行「第三回笔尖悬在格子上头，没落下去。」
  被当成章头，切成 7 章、该章尾巴 1929 字挂成垃圾章）；**行首裸中文数字「X回了/X回，」
  无「第」字也切**（20260906 P34 第46章实录：「三回了。她不问了。」整行行首，被切成
  假章头 11≠10 被 import 前守卫拦下；FAKE_HEAD_RE 要求「第」开头抓不到它）；行中/句号后
  **不切**，「第二节」「第3回」行中也不切。`【第41章】日子排上了` 这类**括号章头**行首也切
  （23 第42章开头混进的前情提要标签）。手动修补这类漏网形态：直接改 evals.json 该条 code
  里的 b64（解码→并入上一非空行→断言→重编码替换；**原料 work/*.txt 不含补丁，补丁只进
  b64**，勿按原料改完再重跑 prep——会重新下载覆盖且补丁规则不含此形态）。
- 补丁手法（**只动换行位置不动文字**）：散文式假章头行→并入前面最近的**非空**行
  （⚠️ 合并到空行=白合并，位置不变照样切）；括号元数据标签（【第X章】…前情提要类）
  →整行删除（读者向排版，非正文叙述）；「第N章完。」完章标记独占一行（20260906 P44
  第35章尾实录，模型写进正文的元数据）→整行删，且 split_chapters 不把它当章头
  （END_MARK_RE 要求「完」后只剩标点/行尾，防误删「第35章 完结篇」这类真章头；
  阿拉伯数字版会撞 `^第\d+章` 守卫多算一章=22≠21 跳书，中文数字版落 FAKE_HEAD 并入；
  20260917 P94 ch9 实录 «第9章完» 书名号/引号包裹变体，END_MARK_RE 已扩包裹标点
  且修库清除后重 prep）。
  补丁后断言：无残留行首假章头。
- **早期守卫（必加）**：parse 后先核对 `chapters.length===预期` 且每章标题匹配
  预期章号，不匹配**不导入**直接返回诊断（47 第一版守卫放在 import 后，
  垃圾章已进草稿；23 早期守卫在 import 前拦下，草稿零污染）。
- 意外导入的垃圾章清除：`DELETE /wrhp-api/api/v1/novel/{novel_id}/chapter/{node_id}`
  （前端章节编辑器同款接口，签约作品未提交章可用，200 回执**带该章全文**）。
  47 实录：删 7 残片→补丁→重导 6 章→submit 6/0。

### 20260907 批 10 本 291 章：pre_patch_text 切章前预清理 + 大书分块注入

- **to_chapter 上限 99 已升 999**（prepare_batch.py）：书过百章后 49→99 截尾，
  31/40 被「导出少 N 章」误报；对账守卫会拦（章数对不上跳书），改 999 后 568KB 单本全量过。
- **pre_patch_text（已内置，split_chapters 之前跑）**治「本地切章多算一章」——真章头
  =「第N章 标题」（章号后有空白），以下无空白紧跟的行全是模型写进正文的元数据：
  「第76章完。全章约2750字…」阿拉伯数字完章标记+写作说明长段（P39）；「第61章《标题》」
  章尾书名号重复标签（P34）；「第51章预告已触发：…」「第56章预告：（略）」（P36/P40）；
  「第70章那夜她把银根…」章号后直接接叙述句（P37）→并入上一非空行；
  「</thinking>」思考链闭合标签行（P34 唯一一处）、「本章完成了大纲承诺…」/
  「写作说明（供参考，非正文）：…」整段写作说明（P22 第54章尾两行）→整行删。
- **平台侧另两种行首切法**（本地切章看不见，靠 parse_mismatch 守卫拦下再补规则）：
  行首裸中文数字「一回是巧，…」（P38，接续 20260906 P34「三回了。」形态）与
  行首裸阿拉伯数字「104章那本账还摊在…」（P31，无「第」字）——均已入
  BARE_CN_HUI_RE/BARE_AR_CH_RE 并入上一非空行。撞守卫后处理法：改 pre_patch_text
  加规则→写单本 updates.json 子集→重跑 prep 到新目录→重推（守卫在 import 前，零污染可安全重试）。
- **大书 eval 分块注入**（>250KB 一律分块，技能旧口径「单条 ≥300KB」不再靠）：
  从 evals.json 该条 code 里正则抽出 b64 字面量→替换 `const b64 = window.__pushB64;`
  →`window.__pushB64 = "块0"` / `+= "块n"`（每块 250KB，返回累计长度自证）→
  主体代码 evaluate（timeoutMs 100000）→delete 清理。568KB/三块实测过。
  evaluate 第二参传 undefined、第三参 {timeoutMs}；js 调用 timeout_ms 120000（上限）。

### 20260912 批 6 本 160 章：章尾泄漏块大扩表（23 行实录）+ pre_cleanup 可见化

- **prep 报 ✓ ≠ 干净**：LEAK_RE 词表只拦住 6 本中 2 本（爽点/大纲命中），其余 21 行
  元数据全靠人工全词扫描补获。推前务必对 work/*.txt 独立扫一轮：
  `本章完|关键词|应答|供参考|改进|完成度|/10|system_|正文完|正文收在|伏笔|钩子|约[0-9]*字`，
  命中逐行人工分类（「严丝合缝」是这批书文风词、钩子多为鱼钩/秤钩比喻，勿误杀）。
- 章尾/章中元数据新形态 8 族（全部已入 WRITER_NOTE_RE，整行删）：
  ①「（本章完）」三变体（（本章完）/（本章完，约3000字）/（本章完约3050字））
  ②「关键词：#话题标签」行（P22）
  ③「（应答说明：本章约2900字，完成…伏笔的major级兑现…））」（P22，注意双括号尾巴）
  ④「补充说明一句，供参考：正文约二千九百字…」（P22，中文数字躲过 约\d+字 类正则）
  ⑤「（当然了，本书的规矩：爽点从来写在旁人身上，X自己只管站着。）」第四面墙吐槽（P37）
  ⑥ AI 自评块 6 行（P37）：引言「本章是本卷…实际完成度合格：」+ 评分行
  「兑现层面（9.0/10）：/信息控制（8.5/10）：/角色（8.5/10）：/章末（8.5/10）：」+
  「改进建议：…推荐发布。」
  ⑦「正文收在钩子处：…」「正文完，约3100字。本章兑现了大纲承诺的…」（P38/P80 章尾写作注）
  ⑧`<system_warning>output token limit approaching</system_warning>` + 场景标签行
  「胖大姐百货店：」+ 其后创作分析行（含「因上一章的事做出的反应」）（P80 ch16 尾，三行一体）
- **pre_patch_text 删除行可见化**：删除行全量记 `PREPATCH_REMOVED`，updates_prep 按
  书取增量报进 report.md「预清理删除: N行（如 …）」，防静默删除。
- LEAK_RE 纵深词补：`应答说明|供参考|改进建议|完成度合格|system_warning|关键词[:：]|\d+\.\d+/10）`。
- 教训：模型泄漏形态每批都在换皮，词表永远是追赶方——**人工扫描是必要工序不是冗余**。

### 20260916 批 16 本 520 章：更新批新泄漏形态 9 处（当日修库全净）

- **当日主线**：0916 全池连写批（24 本在队）中途先推已完成的 16 本签约书 520 章零失败；
  P97/98/99（0916 晨投 12 章组）已过审 contracted 可推更新；**蛙蛙已完结书（is_finished=true
  15 本）按拍板跳过**。P65 未推：蛙蛙 sid17818 是用户手写版自投（书名还少个「我」字），
  与系统版不同源，标题匹配不上属幸事，**勿把它跟系统版接上**，待用户拍板。
- 新泄漏形态 9 处（全部当日 update_chapter 修库+回读断言，词表已入 WRITER_NOTE_RE/LEAK_RE）：
  ①「以上为生成的第135章正文。」（P38 ch135 尾）
  ②「注：按规则不应输出完章标记与字数说明，改正如下——…」（P39 ch130 尾，模型自我纠正注）
  ③「【本章伏笔登记·仅供系统核对，不属正文】+回收：/埋入：/说明：\d{4,}」三行块（P39 ch126 尾）
  ④「第四章\n5\n\n<!--…占位符，请忽略。本章到此收束。-->」垃圾尾块（P80 ch54 尾；锚后截断法，
     断言锚后只剩垃圾再切）
  ⑤自评六行块「本章核心变化兑现：/伏笔回收（/承接上章：/收束功能：/声纹自查：/字数：约…」（P89 ch35 尾）
  ⑥「自查：字数约2100，偏短。需扩到约3000。…以下为修订后全文。」（P88 ch42 尾）——**「以下为
     修订后全文」是空头承诺，正文完整自然收尾，删行即可，勿当双版拼接拆**
  ⑦ 行首裸中文数字+章「一章是谁后来补盖的，没人知道。」（P87 ch39，新切章形态，已入
     BARE_CN_CH_RE 并入上一非空行；当日走修库段落合并）
  ⑧ 叠字错版顺手修：「这这一家人」（P39 ch126）「这话这话」（P89 ch36）
- 教训重申：prep ✓ ≠ 干净——当日 prep 只拦 4 本，人工全词扫 work/*.txt 又抓出 P88 ch42 一处，
  **两道工序一个都不能省**。推送中途连写队列还在写：P39 175→178、P80 76→78、P88 60→61 章
  期间自然增长，prep 以下载时点为准、守卫兜底，后续批再推增量即可。

### 20260923 批 15 本 264 章：泄漏形态再换皮 4 处 + 大书 HTTP 绕行全量落地

- 当日主线：0922 连写批 29 本写完后首推增量。15 本签约书 264 章零失败（P112 28/P114 24/P116 24/
  P113 22/P115 22/P117 22/P132 22/P118 21/P128 13/P94 6/P119/P120/P123/P124/P129 各 12），
  P65（用户手写自投版不同源勿接）与未投稿的 P127/131/133 自然无匹配；推送中途 P112/113/114/133
  仍在连写（prep 以下载时点为准，P112/P114 尾章恰逢写完润色毕一并推净）。
- 泄漏形态 4 处（当日修库 5 章全回读验证，词表均已入 WRITER_NOTE_RE）：
  ①「（本段正文约3050字，年代文壳「嗯」为主，…均已落位。）」风格自注（P112 ch16，行首带
     （ 逃过 ^锚定词表 → 新增 [（(]本段正文约\d+字）
  ②英文系统提示整句混入正文「Missing assistant reply in the final output turn. Please
     regenerate…(Output the chapter content only, no meta-commentary.)初五还有两日。…」
     （P115 ch15，英文与中文同行——修库法=同行内只删英文段保中文，整行删会伤正文）
  ③「【正文中不得出现任何创作元信息（如：自查结果、字数统计、…）——上述内容已在内部完成，
     此处仅输出正文本身。】」指令块泄漏（P116 ch16）+ 同书 ch13 生成脚手架两行
     「是娘的笔迹。原句：…一母同胞␤下文：。。」——修法=并回自然散文「是娘的笔迹。是祭坛…」
     （「原句：」「下文：。。」是续写框架残迹，不是真引用）
  ④办公软件追踪串三连尾（P94 ch98）：正文末句粘「};」+「_support_cite~754d61…^default^…」
     整行 +「用户消息包含」截断行——修库法=锚定正文末句「见客。」截断其全部尾部
- 人工扫描新增判读：P119「止住神应答的手势」=剧情用词误报放行（「应答」在灵异文是正常动词）；
  P112「清查组管念提纲」=审问剧情误报放行（allow_leak 书级字段）。
- **>250KB 大书本地 HTTP 绕行全量落地**（0922 四本后本批再证三本 251/256/295KB 一次过）：
  js 调用内起 http.createServer(127.0.0.1:8899, ACAO *)，eval 的 `const b64 = "…"` 字面量
  正则替换为 `const b64 = await (await fetch("http://127.0.0.1:8899/e0")).text()` + 长度断言，
  evaluate 只传 ~1KB 壳（仍须 esc() 全量转义）；server 与 evaluate 同一 js 调用内起停，
  **勿用顶层 return 控制流**（无输出坑：本批 P94 推完但回执被吞，靠 my_list 复查判真）。
- 流程小改进：被拦书单本重备（updates 子集 + 独立 -o 目录）不打扰已打包的好书，四批
  （主批 10 本/batch2/batch3/batch4）各自 precheck→推送→verify 串行执行，verify 里
  已挪批的书报 false 属预期。

### 20260923晚 批 18 本 292 章：新泄漏形态 5 族 + 导出 CDN 缓存旧响应坑

- 当日第二推（对账 18 本可推 222 章，推送窗口内连写仍在写，112/115/122/126/132 实际推更多，
  P112 两批间自然长 8 章一并推净）。18 本 292 章零失败：批次一 17 本 202 章 + 批次二（重备）
  5 本 66 章 + 批次三 P122 24 章。P127 当天新投 sidXXXXXX（reviewing，66 章整投，不能推更新）；
  P131/133 仍未投稿。
- 新泄漏形态 5 族（修库 10 章全回读验证，词表已入 WRITER_NOTE_RE）：
  ①「（正文约3000字）」简版字数自注独占章尾行（P112 ch46/47、P115 ch36——旧表只有
     「正文完，约N字」带「完」版，简版漏接）
  ②残留标签「</s>」（P118 ch34）与「</content>」+ 尾随假人味声明「良心写作，无任何AI辅助，
     纯人脑输出（有时候会用纸笔打草稿）」两行连删（P132 ch49）
  ③生成系统提示回显「（系统提示：本次章节生成已附加作者记忆规则…）」「（系统提示：本段正文
     已按【正文纯净铁律】输出单遍…）」（P132 ch34/35/38——系统流题材加词前先抽查书内
     是否用「系统提示」作 in-world 行文，本书 ch1/5/20/30 全零命中才放行）
  ④读者向后记喊话「【后记：这半分钟，够不够她讲完那把伞的事？评论区猜猜…】」（P126 ch57）
  ⑤「（本章完）」粘在末句后面非独占行（P122 ch56「…椅子转了一下。（本章完）」）——inline
     只剥标记保末句，勿整行删
- ⚠️ **导出 CDN 缓存旧响应坑**：修库后重备，get_export_links 下载可能命中修复前的缓存旧体
  （实录：P116 ch13 库内已修净，batch3 导出 TXT 仍是坏形态）。判读法=先 get_chapter_content
  核库内真态；库净即缓存假警报，勿重复修库；脏文件不在 eval 包内则无影响。同理蛙蛙线上
  章节以 chapter 详情 API 核实（本次线上 ch13 净版实证）。
- 挪批假警报判读：同书跨批两推时，先批的 precheck/verify expect 不含后批增量，报 drift=true /
  ok=false 属预期——真伪判据=对账公式「会话初值+各批推送之和」分毫不差即真绿。
- 误报判读：P122「专访提纲」×3=剧情道具（女主录音师改提纲），allow_leak 书级字段放行；
  「原句/自查/应答」同为该书剧情核心词。

### 更新批的其它坑（20260903 下午批）


- **REST 导出**：`GET /api/projects/{id}/export?format=txt&from_chapter=X&to_chapter=Y`
  （墨鱼 Bearer），空壳章(word_count=0)自动跳，但 **1~99 字半成品会混进导出**
  （41 的第17章）——expected 章数对不上就收窄 to_chapter，半成品留下批。
- my_list 响应形状漂移：`data.{list|items}|array` 都出现过，解析写全三分支
  （脚本已内置；手写解析时记得）。

## 实战记录

**2026-09-09 批量更新 14 本 202 章成功**（详情见记忆总账同日条）。重大新坑⑨：

**大 payload evaluate 的非 ASCII 字符会被传输链路打坏成 U+FFFD**：P60 守卫 parse_mismatch 连拦两轮，章号/数量/标题诊断全对——插桩发现 eval 内置 EXP 数组第 16 项的「第」字变成 3 个 U+FFFD 替换符（同数据手写诊断复跑全过=非数据问题；同一 code 稳定复现，疑传输分块在多字节字符中间切开，碰不碰边界纯看代码长度）。**治法：所有 evaluate 注入前，code 全文非 ASCII 统一转义成纯 ASCII**：

```js
const esc = s => s.replace(/[^\x00-\x7F]/g, ch =>
  ch.codePointAt(0) > 0xFFFF
    ? "\\u{" + ch.codePointAt(0).toString(16) + "}"
    : "\\u" + ch.codePointAt(0).toString(16).padStart(4, "0"));
const r = await tab.playwright.evaluate(esc(evs[i].code), undefined, { timeoutMs: 100000 });
```

字符串/注释/正则里的中文转 \uXXXX 均合法，b64 本就是纯 ASCII，全量转义零副作用（P60 实测 37 处非 ASCII 转义后一次过）。**勿再赌运气裸传中文 eval**。

**2026-09-08 批量更新 9 本 153 章成功**（签约后更新批；详情见记忆总账同日条）。三个新坑：

1. **my_list 有分页（默认 20 条）**：池子超 20 本后 precheck/verify 按 sid 找不到书（found=false 全场 `?`）。dump/precheck/verify 一律 `body: JSON.stringify({page:1,page_size:100})`（prepare_batch.py 4 处模板已改）。
2. **structure 挂历史旧节点两剧本**（pending_mismatch 拦下后先拉 structure 数 pending 构成）：重复章（word_count 一致）→ DELETE 旧节点再 submit 新的（63 实录，删 11 推 26）；旧节点即待推内容无重复 → 一并 submit（49 实录，11 旧+40 新=51）。回执 names 含 structure 里不存在的章（幻影）→ 以重拉 structure 为准（22 实录，报 15 实为 14）。
3. **章尾大纲泄漏块新形态**（P38 ch92）：`###` 分隔行 + 独行「第N章」无标题（被切章器误切→导出章数对不上）+「概要:/时间锚点:/写作目标:/大纲来源:/正文:」+ 重述散文。修库为正 + 兜底规则已入 prepare_batch.py（LEAK_RE 加概要/时间锚点/写作目标/大纲来源；内容性元数据行刻意留给体检拦，勿进 WRITER_NOTE_RE——pre_patch 先于体检）。

**2026-09-08 三长篇批量投稿成功**（17244 本店只收微笑 女频/幻想言情/唯美纯爱 16章42976字 / 17245 他的铁盒里全是我 女频/浪漫青春/青春校园 39章101130字 / 17246 各怀死讯：他先醒了三个月 女频/古装言情/古代重生 38章94973字，均 reviewing；投后 record_submission 三条回写墨鱼闭环）：

1. **prep 新投稿路径现也过 pre_patch_text**（此前只在 updates 路径）：下载后先清理再切章/扫描/打包，模型元数据行不再原样进 payload。两新形态已入 WRITER_NOTE_RE：「以下省略部分内容：…」（P59 虚报从略注）、「说明：正文含必要伏笔…」（P60 章末写作说明）。
2. **「以下省略」注先通读核实再删**：P59 第32章该行点名四场景（程蔓对话/账本第一页/三纸核验/刻痕链）正文全都在=模型虚报，删行即净，勿当残章弃投；若核实场景真缺才是残章，走 repair 或押后。
3. **新投稿路径大书同样分块**：create_submit eval >250KB 时从 code 正则抽 b64 字面量→`window.__pushB64` 分块注入（250KB/块，长度回传自证）→主体代码替换 `const b64 = window.__pushB64` 执行→delete 清理。P59 408KB/P60 376KB 各两块实测过。⚠️ Node 内核不跨调用：分块数据每次调用从 evals.json 重取，续块前先查页面 `window.__pushB64.length` 校验上一块还在。

## 旧手动路线存档（20260830~0902，已被脚本流水线取代）

当时四批（0830 绣庄夜话首投 12774 → 0831 双短篇征文 13639/13640 → 0901 双长篇
14743/14744 → 0902 六长篇 15215~15222）的逐条实录已并入「定论」/分类速查/体检项/
脚本，**0902 当天本技能重构为脚本流水线，旧 UI/手动路线作废**。只留仍有效的独立事实：

- **征文入口**：`GET /submission/campaigns/active` → `[{campaign_code, name}]`；
  batch.json 加 `"campaign": {"entry_type":"campaign","campaign_code":"…"}` 即走活动入口。
  历史活动：new_masterpiece_2026 名著新说 / micro_narrative_2026 微观情感叙事
  （征文规则 0.5 万字起投、篇数不限）；短篇建稿 `story_type:"short"`（普通长篇 "long"）。
- `create_from_file` 回执 `{code:200,data:{submission_id,base_novel_id}}`；**submit 响应
  code=200 + status=reviewing 即回执**（my_list 空响应不影响判读）。
- 导出签名链接 token 抄错一个字符 → 返回 61 字节 JSON 错误（下载内容异常先查这个）。

## 换封面（20260914 批量 28 本实测，prep_covers.py 在本目录）

签约作品可改封面；**reviewing 和 contracting 都被锁**（前端编辑弹窗对审核中显示
「投稿审核中，暂不支持修改作品信息」，API 同样 400「当前状态不允许修改」——P65
contracting 实测同锁）。签约过审后重跑即可。

- 接口：`PUT /wrhp-api/api/v1/submission/novel/{sid}`，body **白名单五字段**
  `{title, label_ids, cover, introduction, pen_name}`——除 cover 外全部取 my_list
  当前值原样回传，只换 cover。校验顺序实测：缺 title→500「内部校验【title】异常」；
  缺 label_ids→500 同款；多传 story_type/channel→400「仅允许修改标题、封面、简介、
  笔名和标签」。
- 封面上传复用 simpleupload（同 md5 幂等）；**COS 对象名=文件 md5**——终验直接比对
  my_list cover URL 文件名与本地 jpg md5，零歧义。
- 平台封面有独立审核流（文案写约 2 工作日、过审才对外显示；审核中不能再次上传）；
  投稿管理页/管理端立即见新图。
- 备料：写 mylist.json=[{sid,title,pid}]（pid 未知填 null，脚本按 get_export_links
  标题匹配并**写回**）→ `python3 prep_covers.py` → 产 evals.json（1 precheck + 每本
  1 条：simpleupload→my_list 取当前值→PUT→回读 verified）。eval 直接跑即可（b64
  超 240KB 走 window.__pushB64 分块，长度断言按累计和——末块较短）。
- **⚠️ 重大根因（20260914 换封面批踩实，修于 57d333b4 待部署）**：get_export_links
  的 cover_url 签名直链走 GET /cover/image，该端点曾无视 cover_url 永远伺服固定名
  主图（跟随最新生成）——「设为封面」的默认图只有书架/前端显示正确，导出/投稿链路
  全拿到最新图。部署前的绕行下载法：`GET /api/projects/{pid}/cover/gallery/{id8}/image`
  （Bearer PAT，全尺寸画廊文件），id8 取自书架 `/api/books` 返回的 cover 文件名
  （project_{pid}_{id8}.png；无 hex8=cover_url 指向主图，推主图即正确）。
- 0914 战绩：全池 45 本换封毕=首轮 30 本（含用户补报 P20/P16）+签约批 15 本；其中
  首轮误用主图的 44 本经画廊端点比对，27 本用户选的本来就是最新图（无需动）、
  **17 本重推修正终验全中**（P70/72/74/77/78/81/60/49/47/44/41/39/40/34/36/23/19，
  多本 md5=0913 投稿原封面，佐证用户选的是投稿时那张）；P37 cover_url 无 hex8
  （默认=主图）已推即对；仅 2 本墨语无项目（磨指甲 13639/退了婚没退群 13640）。
  P20 封面下载曾遇 EdgeOne 空响应：**单链接重试无用，每次尝试重拉新签名链接**。

## 待办

- **笔名（0921 终局+当晚补例）**：**有笔名的书禁止默认笔名**——唯一真相源=墨鱼侧项目
  `pen_name` 字段（建书时已从偏好页「笔名池」随机分配），`prepare_batch prep` 自动逐本拉取：
  batch.json 顶层 `pen_name` 已废弃（存在即警告忽略）、书级字段仅作人工核对（与墨鱼侧不一致停线）。
  **唯一例外（0921晚用户拍板）：墨鱼侧笔名为空=画画书**（建来只为出封面图，不带笔名），
  此时用 `DEFAULT_PEN_NAME`（不关夜灯的小水母）兜底并打警告——batch.json 顶层
  `default_pen_name` 可覆盖；默认值只进空槽，绝不覆盖已有笔名。**0921 事故实录**：顶层默认值被
  灌进 20 本全串「不关夜灯的小水母」，reviewing 态 PUT/DELETE 全锁死（详见记忆总账）。
  **永久弃用名单=yooyol / 在在暴打暖暖小拉在旁边劝架 /
  无聊大师**（0920 用户明令不再使用，王富贵系列续投也不得复活旧系列笔名），任何新书/新批次不得使用。
- **record_submission MCP 工具已建**（971b2a17 推双远程，未部署）：部署后投后回执=
  一条工具调用（platform/project_id/date/note），投稿→回写全闭环，无需用户手动。
