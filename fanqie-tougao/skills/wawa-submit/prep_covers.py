#!/usr/bin/env python3
"""蛙蛙侧换封准备：墨语已选封面 -> 下载转jpg -> 生成 upload+PUT evals。
只处理非 reviewing 书；reviewing 平台锁定换不了。"""
import base64, hashlib, json, re, subprocess, sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL))
from prepare_batch import mcp_call, download, OK, BAD, WARN, END

WORK = Path("/tmp/wawa_cover")
OUT = WORK / "work"
mylist = json.loads((WORK / "mylist.json").read_text())

known_pids = sorted({b["pid"] for b in mylist if b["pid"]})
cand_pids = known_pids + [13, 14, 15, 17, 19, 21, 24, 25, 26, 28, 30]
cand_pids = sorted(set(cand_pids))

links_map, title_map = {}, {}
print("== get_export_links 探测 ==")
for pid in cand_pids:
    try:
        links = mcp_call("get_export_links", {"project_id": pid})
    except Exception as e:
        print(f"[{pid}] ERR {str(e)[:80]}")
        continue
    if not isinstance(links, dict) or "title" not in links:
        print(f"[{pid}] 异常响应: {json.dumps(links, ensure_ascii=False)[:100]}")
        continue
    links_map[pid] = links
    title_map[pid] = links["title"]
    print(f"[{pid}] {links['title']}  cover={'有' if links.get('cover_url') else '无'}")

# null-pid 书按标题匹配（精确优先，再去标点子串）
def norm(s):
    return re.sub(r"[^\w\u4e00-\u9fff]", "", s)
t2p = {}
for pid, t in title_map.items():
    t2p.setdefault(norm(t), pid)

for b in mylist:
    if b["pid"]:
        continue
    pid = t2p.get(norm(b["title"]))
    if pid is None:
        for npid, nt in title_map.items():
            if norm(b["title"]) and norm(b["title"]) in norm(nt):
                pid = npid
                break
    b["pid"] = pid
    b["matched_by"] = "title" if pid else "NONE"
    print(f"[sid {b['sid']}] {b['title']} -> pid {pid} ({b.get('matched_by')})")
(WORK / "mylist.json").write_text(json.dumps(mylist, ensure_ascii=False, indent=1))  # 匹配结果写回，防下游映射丢 pid

evals = [{"op": "eval", "stage": "precheck", "sid": 0, "note": "登录+域核验",
          "code": "(async()=>{if(!location.origin.includes('wawawriter'))return{error:'wrong origin'};"
                  "const j=await fetch('/wrhp-api/api/v1/submission/novel/my_list',{method:'POST',"
                  "credentials:'include',headers:{'Content-Type':'application/json'},"
                  "body:JSON.stringify({page:1,page_size:100})}).then(x=>x.json());"
                  "const d=j.data||{};const arr=(d.items||d.list)||(Array.isArray(d)?d:[]);"
                  "return{code:j.code,total:d.total,loggedIn:document.body.innerText.length>0}})()"}]
report = ["# 蛙蛙换封准备报告\n"]
skipped = []
for b in mylist:
    sid, pid, title = b["sid"], b["pid"], b["title"]
    if not pid:
        skipped.append(f"sid {sid} {title}: 墨语无对应项目，跳过")
        continue
    links = links_map[pid]
    cover_url = links.get("cover_url")
    safe = re.sub(r"[^\w\u4e00-\u9fff]", "", links["title"])[:30]
    png_path = OUT / f"{pid}_{safe}.png"
    jpg_path = OUT / f"{pid}_cover.jpg"
    if not cover_url:
        skipped.append(f"sid {sid} {title} (P{pid}): 墨语无封面，跳过")
        continue
    download(cover_url, png_path)
    raw = png_path.read_bytes()
    if raw[:1] == b"{":
        skipped.append(f"sid {sid} {title} (P{pid}): 封面接口回JSON(无封面)，跳过")
        continue
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "75",
                    "-Z", "1024", str(png_path), "--out", str(jpg_path)],
                   check=True, capture_output=True)
    b64 = base64.b64encode(jpg_path.read_bytes()).decode()
    md5 = hashlib.md5(jpg_path.read_bytes()).hexdigest()
    code = f"""(async()=>{{
  if(!location.origin.includes("wawawriter"))return{{error:"wrong origin"}};
  const b64="{b64}";
  if(b64.length!=={len(b64)})return{{error:"注入不完整"}};
  const bin=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
  const fd=new FormData();
  fd.append("file",new File([bin],"cover.jpg",{{type:"image/jpeg"}}));
  fd.append("file_secret","{md5}");
  const up=await fetch("/wrhp-api/api/v1/file/simpleupload",{{method:"POST",body:fd,credentials:"include"}}).then(x=>x.json());
  const url=(up.data&&(up.data.result||up.data.url))||null;
  if(!url)return{{upload:{{code:up.code,msg:(up.message||"").slice(0,120)}}}};
  const j=await fetch("/wrhp-api/api/v1/submission/novel/my_list",{{method:"POST",credentials:"include",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{page:1,page_size:100}})}}).then(x=>x.json());
  const d=j.data||{{}};const arr=(d.items||d.list)||(Array.isArray(d)?d:[]);
  const it=arr.find(x=>x.submission_id==={sid});
  if(!it)return{{upload:{{code:up.code}},url,error:"my_list未找到sid {sid}"}};
  const intro=(it.introduction||"").trim()||"暂无简介";
  // 20260916 实测：只发 cover+introduction 被 500「内部校验【title】异常」——
  // 五字段白名单除 cover 外全部取 my_list 当前值原样回传
  const put=await fetch("/wrhp-api/api/v1/submission/novel/{sid}",{{method:"PUT",credentials:"include",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{title:it.title,label_ids:it.label_ids||[],cover:url,introduction:intro,pen_name:it.pen_name||undefined}})}}).then(x=>x.json());
  const j2=await fetch("/wrhp-api/api/v1/submission/novel/my_list",{{method:"POST",credentials:"include",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{page:1,page_size:100}})}}).then(x=>x.json());
  const d2=j2.data||{{}};const arr2=(d2.items||d2.list)||(Array.isArray(d2)?d2:[]);
  const it2=arr2.find(x=>x.submission_id==={sid});
  return{{sid:{sid},title:it.title,status:it.status,upload:{{code:up.code}},put:{{code:put.code,msg:(put.message||"").slice(0,120)}},
    verified:!!it2&&it2.cover===url,introLen:intro.length,titleOk:!it2||it2.title===it.title}};
}})()"""
    evals.append({"op": "eval", "stage": "cover_update", "sid": sid, "pid": pid,
                  "note": title, "code": code})
    kb = len(code) // 1024
    report.append(f"- sid {sid} <- P{pid} {links['title']}: jpg {jpg_path.stat().st_size//1024}KB md5 `{md5}` eval {kb}KB")
    print(f"[{OK}✓{END}] sid {sid} <- P{pid} {links['title']} jpg {jpg_path.stat().st_size//1024}KB eval {kb}KB")

if skipped:
    report.append("\n## 跳过\n" + "\n".join("- " + s for s in skipped))
    print("\n".join("跳过: " + s for s in skipped))
(WORK / "evals.json").write_text(json.dumps(evals, ensure_ascii=False, indent=1))
(WORK / "report.md").write_text("\n".join(report) + "\n")
print(f"\n产物: {WORK}/evals.json  共 {len(evals)} 条（1 precheck + {len(evals)-1} 本）")
