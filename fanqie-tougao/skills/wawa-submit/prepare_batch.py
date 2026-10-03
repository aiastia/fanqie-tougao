#!/usr/bin/env python3
"""蛙蛙批量投稿备料脚本：下载整书+封面 → 体检 → 生成浏览器注入代码。

一次性完成所有固定处理，浏览器环节只剩照序执行 evals.json 里的代码。
每本书固定 2 条 eval（>250KB 一律 window.__pushB64 分块注入，本脚本产出的均 ≤220KB）：
  stage=cover         传封面 → simpleupload → URL 存 window.__covURL{pid}
  stage=create_submit 解正文 → 页内切章(^第\\d+章) → create_from_file → submit

用法：
  python3 prepare_batch.py list                      # 列线上书(未投稿优先看)
  python3 prepare_batch.py prep batch.json -o /tmp/wawa_batch
  python3 prepare_batch.py updates_list [-m mylist.json] [-o updates.json] [--pid 37,38] [--archived false|true|all]
  python3 prepare_batch.py updates_prep updates.json -o /tmp/wawa_batch

签约书更新章节（updates 流水线）：墨鱼侧全程 MCP 直连（本脚本 mcp_call，读
config.json 的 moyuonlin key；会话里没挂 MCP 工具也不需要抓浏览器 token），
蛙蛙侧登录态只在浏览器里，保持 eval 注入。mylist.json 来自浏览器页内
POST my_list 的一次 dump（代码见 SKILL.md「更新章节」节）。

batch.json 格式（intro 必须是用户确认过的定稿）：
{
  "campaign": {"entry_type": "campaign", "campaign_code": "xxx"},   # 可选,征文才填
  # ⚠️ 笔名不要填：有笔名的书一律用墨鱼侧项目 pen_name（prep 自动逐本拉取，书级若填
  # 只作核对、不一致停线；顶层 pen_name 已废弃）。唯一例外：墨鱼侧笔名为空=画画书，
  # 用 DEFAULT_PEN_NAME(不关夜灯的小水母)兜底——顶层 default_pen_name 可覆盖。
  "books": [
    {"project_id": 41,
     "intro": "……定稿简介……",
     "channel": "女频",
     "cate": ["女频", "浪漫青春", "青春校园"],
     "labels": ["言情", "打脸", "黑莲花", "现代"]}
  ]
}
labels 传名称，脚本查同目录 labels.json 转成 id（系统+自定义都在）。
"""

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
ZCODE_CONFIG = Path.home() / ".zcode" / "cli" / "config.json"
# 0920 用户拍板：笔名随书不再有全局默认——每本书用项目自己的 pen_name（建书时已从
# 偏好页笔名池随机分配）。
# **0921 终局（20本全串水母事故后用户拍板）：有笔名的书一律用墨鱼侧项目 pen_name
# （唯一真相源，cmd_prep 自动逐本拉取对账；batch.json 顶层字段废弃、书级字段与墨鱼侧
# 不一致停线）。**唯一例外（0921晚用户拍板）：墨鱼侧笔名为空=画画书（建来只为出封面
# 图，不带笔名），此时用 DEFAULT_PEN_NAME 兜底并打警告——默认值只进空槽，绝不覆盖
# 已有笔名。
# **永久弃用名单=yooyol / 在在暴打暖暖小拉在旁边劝架 / 无聊大师**（0920 用户明令不再使用，
# 王富贵系列续投也不得复活旧系列笔名）。
# 登录态探测按历史昵称双兼容——问候语是否跟随笔名换名未实证，两个都认最稳。
# 画画书（墨鱼侧笔名为空）的兜底默认笔名；batch.json 顶层 default_pen_name 可覆盖。
DEFAULT_PEN_NAME = "\u4e0d\u5173\u591c\u706f\u7684\u5c0f\u6c34\u6bcd"  # 不关夜灯的小水母
NICKNAMES_JS = '["yooyol", "\\u4e0d\\u5173\\u591c\\u706f\\u7684\\u5c0f\\u6c34\\u6bcd"]'
# 「概要：/时间锚点/写作目标/大纲来源」=章末大纲元数据块（20260908 P38 实录：第92章尾
# 追加「###\n第92章\n概要:…\n时间锚点:…\n写作目标:…\n大纲来源:…\n正文:…」整块泄漏，
# 「概要」不在旧词表漏检）——体检层命中即 STOP；重述散文无法行级删，主修靠 update_chapter 修库。
LEAK_RE = re.compile(r"提纲|大纲|梗概|本章目标|剧情点|写作要求|字数要求|爽点|要求[:：]|基调[:：]"
                     r"|概要[:：]|时间锚点|写作目标[:：]|大纲来源"
                     # 20260912 六书更新批纵深词：已知形态 pre_patch 删，变体漏网靠这里 STOP
                     r"|应答说明|供参考|改进建议|完成度合格|system_warning|关键词[:：]"
                     r"|\d+\.\d+/10）"
                     # 20260913 投稿前16本全量扫描新形态（当日修库8处，见总账；消毒词表
                     # 同步扩了行删版——这里留 STOP 网防部署前新章再漏）
                     r"|补充说明（非正文）|结束分隔|（第\d+章完|自检注|完章标记|前三章末尾"
                     r"|交付内容说明|自查要点|伏笔埋入|上章承接|情绪曲线[:：]|声纹区分[:：]"
                     r"|需复核一处|iosa检查|（（本章完））"
                     # 20260916 十六本更新批新形态（当日修库9处）
                     r"|以上为生成的第\d+章正文|伏笔登记|承接上章|核心变化兑现"
                     r"|声纹自查|收束功能|修订后全文|按规则不应输出|伏笔回收"
                     # 20260920 更新批：模型自我纠正注「原句：…／下文：。。…」（可嵌正文段中）
                     r"|原句[:：]|下文[:：]"
                     # 20260921 投稿批20本实录（6书13章当日修库）：自查块/文风声明/裸完章
                     r"|装置自查|装置清点|自检要点|仿写说明|仿写，非"
                     r"|（正文完）|字数约\d+字|说明[:：]以上为第\d+章")

# G类「章节号自引用」体检（20260915 接入）：消毒器对这类只报不改，这里接推送面
# STOP 网——存量老书重推时把病带上平台的最后一道闸。守卫（文书词表/条文跟随等）
# 已内置 find_chapter_self_refs；本机无 book 仓库时优雅降级跳过。
try:
    _BACKEND = SKILL_DIR.parents[2] / "backend"
    sys.path.insert(0, str(_BACKEND))
    from app.services.content_sanitizer import find_chapter_self_refs as _FIND_SELFREFS
except Exception:
    _FIND_SELFREFS = None


def selfref_hits(text):
    if _FIND_SELFREFS is None:
        return []
    return _FIND_SELFREFS(text)
CN_HEAD_RE = re.compile(r"^第\s*[0-9一二三四五六七八九十百]+\s*章")
AR_HEAD_RE = re.compile(r"^第\d+章")
WARN = "\033[33m"; OK = "\033[32m"; BAD = "\033[31m"; END = "\033[0m"


def mcp_conf():
    cfg = json.loads(ZCODE_CONFIG.read_text())
    # ~/.zcode/cli/config.json 里挂在顶层 mcp.servers 下；老版本在 mcpServers，两处兼容
    servers = cfg.get("mcp", {}).get("servers") or cfg.get("mcpServers") or {}
    s = servers["moyuonlin"]
    return s["url"], s["headers"]["X-MCP-API-Key"]


def _mcp_post(url, key, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "X-MCP-API-Key": key})
    # 源站被打满时(522/RemoteDisconnected)3连2秒扛不住：8连指数退避，约3分钟窗口
    for attempt, wait in enumerate((0, 2, 4, 8, 15, 30, 45, 60)):
        try:
            body = urllib.request.urlopen(req, timeout=120).read().decode()
            break
        except Exception as e:
            if attempt == 7:
                raise
            time.sleep(wait)
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json",
                         "Accept": "application/json, text/event-stream",
                         "X-MCP-API-Key": key})
    if not body.strip():
        return None
    if "data:" in body:
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except Exception:
                    pass
        raise RuntimeError("SSE 解析失败: " + body[:200])
    return json.loads(body)


def mcp_call(name, args):
    url, key = mcp_conf()
    _mcp_post(url, key, {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "wawa-prep", "version": "1"}}})
    _mcp_post(url, key, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    r = _mcp_post(url, key, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": name, "arguments": args}})
    return json.loads(r["result"]["content"][0]["text"])


def download(url, dest, tries=8):
    waits = (0, 3, 6, 10, 20, 30, 45, 60)
    for attempt in range(tries):
        try:
            subprocess.run(["curl", "-sL", "--max-time", "120", "-o", str(dest), url],
                           check=True)
            if dest.stat().st_size > 0 and not dest.read_bytes()[:1] == b"":
                # 零字节/连接级失败靠 curl 退出码兜；这里只防意外空文件
                if dest.stat().st_size > 0:
                    return
        except Exception:
            pass
        time.sleep(waits[min(attempt + 1, tries - 1)])
    raise RuntimeError(f"下载失败: {url}")


def resolve_labels(names):
    table = json.loads((SKILL_DIR / "labels.json").read_text())
    out, missing = [], []
    for n in names:
        if n in table["system"]:
            out.append(table["system"][n]["id"])
        elif n in table["custom"]:
            out.append(table["custom"][n])
        else:
            missing.append(n)
    if missing:
        raise SystemExit(f"{BAD}labels.json 里找不到标签: {missing}"
                         f"（名字改用平台现名，或按 SKILL.md 的刷新法更新表）{END}")
    return out


def split_chapters(text):
    """页内同款切法：只认 ^第\\d+章，绕开「第X节」误切。
    「第N章完。」完章标记行不当章头（落入正文，后续 patch_text 整行删）。"""
    chapters, cur = [], None
    for line in text.splitlines():
        s = line.strip()
        if AR_HEAD_RE.match(s) and not END_MARK_RE.match(s):
            cur = {"name": s, "text": ""}
            chapters.append(cur)
        elif cur is not None:
            cur["text"] += ("\n" if cur["text"] else "") + line
    for c in chapters:
        c["text"] = c["text"].strip()
    return chapters


def cmd_list():
    data = mcp_call("list_projects", {})
    items = data.get("projects", data if isinstance(data, list) else [])
    print(f"{'ID':>4} {'字数':>8} {'状态':<10} {'投稿':<4} {'笔名':<14} 书名")
    for p in sorted(items, key=lambda x: (x.get("submissions", {}).get("count", 0), -x.get("word_count", 0))):
        sub = p.get("submissions", {})
        print(f"{p['id']:>4} {p.get('word_count', 0):>8} {p.get('status', ''):<10} "
              f"{sub.get('count', 0):<4} {p.get('pen_name', ''):<14} {p.get('title', '')}")


def cmd_prep(cfg_path, out_dir, draft_only=False):
    cfg = json.loads(cfg_path.read_text())
    out = Path(out_dir)
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    # 0921笔名事故终局（用户拍板）：投稿流水线禁止默认笔名。唯一真相源=墨鱼侧
    # 项目 pen_name 字段，prep 自动逐本拉取。batch.json 不需要填笔名；书级
    # pen_name 字段若填了仅作人工核对（与墨鱼侧不一致直接停线，防手滑）；顶层
    # pen_name 字段废弃——存在即警告忽略，任何「默认/兜底」一律不认。
    if cfg.get("pen_name"):
        print(f"{WARN}⚠ batch.json 顶层 pen_name 已废弃（0921事故），本次忽略——笔名一律取墨鱼侧项目字段{END}")
    lp = mcp_call("list_projects", {})
    src_pen = {p["id"]: (p.get("pen_name") or "").strip() for p in lp.get("projects", [])}
    pen_bad = []
    for b in cfg["books"]:
        want = src_pen.get(b["project_id"])
        if want is None:
            pen_bad.append(f"P{b['project_id']} {b.get('title','?')}: 墨鱼侧查无此项目")
        elif not want:
            # 0921晚用户拍板：笔名为空=画画书（建来只为出封面图），用默认笔名兜底不拦
            fallback = str(cfg.get("default_pen_name") or DEFAULT_PEN_NAME).strip()
            print(f"{WARN}⚠ P{b['project_id']} {b.get('title','?')}: 墨鱼侧无笔名（画画书？）"
                  f"——本次用默认笔名「{fallback}」{END}")
            b["pen_name"] = fallback
        elif b.get("pen_name") and str(b["pen_name"]).strip() != want:
            pen_bad.append(f"P{b['project_id']} {b.get('title','?')}: batch.json 写「{b['pen_name']}」但墨鱼侧是「{want}」"
                           f"——笔名以墨鱼侧为准，请修正或删掉该字段")
        else:
            b["pen_name"] = want  # 统一回填墨鱼侧笔名
    if pen_bad:
        sys.exit(f"{BAD}笔名对账失败（禁止默认笔名，投错改不了）:\n  " + "\n  ".join(pen_bad) + END)
    campaign = cfg.get("campaign")

    links_map = {}
    for b in cfg["books"]:
        cap = int(b.get("to_chapter") or 0)  # 可选单本章数上限：0=全本（与 updates 路径同款语义）
        links = mcp_call("get_export_links", {"project_id": b["project_id"],
                                              **({"to_chapter": cap} if cap else {})})
        if not links.get("ok"):
            raise SystemExit(f"{BAD}get_export_links 失败: project {b['project_id']}{END}")
        links_map[b["project_id"]] = links
    titles = [links_map[b["project_id"]]["title"] for b in cfg["books"]]
    dupes = {t for t in titles if titles.count(t) > 1}
    if dupes:
        raise SystemExit(f"{BAD}书名重复（平台会混淆）: {dupes}{END}")

    evals = [{"op": "eval", "stage": "precheck", "pid": 0,
              "note": "登录核验+重名拦截（有 draft/reviewing 同名即停，勿重建）",
              "code": precheck_code(titles)}]
    report = ["# 备料报告\n"]

    for b in cfg["books"]:
        pid = b["project_id"]
        links = links_map[pid]
        title = links["title"]
        safe = re.sub(r"[^\w\u4e00-\u9fff]", "", title)
        txt_path = work / f"{pid}_{safe}.txt"
        png_path = work / f"{pid}_{safe}.png"
        jpg_path = work / f"{pid}_cover.jpg"
        download(links["txt_url"], txt_path)
        download(links["cover_url"], png_path)
        raw_cover = png_path.read_bytes()
        cover_missing = raw_cover[:1] == b"{"  # 无封面时接口回 JSON {"detail":...}
        cover_md5 = ""
        if cover_missing:
            cover_b64 = ""
        else:
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "75",
                            "-Z", "1024", str(png_path), "--out", str(jpg_path)],
                           check=True, capture_output=True)
            cover_b64 = base64.b64encode(jpg_path.read_bytes()).decode()
            cover_md5 = hashlib.md5(jpg_path.read_bytes()).hexdigest()

        text = txt_path.read_text(encoding="utf-8")
        # 新投稿路径同样过预清理（20260908 P59/P60 实录：模型元数据行会原样进 payload）；
        # 只删元数据行/并假章头，真章头 ^第\d+章 不动，页内切章数不受影响。
        text = pre_patch_text(text)
        chapters = split_chapters(text)
        sizes = [len(c["text"]) for c in chapters]
        cn_heads = [l.strip()[:40] for l in text.splitlines()
                    if CN_HEAD_RE.match(l.strip()) and not AR_HEAD_RE.match(l.strip())]
        leaks = [l.strip()[:50] for l in text.splitlines() if LEAK_RE.search(l)]
        sr_hits = selfref_hits(text)
        problems = []
        # links.chapters 口径=全书有效章数；设了 to_chapter 时钳到上限（与 updates 路径同款）
        expect_ch = min(links.get("chapters", 0), int(b.get("to_chapter") or 0)) \
            if b.get("to_chapter") else links.get("chapters", len(chapters))
        if len(chapters) != expect_ch:
            problems.append(f"切章数 {len(chapters)} ≠ 平台 {expect_ch}")
        if min(sizes, default=0) < 200:
            problems.append(f"短章: {[(i + 1, s) for i, s in enumerate(sizes) if s < 200]}")
        if cn_heads:
            problems.append(f"中文数字章头(切分会漏/正文误排?): {cn_heads[:3]}")
        if leaks:
            problems.append(f"泄漏嫌疑 {len(leaks)} 行: {leaks[:3]}")
        if sr_hits:
            problems.append(f"章节号自引用 {len(sr_hits)} 处: {[h['preview'][:36] for h in sr_hits[:3]]}")

        txt_b64 = base64.b64encode(text.encode()).decode()
        payload = {
            "novel_title": title, "story_type": b.get("story_type", "long"),
            "channel": b["channel"], "introduction": b["intro"],
            "is_finished": b.get("is_finished", False),
            "pen_name": b["pen_name"],  # 已在头部对账回填墨鱼侧值,无默认无兜底
            "label_ids": resolve_labels(b["labels"]),
            "cate1_name": b["cate"][0], "cate2_name": b["cate"][1], "cate3_name": b["cate"][2],
        }
        if campaign:
            payload.update(campaign)

        if not cover_missing:
            evals.append({"op": "eval", "stage": "cover", "pid": pid, "note": title,
                          "code": cover_code(pid, cover_b64, cover_md5)})
        if draft_only:
            # 20260913 定时投稿批：只建稿停 draft 态不 submit，sid 回执后续定时任务补提交
            evals.append({"op": "eval", "stage": "create_draft", "pid": pid, "note": title,
                          "code": create_draft_code(pid, txt_b64, len(chapters), payload)})
        else:
            evals.append({"op": "eval", "stage": "create_submit", "pid": pid, "note": title,
                          "code": create_submit_code(pid, txt_b64, len(chapters), payload)})

        flag = "; ".join(problems) if problems else "干净"
        clamp_note = f"，to_chapter 钳自全书 {links.get('chapters')}" if b.get("to_chapter") else ""
        report += [f"## {pid} {title}", "",
                   f"- 切章: **{len(chapters)}** 章（平台 links 报 {expect_ch}{clamp_note}），"
                   f"每章 {min(sizes)}~{max(sizes)} 字，墨鱼 total_chars {links.get('total_chars')}",
                   f"- 封面: " + (f"jpg {jpg_path.stat().st_size // 1024}KB md5 `{cover_md5}`"
                                  if not cover_missing else "⚠️ 无封面（建稿空串过，平台可后补）"),
                   f"- eval 容量: cover {(len(evals[-2]['code']) // 1024) if not cover_missing else 0}KB / "
                   f"create {len(evals[-1]['code']) // 1024}KB",
                   f"- 简介({len(b['intro'])}字): {b['intro'][:60]}…",
                   f"- 体检: {flag}", ""]
        mark = f"{BAD}⚠️{END}" if problems else f"{OK}✓{END}"
        print(f"[{pid}] {title}: {len(chapters)}章 {mark} "
              f"{'; '.join(problems) if problems else ''}")

    (out / "evals.json").write_text(json.dumps(evals, ensure_ascii=False, indent=1))
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"\n产物: {out}/evals.json（{len(evals)} 条 eval）+ report.md + work/")


# ---------------- 签约书更新章节（updates 流水线） ----------------

BRACKET_META_RE = re.compile(r"^[【\[]\s*第\s*[0-9一二三四五六七八九十百]+\s*(?:章|回|节|卷|篇)\s*[】\]]")
FAKE_HEAD_RE = re.compile(r"^第\s*[0-9一二三四五六七八九十百]+\s*(?:章|回|节|卷|篇)")
# 完章标记行（如「第35章完。」独占一行）：模型写进正文的元数据，整行删。
# 20260917 P94 实录补书名号/引号包裹变体（«第9章完»）；要求「完」后只剩
# 标点/行尾，避免误删「第35章 完结篇」这类真章头。
END_MARK_RE = re.compile(r"^[«»「」『』\"'“”‘’]?\s*第\s*[0-9一二三四五六七八九十百]+\s*(?:章|回|节|卷|篇)\s*完[\s。．.！!～~«»「」『』\"'“”‘’]*$")

# 切章前预清理（20260907 六书实录）：真章头=「第N章 标题」章号后有空白；以下
# 无空白紧跟的形态是模型写进正文的元数据，split_chapters 会误当章头（对账必炸）。
META_LINE_RE = re.compile(r"^第\d+章(?:完[。．.!]|《[^》]*》\s*$|预告)")
# 「以下省略部分内容：」=模型虚报从略注（20260908 P59 实录：点名四场景正文全在，
# 纯元数据行）；「说明：正文含必要伏笔」=章末写作说明（20260908 P60 实录）——均整行删。
# 20260908 P38 补两种纯结构行：markdown 分隔线「###」独行、「第92章」独行假章头
# （章号后行尾即止，split_chapters 误切）。⚠️「概要:/时间锚点:」等内容性元数据行
# 刻意不在此删——pre_patch 跑在体检之前，删了体检就看不见，重述散文会静默混进
# payload；留给 LEAK_RE 命中 STOP 人工修库。
# ——20260912 六书更新批实录（6 本 23 行，逐行人工核实：均为章尾附着块，正文本体
# 在前后句完整收束，整行删零损失；删除行全量进 PREPATCH_REMOVED 报告可查）——
# 「（本章完）」三种变体/「关键词：#标签」行/「（应答说明：…））」/「补充说明…供参考：」/
# 「（当然了，本书的规矩：爽点…）」第四面墙吐槽/「正文收在钩子处：」章尾写作注/
# 「正文完，约3100字。本章兑现了…」/AI 自评块（本章是本卷…+评分行+改进建议）/
# <system_warning> token 限额标签/「胖大姐百货店：」场景标签行+其后创作分析行。
WRITER_NOTE_RE = re.compile(r"^(?:本章完成了大纲承诺|写作说明（供参考，非正文）"
                            r"|以下省略部分内容：|说明：正文含"
                            r"|#{3,}\s*$"
                            r"|第\d+章\s*$"
                            r"|（本章完"
                            r"|[（(]正文完，约\d+字[）)]"
                            r"|本章节"
                            r"|[（(]补充说明：本章节正文完"
                            r"|关键词[:：]#"
                            r"|（应答说明："
                            r"|补充说明[^，。]*，供参考[：:]"
                            r"|（当然了，本书的规矩："
                            r"|正文收在[^：:]{0,20}[：:]"
                            r"|正文完，约\d+字。"
                            r"|本章是本卷"
                            r"|(?:兑现|信息|角色|章末)[^：:]{0,8}（\d+\.\d+/10）[：:]"
                            r"|改进建议[：:]"
                            r"|<system_warning>"
                            r"|胖大姐百货店[：:]$"
                            r"|.*因上一章的事做出的反应"
                            # 20260916 十六本更新批新形态（当日修库9处，见SKILL.md 0916节）
                            r"|以上为生成的第\d+章正文"
                            r"|注[:：]按规则不应输出"
                            r"|【本章伏笔登记"
                            # 20260923 十四本更新批新形态（当日修库4处，见SKILL.md 0923节）
                            r"|[（(]本段正文约\d+字"
                            r"|Missing assistant reply"
                            r"|正文中不得出现任何创作元信息"
                            r"|_support_cite"
                            r"|用户消息包含"
                            r"|回收[:：]\d{4,}"
                            r"|埋入[:：]\d{4,}"
                            r"|说明[:：]\d{4,}（"
                            r"|本章核心变化兑现"
                            r"|伏笔回收（"
                            r"|承接上章[:：]"
                            r"|收束功能[:：]"
                            r"|声纹自查[:：]"
                            r"|字数[:：]约\d+字"
                            r"|自查[:：]字数约"
                            r"|<!--"
                            # 20260921 投稿批实录（消毒器同款）：自查长块/文风声明/裸完章
                            r"|（字数约\d+字"
                            r"|（自查："
                            r"|仿写说明[:：]"
                            r"|[（(]仿写，非[^）]{0,24}原文[）)]"
                            r"|自检要点"
                            r"|[（(]正文完[）)]"
                            r"|[（(]说明[:：]以上为第\d+章"
                            r"|原句[:：]\s*[-—─]{2,}"
                            # 20260922 更新批实录（修库18处）：仿写声明三变体（星号包裹/
                            # 无括号练习体/非原著变体——前两种旧表漏接）+「（本章正文完，约N字）」
                            r"|.*仿写[^。]{0,24}非(?:顾漫原文|原著)"
                            r"|（本章正文完"
                            # 20260923晚 更新批实录（修库10章）：字数自注简版/残留标签/
                            # 系统提示回显/假人味声明/读者向后记
                            r"|[（(]正文约\d+字[）)]\s*$"
                            r"|^</s+>$"
                            r"|^</content>"
                            r"|^（系统提示："
                            r"|良心写作，无任何AI辅助"
                            r"|^【后记[：:]"
                            r")")
THINKING_TAG_RE = re.compile(r"^</?thinking>\s*$")
AR_FAKE_PROSE_RE = re.compile(r"^第\d+章\S")
# 行首裸中文数字+回（如「三回了。」「一回是巧，…」）平台切章器也切（20260906 P34 /
# 20260907 P38 两实录）——并入上一非空行。
BARE_CN_HUI_RE = re.compile(r"^[一二三四五六七八九十百零两]+回")
# 行首裸阿拉伯数字+章（如「104章那本账还摊在…」，无「第」字，20260907 P31 实录）
# 平台同样切——并入上一非空行。
BARE_AR_CH_RE = re.compile(r"^\d+\s*章")
# 行首裸中文数字+章（如「一章是谁后来补盖的，没人知道。」，20260916 P87 实录）
# 平台同样切——并入上一非空行。
BARE_CN_CH_RE = re.compile(r"^[一二三四五六七八九十百零两]+章")


PREPATCH_REMOVED: list = []  # pre_patch_text 删除的行（跨书累积；调用方记游标取增量）


def pre_patch_text(text):
    """split_chapters 之前跑：删完章标记/书名号重复标题/预告标签/写作说明/
    thinking 标签整行；章号后无空白的叙述句（如「第70章那夜她把银根…」）及
    行首裸「X回」句并入上一非空行。只动换行位置不动文字。
    删除行全量记入 PREPATCH_REMOVED（20260912 起，让预清理可见可审计）。"""
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        if s and (META_LINE_RE.match(s) or WRITER_NOTE_RE.match(s)
                  or THINKING_TAG_RE.match(s)):
            PREPATCH_REMOVED.append(s[:60])
            continue
        if s and (AR_FAKE_PROSE_RE.match(s) or BARE_CN_HUI_RE.match(s)
                  or BARE_AR_CH_RE.match(s) or BARE_CN_CH_RE.match(s)):
            i = next((i for i in range(len(out) - 1, -1, -1) if out[i].strip()), None)
            if i is not None:
                out[i] += ln
                continue
        out.append(ln)
    return "\n".join(out)


def cjk_len(s):
    return len(re.findall(r"[\u4e00-\u9fff]", s))


def patch_text(text):
    """平台切章器会切行首「第X回」和「【第X章】」标签（实测行中不切）。
    散文式假章头→并入前面最近的非空行（并到空行=白并，位置不变照样切）；
    括号元数据标签（前情提要类，非正文）→整行删；「第N章完。」完章标记→整行删。
    只动换行位置不动文字。"""
    merged, removed, out = [], [], []
    for ln in text.split("\n"):
        s = ln.strip()
        if s and (BRACKET_META_RE.match(s) or END_MARK_RE.match(s)):
            removed.append(s[:30])
            continue
        if s and FAKE_HEAD_RE.match(s) and not AR_HEAD_RE.match(s):
            i = next((i for i in range(len(out) - 1, -1, -1) if out[i].strip()), None)
            if i is not None:
                out[i] += ln
                merged.append(s[:24])
                continue
        out.append(ln)
    return "\n".join(out), merged, removed


def cmd_updates_list(pid_filter, mylist_path, out_path, archived="false"):
    # archived 三态：false=只盘未归档（默认，0905 拍板「归档书不查不推」）/
    # true=只盘已归档 / all=全池都盘。0914 全池体检实录：已归档书仍在蛙蛙在架
    # 需要维护（P22/P23/P36 当时是手写 updates.json 绕过的），这类批次传 all。
    # 线上旧版不认 MCP 筛参（静默忽略），条目级再兜底过滤一次。
    mcp_args = {"archived": False} if archived == "false" else (
        {"archived": True} if archived == "true" else {})
    try:
        data = mcp_call("list_projects", mcp_args)
    except Exception:
        data = mcp_call("list_projects", {})
    items = data.get("projects", data if isinstance(data, list) else [])
    if archived == "false":
        items = [p for p in items
                 if not (p.get("archived") is True or p.get("status") == "archived")]
    elif archived == "true":
        items = [p for p in items
                 if p.get("archived") is True or p.get("status") == "archived"]
    my = {}
    if mylist_path:
        for x in json.loads(Path(mylist_path).read_text()):
            my[x["title"]] = x
    else:
        print(f"{WARN}未给 -m mylist.json（蛙蛙侧已推章数没法对账）。"
              f"先按 SKILL.md「更新章节」节 dump 一份再跑，或直接手写 updates.json{END}\n")
    rows = []
    for p in sorted(items, key=lambda x: x["id"]):
        if pid_filter and p["id"] not in pid_filter:
            continue
        # 0918 提速：有效章数直接取 list_projects 自带的 written_chapter_count
        # （口径=word_count>0，与 get_export_links 的 chapters 同源），免掉
        # 每本一次 MCP 会话握手（35本×3请求串行≈10分钟 → 1次调用秒级）。
        links = None
        valid = p.get("written_chapter_count")
        if valid is None:
            links = mcp_call("get_export_links", {"project_id": p["id"]})
            if not links.get("ok"):
                print(f"[{p['id']}] get_export_links 失败，跳过")
                continue
            valid = links.get("chapters", 0)
        title = p.get("title", "") or (links or {}).get("title", "")
        w = my.get(title)
        if (w or {}).get("is_finished"):
            # 蛙蛙已完结的书不处理（20260905 用户拍板）；dump 需带 is_finished 字段
            print(f"[{p['id']}] {title}: 蛙蛙已完结，跳过")
            continue
        row = {"project_id": p["id"], "title": title, "valid": valid,
               "submission_id": (w or {}).get("sid"),
               "base_novel_id": (w or {}).get("base_novel_id"),
               "wawa_chapters": (w or {}).get("chapters")}
        row["new"] = (valid - row["wawa_chapters"]) if row["wawa_chapters"] is not None else None
        rows.append(row)
    print(f"{'ID':>4} {'有效章':>5} {'已推':>4} {'可推':>4}  书名")
    for r in rows:
        new = "-" if r["new"] is None else r["new"]
        mark = f"{OK}{new}{END}" if isinstance(r["new"], int) and r["new"] > 0 else new
        print(f"{r['project_id']:>4} {r['valid']:>5} "
              f"{'?' if r['wawa_chapters'] is None else r['wawa_chapters']:>4} {mark:>4}  {r['title']}")
    if out_path:
        draft = {"books": [{k: r[k] for k in ("project_id", "submission_id",
                                              "base_novel_id", "wawa_chapters")}
                           for r in rows if r["new"]] or []}
        Path(out_path).write_text(json.dumps(draft, ensure_ascii=False, indent=1))
        print(f"\n草稿已写 {out_path}（可推>0 的书；核对后跑 updates_prep）")


def cmd_updates_prep(cfg_path, out_dir):
    cfg = json.loads(cfg_path.read_text())
    out = Path(out_dir)
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    evals = [{"op": "eval", "stage": "updates_precheck", "pid": 0,
              "note": "登录核验+平台已推章数漂移检查（drift=true 勿跑后续）",
              "code": updates_precheck_code(cfg["books"])}]
    report = ["# 更新备料报告\n"]

    for b in cfg["books"]:
        pid, wawa_ch = b["project_id"], b["wawa_chapters"]
        from_ch = wawa_ch + 1
        cap = int(b.get("to_chapter") or 999)  # 可选单本推送上限：留末章手动上传等场景
        title = f"project{pid}"
        b["_push_n"] = 0
        try:
            links = mcp_call("get_export_links", {"project_id": pid,
                                                  "from_chapter": from_ch, "to_chapter": cap})
            if not links.get("ok"):
                raise RuntimeError("get_export_links 失败")
            title = links["title"]
            # chapters 口径=全书有效章数；设了 to_chapter 时钳到上限（接口可能回范围数也可能回全量）
            total_valid = min(links.get("chapters", 0), cap)
            expect_new = total_valid - wawa_ch
            safe = re.sub(r"[^\w\u4e00-\u9fff]", "", title)
            txt_path = work / f"{pid}_{safe}_upd.txt"
            download(links["txt_url"], txt_path, tries=5)
            time.sleep(1)
            text = txt_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
            pre_n = len(PREPATCH_REMOVED)
            chapters = split_chapters(pre_patch_text(text))
            pre_removed = PREPATCH_REMOVED[pre_n:]
            # 尾随半成品章（<200字，如还在写的最后一章）自动截掉留下批
            trimmed = []
            while chapters and cjk_len(chapters[-1]["text"]) < 200:
                trimmed.insert(0, chapters.pop()["name"][:20])

            problems = []
            if not chapters:
                problems.append("无新章可推（全是空壳/半成品）")
            else:
                # links.chapters 口径=word_count>0；截掉的尾随半成品也计入它，故同步减掉
                exp2 = expect_new - len(trimmed)
                if len(chapters) != exp2:
                    problems.append(f"可推章数对不上: 导出{len(chapters)}章(已截尾随半成品{len(trimmed)}章)"
                                    f"≠ 有效{total_valid}-已推{wawa_ch}-截{len(trimmed)}={exp2}，查中途短章/空壳")
                else:
                    nums = [int(re.match(r"^第(\d+)章", c["name"]).group(1)) for c in chapters]
                    if nums != list(range(from_ch, from_ch + len(chapters))):
                        problems.append(f"章号不连续: {nums[:6]}…")
            leaks = resid = merged = removed = []
            if not problems:
                patched, merged, removed = patch_text(
                    "\n\n".join(f"{c['name']}\n\n{c['text']}" for c in chapters))
                leaks = [l.strip()[:50] for l in patched.splitlines() if LEAK_RE.search(l)]
                resid = [l.strip()[:40] for l in patched.splitlines()
                         if FAKE_HEAD_RE.match(l.strip()) and not AR_HEAD_RE.match(l.strip())]
                sr_hits = selfref_hits(patched)
                if leaks:
                    if b.get("allow_leak"):
                        print(f"[{pid}] {title}: 泄漏嫌疑 {len(leaks)} 行已人工核放行(allow_leak)")
                    else:
                        problems.append(f"泄漏嫌疑 {len(leaks)} 行: {leaks[:3]}（人工核，确认误报可放行）")
                if sr_hits:
                    if b.get("allow_selfref"):
                        print(f"[{pid}] {title}: 自引用 {len(sr_hits)} 处已人工核放行(allow_selfref)")
                    else:
                        problems.append(f"章节号自引用 {len(sr_hits)} 处: {[h['preview'][:36] for h in sr_hits[:3]]}（修库后重备）")
                if resid:
                    problems.append(f"补丁后仍有行首假章头: {resid[:3]}")
            if problems:
                report += [f"## {pid} {title}", "", f"- ⚠️ {'; '.join(problems)}", ""]
                print(f"[{pid}] {title}: {BAD}跳过{END} {'; '.join(problems)}")
                b["_skip"] = "; ".join(problems)
                continue

            n = len(chapters)
            b["_push_n"] = n
            b["_range"] = f"{from_ch}~{from_ch + n - 1}"
            txt_b64 = base64.b64encode(patched.encode()).decode()
            evals.append({"op": "eval", "stage": "update_submit", "pid": pid, "note": title,
                          "code": update_submit_code(b["submission_id"], b["base_novel_id"],
                                                     txt_b64, from_ch, n)})
            sizes = [cjk_len(c["text"]) for c in chapters]
            report += [f"## {pid} {title}", "",
                       f"- 推送范围: **第{from_ch}~{from_ch + n - 1}章**（{n}章，"
                       f"每章 {min(sizes)}~{max(sizes)} 字）"
                       + (f"；截掉尾随半成品: {trimmed}" if trimmed else ""),
                       f"- 预清理删除: {len(pre_removed)}行"
                       + (f"（如 {pre_removed[:2]}…）" if pre_removed else ""),
                       f"- 正文补丁: 并入上一段 {merged or '无'}；删除标签行 {removed or '无'}",
                       f"- eval 容量: {len(evals[-1]['code']) // 1024}KB", ""]
            print(f"[{pid}] {title}: 推 {n} 章(第{from_ch}~{from_ch + n - 1}) {OK}✓{END}"
                  + (f" 截半成品{len(trimmed)}章" if trimmed else "")
                  + (f" 补丁{len(merged) + len(removed)}处" if (merged or removed) else ""))
        except Exception as e:
            b["_skip"] = str(e)
            report += [f"## {pid} {title}", "", f"- ⚠️ 失败: {e}", ""]
            print(f"[{pid}] {title}: {BAD}失败{END} {e}")

    todo = [b for b in cfg["books"] if b.get("_push_n")]
    evals.append({"op": "eval", "stage": "updates_verify", "pid": 0,
                  "note": "终验:my_list 对账（submitted == 已推+本次）",
                  "code": updates_verify_code(todo)})
    (out / "evals.json").write_text(json.dumps(evals, ensure_ascii=False, indent=1))
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")
    total = sum(b["_push_n"] for b in todo)
    print(f"\n产物: {out}/evals.json（{len(evals)} 条: precheck + {len(todo)} 本书"
          f"共{total}章 + verify）+ report.md")
    print("浏览器打开 wawawriter.com/app/ 按序执行即可；precheck drift=true 或"
          "某本报 parse_mismatch/pending_mismatch 时停，人工看再决定。")


def updates_precheck_code(books):
    want = json.dumps([{"sid": b["submission_id"], "wawa": b["wawa_chapters"]}
                       for b in books], ensure_ascii=False)
    return f"""(async () => {{
  if (!location.origin.includes("wawawriter")) return {{ error: "wrong origin" }};
  const j = await fetch("/wrhp-api/api/v1/submission/novel/my_list", {{ method: "POST", credentials: "include", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{page:1,page_size:100}}) }}).then(x => x.json());
  const arr = (j.data && (j.data.items || j.data.list)) || (Array.isArray(j.data) ? j.data : []);
  const want = {want};
  return {{ loggedIn: {NICKNAMES_JS}.some(n => document.body.innerText.includes(n)),
    rows: want.map(w => {{
      const x = arr.find(i => String(i.submission_id) === String(w.sid));
      const n = x && Array.isArray(x.submitted_chapter_ids) ? x.submitted_chapter_ids.length : null;
      return {{ sid: w.sid, found: !!x, status: x && x.status, submitted: n, expect: w.wawa,
                drift: n !== null && n !== w.wawa }};
    }}) }};
}})()"""


def update_submit_code(sid, base_id, txt_b64, from_ch, n):
    exp = json.dumps([f"第{from_ch + i}章" for i in range(n)], ensure_ascii=False)
    return f"""(async () => {{
  if (!location.origin.includes("wawawriter")) return {{ error: "wrong origin" }};
  const b64 = "{txt_b64}";
  if (b64.length !== {len(txt_b64)}) return {{ error: "注入不完整" }};
  const text = new TextDecoder("utf-8").decode(Uint8Array.from(atob(b64), c => c.charCodeAt(0)));
  const EXP = {exp};
  const J = async (u, o) => fetch(u, Object.assign({{ credentials: "include" }}, o)).then(x => x.json());
  const POST = (u, b) => J(u, {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify(b || {{}}) }});
  const struct = async () => {{
    const j = await J("/wrhp-api/api/v2/novel/{base_id}/structure");
    const d = j.data || j;
    const vols = d.volumes || [];
    const all = vols.flatMap(v => (v.chapters || []).map(c => Object.assign({{}}, c, {{ volume_id: v.volume_id }})));
    const main = vols.slice().sort((a, b) => (b.chapters || []).length - (a.chapters || []).length)[0] || {{}};
    return {{ all, volId: main.volume_id }};
  }};
  const s1 = await struct();
  const before = s1.all.length;
  const pj = await POST("/wrhp-api/api/v2/novel/parse_chapters", {{ text }});
  const pd = pj.data || pj;
  const chapters = Array.isArray(pd) ? pd : (pd.chapters || []);
  const titles = chapters.map(c => (c.title || c.name || "").trim());
  if (chapters.length !== EXP.length || !titles.every((t, i) => t.startsWith(EXP[i])))
    return {{ fail: "parse_mismatch", parseN: chapters.length, titles: titles.map(t => t.slice(0, 10)) }};
  const count = async () => (await struct()).all.length;
  let version = null, imp = null;
  imp = await POST("/wrhp-api/api/v2/novel/{base_id}/import_chapters", {{ chapters, volume_id: s1.volId }});
  let after = await count();
  if (after > before) version = "v2";
  else {{
    imp = await POST("/wrhp-api/api/v1/novel/{base_id}/import_chapters", {{ chapters, volume_id: s1.volId }});
    after = await count();
    if (after > before) version = "v1";
  }}
  if (!version) return {{ fail: "import_noop", before, imp: JSON.stringify(imp).slice(0, 150) }};
  const s3 = await struct();
  const pending = s3.all.filter(c => !c.is_submitted);
  if (pending.length !== EXP.length) return {{ fail: "pending_mismatch", before, after, pendingN: pending.length, names: pending.map(c => c.name) }};
  const sub = await POST("/wrhp-api/api/v1/submission/update/submit_chapters", {{ submission_id: {sid}, chapter_ids: pending.map(c => c.node_id) }});
  const sd = sub.data || sub;
  return {{ before, after, version, n: EXP.length,
    head: pending[0] && pending[0].name, tail: pending[pending.length - 1] && pending[pending.length - 1].name, submit: sd }};
}})()"""


def updates_verify_code(books):
    want = json.dumps([{"sid": b["submission_id"], "want": b["wawa_chapters"] + b["_push_n"]}
                       for b in books], ensure_ascii=False)
    return f"""(async () => {{
  if (!location.origin.includes("wawawriter")) return {{ error: "wrong origin" }};
  const j = await fetch("/wrhp-api/api/v1/submission/novel/my_list", {{ method: "POST", credentials: "include", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{page:1,page_size:100}}) }}).then(x => x.json());
  const arr = (j.data && (j.data.items || j.data.list)) || (Array.isArray(j.data) ? j.data : []);
  const want = {want};
  return want.map(w => {{
    const x = arr.find(i => String(i.submission_id) === String(w.sid));
    const n = x && Array.isArray(x.submitted_chapter_ids) ? x.submitted_chapter_ids.length : null;
    return {{ sid: w.sid, submitted: n, want: w.want, ok: n === w.want, words: x && x.total_word_count }};
  }});
}})()"""


def precheck_code(titles):
    wanted = json.dumps([t for t in titles if t], ensure_ascii=False)
    return f"""(async () => {{
  if (!location.origin.includes("wawawriter")) return {{ error: "wrong origin: " + location.origin }};
  const j = await fetch("/wrhp-api/api/v1/submission/novel/my_list", {{ method: "POST", credentials: "include", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{page:1,page_size:100}}) }}).then(x => x.json());
  const arr = (j.data && (j.data.items || j.data.list)) || (Array.isArray(j.data) ? j.data : []);
  const want = {wanted};
  return {{ loggedIn: {NICKNAMES_JS}.some(n => document.body.innerText.includes(n)), total: arr.length,
    existing: arr.filter(i => want.includes(i.title) && i.status !== "rejected")
                 .map(i => ({{ sid: i.submission_id, title: i.title, status: i.status }})) }};
}})()"""


def cover_code(pid, b64, md5):
    return f"""(async () => {{
  if (!location.origin.includes("wawawriter")) return {{ error: "wrong origin: " + location.origin }};
  const b64 = "{b64}";
  if (b64.length !== {len(b64)}) return {{ error: "注入不完整" }};
  const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const fd = new FormData();
  fd.append("file", new File([bin], "cover.jpg", {{ type: "image/jpeg" }}));
  fd.append("file_secret", "{md5}");
  const r = await fetch("/wrhp-api/api/v1/file/simpleupload", {{ method: "POST", body: fd, credentials: "include" }}).then(x => x.json());
  const url = (r.data && (r.data.result || r.data.url)) || null;
  if (url) window.__covURL{pid} = url;
  return {{ code: r.code, url }};
}})()"""


def create_submit_code(pid, txt_b64, nchapters, payload):
    return f"""(async () => {{
  if (!location.origin.includes("wawawriter")) return {{ error: "wrong origin: " + location.origin }};
  const b64 = "{txt_b64}";
  if (b64.length !== {len(txt_b64)}) return {{ error: "注入不完整" }};
  const text = new TextDecoder("utf-8").decode(Uint8Array.from(atob(b64), c => c.charCodeAt(0)));
  const chapters = []; let cur = null;
  for (const line of text.split(/\\r?\\n/)) {{
    if (/^第\\d+章/.test(line.trim())) {{ cur = {{ name: line.trim(), text: "" }}; chapters.push(cur); }}
    else if (cur) {{ cur.text += (cur.text ? "\\n" : "") + line; }}
  }}
  chapters.forEach(c => {{ c.text = c.text.trim(); }});
  if (chapters.length !== {nchapters}) return {{ error: "章数不符", got: chapters.length }};
  if (Math.min(...chapters.map(c => c.text.length)) < 30) return {{ error: "有<30字短章" }};
  const cover = window.__covURL{pid};
  if (!cover) return {{ error: "封面未上传（先跑 cover 那条）" }};
  const body = {json.dumps(payload, ensure_ascii=False)};
  body.cover = cover; body.chapters = chapters;
  const c = await fetch("/wrhp-api/api/v1/submission/novel/create_from_file", {{ method: "POST", credentials: "include", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify(body) }}).then(x => x.json());
  const sid = c.data && c.data.submission_id;
  if (!sid) return {{ create: {{ code: c.code, msg: (c.message || "").slice(0, 120) }} }};
  const s = await fetch("/wrhp-api/api/v1/submission/novel/" + sid + "/submit", {{ method: "POST", credentials: "include", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{page:1,page_size:100}}) }}).then(x => x.json());
  const d = s.data || {{}};
  return {{ create: {{ code: c.code, sid }}, submit: {{ code: s.code, status: d.status, words: d.total_word_count, chapters: (d.submitted_chapter_ids || []).length }} }};
}})()"""


def create_draft_code(pid, txt_b64, nchapters, payload):
    """create_submit_code 的只建稿版：create_from_file 成即返回 sid，不调 submit。
    章节随 create 落库（my_list 显示 0 章 0 字是正常态），submit 由后续定时任务补。"""
    return f"""(async () => {{
  if (!location.origin.includes("wawawriter")) return {{ error: "wrong origin: " + location.origin }};
  const b64 = "{txt_b64}";
  if (b64.length !== {len(txt_b64)}) return {{ error: "注入不完整" }};
  const text = new TextDecoder("utf-8").decode(Uint8Array.from(atob(b64), c => c.charCodeAt(0)));
  const chapters = []; let cur = null;
  for (const line of text.split(/\\r?\\n/)) {{
    if (/^第\\d+章/.test(line.trim())) {{ cur = {{ name: line.trim(), text: "" }}; chapters.push(cur); }}
    else if (cur) {{ cur.text += (cur.text ? "\\n" : "") + line; }}
  }}
  chapters.forEach(c => {{ c.text = c.text.trim(); }});
  if (chapters.length !== {nchapters}) return {{ error: "章数不符", got: chapters.length }};
  if (Math.min(...chapters.map(c => c.text.length)) < 30) return {{ error: "有<30字短章" }};
  const cover = window.__covURL{pid} || "";  // 无封面书（cover_missing）空串过，草稿可后补图
  const body = {json.dumps(payload, ensure_ascii=False)};
  body.cover = cover; body.chapters = chapters;
  const c = await fetch("/wrhp-api/api/v1/submission/novel/create_from_file", {{ method: "POST", credentials: "include", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify(body) }}).then(x => x.json());
  const sid = c.data && c.data.submission_id;
  if (!sid) return {{ create: {{ code: c.code, msg: (c.message || "").slice(0, 120) }} }};
  return {{ create: {{ code: c.code, sid }} }};
}})()"""


def main():
    ap = argparse.ArgumentParser(description="蛙蛙批量投稿/签约书更新 备料")
    ap.add_argument("cmd", choices=["list", "prep", "updates_list", "updates_prep"])
    ap.add_argument("config", nargs="?", help="batch.json / updates.json（prep 必填）")
    ap.add_argument("-o", "--out", default="/tmp/wawa_batch")
    ap.add_argument("-m", "--mylist", help="mylist.json（updates_list 用，蛙蛙侧 dump）")
    ap.add_argument("--pid", help="updates_list 只盘这几本，逗号分隔")
    ap.add_argument("--archived", choices=["false", "true", "all"], default="false",
                    help="updates_list 盘点范围：false=只盘未归档（默认，归档书不查不推）/ "
                         "true=只盘已归档 / all=全池都盘（维护蛙蛙在架的归档书时用）")
    ap.add_argument("--draft-only", action="store_true",
                    help="prep 只建稿不提交（定时投稿两段式第一步）")
    args = ap.parse_args()
    if args.cmd == "list":
        cmd_list()
    elif args.cmd == "updates_list":
        pids = {int(x) for x in args.pid.split(",")} if args.pid else None
        out_path = args.out if args.out.endswith(".json") else None
        cmd_updates_list(pids, args.mylist, out_path, archived=args.archived)
    elif args.cmd == "updates_prep":
        if not args.config:
            ap.error("updates_prep 需要 updates.json 路径")
        cmd_updates_prep(Path(args.config), args.out)
    else:
        if not args.config:
            ap.error("prep 需要 batch.json 路径")
        cmd_prep(Path(args.config), args.out, draft_only=args.draft_only)


if __name__ == "__main__":
    main()
