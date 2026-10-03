#!/usr/bin/env python3
r"""蛙蛙批量导入本地 txt 为草稿（不投稿）。

与 prepare_batch.py 的区别：数据源是本地 txt（非墨鱼导出）、不传封面、
create_from_file 后不调 submit——作品停在 draft 态，之后用户在网页自行投稿。

用法:
    python3 import_draft.py <a.txt> [b.txt ...] -o /tmp/wawa_draft
产物:
    evals.json  precheck + 每本 1 条 create_only（code 已全量 \uXXXX 转义为纯 ASCII，
                按坑⑨定律防大 payload 非 ASCII 被传输链路打坏）
    report.md   书单/章数/字数

字段策略: channel/cate/label_ids/introduction 是建稿 API 字段，给占位值兜底；
简介自动取正文开头 150 字。缺字段报 422 时按 message 现场补 payload 再跑。
"""
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

OUT_DIR = "/tmp/wawa_draft"
# 0916 拍板默认笔名（旧 yooyol 弃用）；登录态探测双昵称兼容，JS 侧用纯 ASCII 字面量
# （坑⑨纪律）：\u4e0d\u5173\u591c\u706f\u7684\u5c0f\u6c34\u6bcd = 不关夜灯的小水母
PEN_NAME = "不关夜灯的小水母"
NICKNAMES_JS = '["yooyol", "\\u4e0d\\u5173\\u591c\\u706f\\u7684\\u5c0f\\u6c34\\u6bcd"]'
# 占位分类（skill 分类速查里验证过存在的路径）；不投稿，仅过字段校验
PLACEHOLDER = {
    "story_type": "long",
    "channel": "女频",
    "cate": ["女频", "情感小说", "婚恋情感"],
    "is_finished": False,
}


def esc(s: str) -> str:
    """code 全文非 ASCII → \\uXXXX（坑⑨：大 payload 非 ASCII 会被传输打坏成 U+FFFD）。"""
    return re.sub(
        r"[^\x00-\x7F]",
        lambda m: (
            "\\u{" + format(ord(m.group(0)), "x") + "}"
            if ord(m.group(0)) > 0xFFFF
            else "\\u" + format(ord(m.group(0)), "04x")
        ),
        s,
    )


def read_text(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"[X] {p.name}: 无法解码（utf-8/gb18030 都失败）")


def split_chapters(text: str):
    chapters, cur = [], None
    for line in text.splitlines():
        if re.match(r"^第\d+章", line.strip()):
            cur = {"name": line.strip(), "text": ""}
            chapters.append(cur)
        elif cur is not None:
            cur["text"] += ("\n" if cur["text"] else "") + line
    for c in chapters:
        c["text"] = c["text"].strip()
    return chapters


def intro_of(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s and not re.match(r"^第\d+章", s):
            return re.sub(r"\s+", " ", s)[:150]
    return "暂无简介"


def precheck_code(titles):
    wanted = json.dumps(titles, ensure_ascii=False)
    return f"""(async () => {{
  if (!location.origin.includes("wawawriter")) return {{ error: "wrong origin: " + location.origin }};
  const j = await fetch("/wrhp-api/api/v1/submission/novel/my_list", {{ method: "POST", credentials: "include", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{page:1,page_size:100}}) }}).then(x => x.json());
  const arr = (j.data && (j.data.items || j.data.list)) || (Array.isArray(j.data) ? j.data : []);
  const want = {wanted};
  return {{ loggedIn: {NICKNAMES_JS}.some(n => document.body.innerText.includes(n)), total: arr.length,
    existing: arr.filter(i => want.includes(i.title) && i.status !== "rejected")
                 .map(i => ({{ sid: i.submission_id, title: i.title, status: i.status }})) }};
}})()"""


def create_only_code(txt_b64, nchapters, payload):
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
  const body = {json.dumps(payload, ensure_ascii=False)};
  body.chapters = chapters;
  const c = await fetch("/wrhp-api/api/v1/submission/novel/create_from_file", {{ method: "POST", credentials: "include", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify(body) }}).then(x => x.json());
  return {{ create: {{ code: c.code, msg: (c.message || "").slice(0, 160), sid: c.data && c.data.submission_id }} }};
}})()"""


def main():
    import argparse
    ap = argparse.ArgumentParser(description="蛙蛙批量导入本地 txt 为草稿（不投稿）")
    ap.add_argument("txts", nargs="+", help="txt 文件路径（可多个）")
    ap.add_argument("-o", "--out", default=OUT_DIR)
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    books = []
    for arg in args.txts:
        p = Path(arg).expanduser()
        if not p.is_file():
            raise SystemExit(f"[X] 文件不存在: {p}")
        title = p.stem.strip()
        text = read_text(p)
        chapters = split_chapters(text)
        if not chapters:
            raise SystemExit(f"[X] {p.name}: 切不出任何章（页内同款规则只认行首「第N章」）")
        sizes = [len(c["text"]) for c in chapters]
        payload = {
            "novel_title": title,
            "story_type": PLACEHOLDER["story_type"],
            "channel": PLACEHOLDER["channel"],
            "introduction": intro_of(text),
            "is_finished": PLACEHOLDER["is_finished"],
            "pen_name": PEN_NAME,
            "label_ids": [],
            "cate1_name": PLACEHOLDER["cate"][0],
            "cate2_name": PLACEHOLDER["cate"][1],
            "cate3_name": PLACEHOLDER["cate"][2],
            # cover 是建稿必填字段（缺了 422「请求参数【cover】异常」），不传封面给空串即过
            "cover": "",
        }
        txt_b64 = base64.b64encode(text.encode()).decode()
        books.append({
            "title": title, "path": p, "chapters": chapters, "sizes": sizes,
            "txt_b64": txt_b64, "payload": payload,
        })

    titles = [b["title"] for b in books]
    dupes = {t for t in titles if titles.count(t) > 1}
    if dupes:
        raise SystemExit(f"[X] 书名重复（平台会混淆）: {dupes}")

    evals = [{"op": "eval", "stage": "precheck", "book": "",
              "note": "登录核验+重名拦截（同名 draft/reviewing 即停，勿重建防双稿）",
              "code": esc(precheck_code(titles))}]
    report = ["# 蛙蛙草稿导入备料（不投稿）\n"]
    for b in books:
        code = create_only_code(b["txt_b64"], len(b["chapters"]), b["payload"])
        evals.append({"op": "eval", "stage": "create_only", "book": b["title"],
                      "note": f"{len(b['chapters'])}章 → 草稿（不submit）",
                      "code": esc(code)})
        report += [
            f"## {b['title']}", "",
            f"- 来源: {b['path']}",
            f"- 切章: **{len(b['chapters'])}** 章，每章 {min(b['sizes'])}~{max(b['sizes'])} 字，"
            f"总 {sum(b['sizes'])} 字",
            f"- 简介(占位): {b['payload']['introduction'][:60]}…",
            f"- eval 容量: {len(code) // 1024}KB（转义后 {len(esc(code)) // 1024}KB）",
            "",
        ]
        short = [(i + 1, s) for i, s in enumerate(b["sizes"]) if s < 200]
        if short:
            report.append(f"- ⚠️ 短章(<200字): {short}（守卫仍会放行≥30字章，自行斟酌）\n")

    (out_dir / "evals.json").write_text(json.dumps(evals, ensure_ascii=False, indent=1))
    (out_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"[ok] {len(books)} 本备料完成 → {out_dir}/evals.json（{len(evals)} 条 eval，含 precheck）")
    for b in books:
        print(f"  - {b['title']}: {len(b['chapters'])}章 {sum(b['sizes'])}字")


if __name__ == "__main__":
    main()
