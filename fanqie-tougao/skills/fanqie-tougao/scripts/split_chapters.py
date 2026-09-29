#!/usr/bin/env python3
"""把单个长篇稿件按章节标记拆成 JSON，供番茄投稿助手发布用。

纯 python3 标准库。识别的章节标题行：
  - "第X章/节/卷/回"（中文数字或阿拉伯数字），如：第十二章 风雪夜归 / 第3章 xxx
  - 楔子 / 序章 / 引子 / 序言 / 尾声 / 终章 / 番外（可带标题）
  - markdown 标题行（# ## ###）若其文本符合上述模式，或位于文档开头作为书名
用法:
  python3 split_chapters.py 稿件.txt -o /tmp/fanqie_chapters.json
  python3 split_chapters.py 稿件.txt --heading-pattern '^卷[一二三]'
输出 JSON: {source, total_chars, chapter_count, chapters:[{index,title,char_count,content}], warnings:[...]}
"""
import argparse
import json
import re
import sys

DEFAULT_PATTERN = (
    r"^\s*(?:#{1,3}\s*)?"                       # 允许 markdown 前缀
    r"("
    r"第\s*[0-9零一二三四五六七八九十百千万两]+\s*[章节卷回][^\n，。！？]{0,40}"
    r"|楔子[^\n，。！？]{0,40}"
    r"|序章[^\n，。！？]{0,40}"
    r"|序言[^\n，。！？]{0,40}"
    r"|引子[^\n，。！？]{0,40}"
    r"|尾声[^\n，。！？]{0,40}"
    r"|终章[^\n，。！？]{0,40}"
    r"|番外[^\n，。！？]{0,40}"
    r")\s*$"
)

WARN_SHORT = 500    # 字数低于此值：可能是标记噪音或空章
WARN_LONG = 15000   # 字数高于此值：可能漏拆（两章并一章）


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig") as f:  # utf-8-sig 顺带去 BOM
        return f.read()


def split_chapters(text: str, pattern: str):
    rx = re.compile(pattern)
    chapters = []  # (title, [lines])
    title = "（开头未标记部分）"
    body: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        m = rx.match(line)
        if m:
            if "".join(body).strip():
                chapters.append((title, body))
            title = m.group(1).strip()
            body = []
        else:
            body.append(raw)
    if "".join(body).strip():
        chapters.append((title, body))
    return chapters


def clean_body(lines) -> str:
    return "\n".join(lines).strip("\n").replace("\u3000\u3000", "\u3000\u3000").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="长篇稿件拆章")
    ap.add_argument("input", help="稿件路径 (txt/md)")
    ap.add_argument("-o", "--output", required=True, help="输出 JSON 路径")
    ap.add_argument("--heading-pattern", default=None,
                    help="自定义章节标题正则（默认识别 第X章/楔子/番外 等）")
    args = ap.parse_args()

    try:
        text = read_text(args.input)
    except OSError as e:
        print(f"[ERROR] 读不到稿件: {e}", file=sys.stderr)
        return 1

    pattern = args.heading_pattern or DEFAULT_PATTERN
    try:
        raw = split_chapters(text, pattern)
    except re.error as e:
        print(f"[ERROR] heading-pattern 无效: {e}", file=sys.stderr)
        return 1

    chapters, warnings = [], []
    for i, (title, lines) in enumerate(raw, 1):
        content = clean_body(lines)
        n = len(content.replace("\n", "").replace(" ", ""))
        chapters.append({"index": i, "title": title, "char_count": n, "content": content})
        if n < WARN_SHORT:
            warnings.append(f"第{i}章「{title}」仅{n}字，偏短：确认是正文还是标记噪音")
        elif n > WARN_LONG:
            warnings.append(f"第{i}章「{title}」达{n}字，过长：可能两章并一章漏拆")

    if not chapters:
        warnings.append("一个章节标记都没认出来：检查标题写法，或用 --heading-pattern 自定义")
    elif chapters[0]["title"].startswith("（开头") and chapters[0]["char_count"] > WARN_LONG:
        warnings.append("开头有一大段未标记文字：可能序章/简介没被识别")

    out = {
        "source": args.input,
        "total_chars": len(text.replace("\n", "").replace(" ", "")),
        "chapter_count": len(chapters),
        "chapters": chapters,
        "warnings": warnings,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print(f"拆出 {len(chapters)} 章，共 {out['total_chars']} 字 → {args.output}")
    for w in warnings:
        print(f"[WARN] {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
