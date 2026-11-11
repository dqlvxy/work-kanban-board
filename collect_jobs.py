# -*- coding: utf-8 -*-
"""工作看板·岗位采集器
数据源（均为公开可访问的招聘列表页，服务器端可直接读取）：
  猎聘 城市机械设计专场页 / 前程无忧工程师招聘网城市机械页
只收录机械/结构/非标相关岗位，字段缺失一律留空，不编造。
"""
import re, json, datetime, urllib.request, sys

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CST = datetime.timezone(datetime.timedelta(hours=8))

SOURCES = [
    # (来源名, 城市码, url, 编码)
    ("猎聘", "xa", "https://www.liepin.com/city-xian/zpjixieyanfasheji112/", "utf-8"),
    ("猎聘", "sz", "https://www.liepin.com/city-sz/zpjixieyanfasheji112/", "utf-8"),
    ("前程无忧", "xa", "https://mgongchengshi.51job.com/xian/jixiegcs/", "gbk"),
    ("前程无忧", "sz", "https://mgongchengshi.51job.com/shenzhen/jixiegcs/", "gbk"),
]

KW = ("机械", "结构", "非标", "治具", "工装", "夹具", "机构", "自动化设备", "整机")

def fetch(url, enc):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    try:
        return raw.decode(enc, "ignore")
    except Exception:
        return raw.decode("utf-8", "ignore")

def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()

def parse_liepin(html, city):
    out = []
    for blk in re.split(r'class="job-card-pc-container"', html)[1:]:
        m = re.search(r'href="(https://www\.liepin\.com/job/\d+\.shtml)"', blk)
        if not m:
            continue
        link = m.group(1)
        t = re.search(r'<div title="(.+?)" class="ellipsis-1">', blk)
        role = clean(t.group(1)) if t else ""
        if not role or not any(k in role for k in KW):
            continue
        area = ""
        a = re.search(r'<span class="dq-bracket">【</span>\s*<span class="ellipsis-1">(.+?)</span>', blk, re.S)
        if a:
            area = clean(a.group(1))
        pay = ""
        p = re.search(r'<span class="job-salary">(.+?)</span>', blk)
        if p:
            pay = clean(p.group(1))
        tags = [clean(x) for x in re.findall(r'<span class="labels-tag"[^>]*>(.*?)</span>', blk, re.S)]
        exp = tags[0] if tags else ""
        edu = tags[1] if len(tags) > 1 else ""
        co = ""
        c = re.search(r'<span class="company-name ellipsis-1">(.+?)</span>', blk, re.S)
        if c:
            co = clean(c.group(1))
        out.append(dict(city=city, co=co, role=role, area=area.replace("【", "").replace("】", ""),
                        exp=exp, edu=edu, pay=pay, src="猎聘", link=link))
    return out

def parse_51job(html, city):
    out = []
    for blk in re.split(r'<a href="(https://m?search\.51job\.com/jobs/[^"]+)" class="e"', html)[1:]:
        pass
    # 按岗位卡片链接切块（含捕获组，需成对处理）
    parts = re.split(r'(<a href="(https://m?search\.51job\.com/jobs/[^"]+)" class="e")', html)
    idx = 1
    while idx < len(parts):
        link = parts[idx + 1]
        body = parts[idx + 2] if idx + 2 < len(parts) else ""
        idx += 3
        n = re.search(r'class="t1 jname at">(.*?)</div>', body, re.S)
        role = clean(n.group(1)) if n else ""
        if not role or not any(k in role for k in KW):
            continue
        sal = re.search(r'class="t2 sal at">(.*?)</span>', body, re.S)
        pay = clean(sal.group(1)) if sal else ""
        tag = re.findall(r'<span>(.*?)</span>', body, re.S)
        exp = clean(tag[0]) if tag else ""
        edu = clean(tag[1]) if len(tag) > 1 else ""
        co = area = ""
        pre = html[:html.find(link)] if link in html else ""
        cm = re.findall(r'class="t1 cname at">(.*?)</div>', pre, re.S)
        am = re.findall(r'class="t2 area at">(.*?)</span>', pre, re.S)
        if cm:
            co = re.split(r'\s+', clean(cm[-1]))[0]
        if am:
            area = clean(am[-1])
        out.append(dict(city=city, co=co, role=role, area=area, exp=exp, edu=edu,
                        pay=pay, src="前程无忧", link=link))
    return out

def score_of(pay):
    nums = [int(x) for x in re.findall(r"\d{2,3}", pay or "")][:2]
    if not nums:
        return 55
    hi = max(nums)
    if "年" in (pay or ""):
        hi = int(hi / 12)
    return max(40, min(99, 40 + hi))

def main():
    now = datetime.datetime.now(CST)
    addAt = now.strftime("%Y-%m-%d %H:%M")
    rows = []
    ok_src = 0
    for src, city, url, enc in SOURCES:
        try:
            html = fetch(url, enc)
            rows += parse_liepin(html, city) if src == "猎聘" else parse_51job(html, city)
            ok_src += 1
            print("[ok]", src, city, len(rows))
        except Exception as e:
            print("[fail]", src, city, str(e)[:60], file=sys.stderr)

    # 去重：同公司同岗位
    seen, uniq = set(), []
    for r in rows:
        k = (r["co"], r["role"], r["city"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)

    maxpay = {}
    jobs = []
    for i, r in enumerate(uniq, 1):
        eduOk = ("大专" in r["edu"] or "不限" in r["edu"] or not r["edu"])
        s = score_of(r["pay"])
        jobs.append(dict(
            id=i, city=r["city"], co=r["co"] or "（用人单位未展示）", coTag="",
            role=r["role"], area=r["area"], exp=r["exp"], edu=r["edu"] or "未标注",
            eduOk=eduOk, pay=r["pay"] or "面议", payNote="", score=s,
            g="core" if s >= 80 else "near", cls="g" if eduOk else "",
            chips=["大专可投"] if eduOk else ["学历待确认"],
            why="",
            src=r["src"], srcUrl=r["link"], link=r["link"],
            postAt="", addAt=addAt,
        ))
    jobs.sort(key=lambda j: (j["city"], -j["score"]))
    per_city, kept = {}, []
    for j in jobs:
        n = per_city.get(j["city"], 0)
        if n >= 15:
            continue
        per_city[j["city"]] = n + 1
        kept.append(j)
    jobs = kept
    for i, j in enumerate(jobs, 1):
        j["id"] = i
    data = dict(updated=addAt, round=0, jobs=jobs)
    with open("jobs.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("采集完成：源 %d/%d，岗位 %d 条" % (ok_src, len(SOURCES), len(jobs)))
    return 0 if ok_src else 1

if __name__ == "__main__":
    sys.exit(main())
