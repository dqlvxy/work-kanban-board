# -*- coding: utf-8 -*-
"""工作看板·岗位采集器
数据源（均为公开可访问的招聘列表页，服务器端可直接读取）：
  猎聘 城市机械设计专场页 / 前程无忧工程师招聘网城市机械页
只收录机械/结构/非标相关岗位，字段缺失一律留空，不编造。
"""
import re, json, datetime, urllib.request, sys, time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CST = datetime.timezone(datetime.timedelta(hours=8))

SOURCES = [
    # (来源名, 城市码, url, 编码)
    ("猎聘", "xa", "https://www.liepin.com/city-xian/zpjixieyanfasheji112/", "utf-8"),
    ("猎聘", "sz", "https://www.liepin.com/city-sz/zpjixieyanfasheji112/", "utf-8"),
    ("前程无忧", "xa", "https://mgongchengshi.51job.com/xian/jixiegcs/", "gbk"),
    ("前程无忧", "sz", "https://mgongchengshi.51job.com/shenzhen/jixiegcs/", "gbk"),
    ("前程无忧", "ak", "https://mgongchengshi.51job.com/ankang/jixiegcs/", "gbk"),
]


# ===== 杜全龙画像（来自 2026-11 简历 + 非标自动化作品集，仅用于本地匹配打分） =====
PROFILE = {
    "years": 16,              # 16 年经验（简历）
    "edu": "大专",            # 广东南粤科技学院 机械制造及其自动化
    "cities": ["xa", "sz", "ak"],
    "prefer_city": "xa",      # 简历求职意向：西安
}

# 命中即加分的能力簇：(权重, [关键词], 对应简历事实)
SKILL_CLUSTERS = [
    (22, ["非标自动化", "非标设备", "非标设计", "非标准设备", "非标机械"], "10 年非标治具与非标自动化设备开发"),
    (20, ["工装夹具", "治具", "夹具", "工装"], "手机/手表/耳机 3C 类非标测试治具与工装夹具设计"),
    (20, ["测试治具", "测试设备", "测试方案", "ICT", "FCT", "功能测试", "在线测试"], "精通 ICT/FCT 测试方案与整机测试设备设计"),
    (14, ["FPC", "连接器", "Pogo", "探针", "pogo pin"], "FPC 连接器测试治具、下探针 Pogo Pin 模组设计"),
    (16, ["气动", "气缸", "伺服", "步进电机", "直线导轨", "滚珠丝杆", "电机选型", "丝杆"], "气动回路与气缸/伺服/导轨/丝杆标准件选型"),
    (18, ["SolidWorks", "solidworks", "三维建模", "工程图", "BOM", "3D建模"], "SolidWorks 三维建模、工程图出图与 BOM 输出"),
    (16, ["整机", "整机结构", "整机设计", "结构方案"], "多台非标整机方案设计与落地（CNC上下料、保压拆解、转盘组装）"),
    (14, ["上下料", "移栽", "码垛", "机械手", "机器人", "转盘", "输送线", "回流线"], "双车床机器人上下料、保压盒码垛与回流线机构设计"),
    (12, ["3C", "消费电子", "手机", "智能手表", "耳机", "PCBA", "组装线"], "服务华为/OPPO/小米/比亚迪/伟创力等 3C 头部客户"),
    (12, ["CNC", "机加工", "钣金", "注塑", "加工工艺", "表面处理"], "零件加工工艺、钣金与公差控制经验"),
    (10, ["节拍", "良率", "防呆", "换型", "快换", "稼动"], "节拍匹配、防呆设计、多品种小批量快换产线"),
    (10, ["AGV", "AMR", "自动化产线", "产线", "设备集成"], "自动化设备集成与产线无人化改造"),
]

EDU_本科 = ["本科", "学士", "硕士", "研究生", "博士"]

# 机械行业一律放行，只排除明显非技术职能岗（学历/经验都不作门槛）
EXCLUDE = ("销售","采购","文员","行政","财务","会计","市场","客服","司机","仓管","业务员","跟单")

def fetch(url, enc):
    """带重试的抓取：招聘站偶发超时，单次失败不能整源作废"""
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": "https://www.liepin.com/",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
            txt = raw.decode(enc, "ignore")
            if len(txt) > 15000:
                return txt
            last = Exception("内容过短 %d" % len(txt))
        except Exception as e:
            last = e
        time.sleep(2)
    raise last

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
        if not role or any(k in role for k in EXCLUDE):
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
        if not role or any(k in role for k in EXCLUDE):
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

def pay_hi(pay):
    """从薪资文本里取上限（元/月）"""
    if not pay:
        return 0
    txt = pay.replace("万", "0000").replace("千", "000").replace("K", "000").replace("k", "000")
    nums = [int(x) for x in re.findall(r"\d+", txt)]
    if not nums:
        return 0
    hi = max(nums)
    if "年" in pay:
        hi = int(hi / 12)
    if "万/年" in pay:
        hi = int(hi / 12)
    return hi

def judge(job_role, edu, pay, city, raw_text=""):
    """返回 (分数, 是否学历可投, 命中的能力簇说明)"""
    text = (job_role + " " + (raw_text or "")).lower()
    hits = []
    score = 38
    for w, kws, fact in SKILL_CLUSTERS:
        if any(k.lower() in text for k in kws):
            score += w
            hits.append(fact)

    # 学历只作展示：不参与打分，也不作为投不投的门槛（经验与作品集才是筹码）
    edu_ok = True

    # 城市
    if city == PROFILE["prefer_city"]:
        score += 8
    elif city == "sz":
        score += 3

    # 薪资
    hi = pay_hi(pay)
    if hi >= 30000: score += 8
    elif hi >= 20000: score += 6
    elif hi >= 15000: score += 4
    elif hi >= 12000: score += 2

    return max(35, min(97, score)), edu_ok, hits

def build_why(role, co, edu, edu_ok, pay, city, hits):
    """用命中的真实简历事实拼匹配理由，不写没依据的话"""
    parts = []
    if hits:
        parts.append("岗位要求里的" + "、".join(hits[:3]) + "，你都实打实做过")
    else:
        parts.append("这个岗和你非标自动化/结构设计的主线沾边，但没命中硬技能，属于保守试投")
    if edu and "不限" not in edu and "大专" not in edu:
        parts.append("学历标「%s」，只是明面要求，你 16 年非标经验＋作品集可以硬顶，投不投你自己定" % edu)
    else:
        parts.append("学历「%s」，不设门槛" % (edu or "未标注"))
    hi = pay_hi(pay)
    if hi >= 25000:
        parts.append("薪资上限 %s，是这块的天花板档，值得优先投" % pay)
    elif hi and hi < 10000:
        parts.append("薪资只有 %s，低于你 16 年经验的合理区间，当兜底" % pay)
    if city == "xa":
        parts.append("在西安，正是你简历写的期望城市")
    elif city == "sz":
        parts.append("在深圳，你 2011-2022 年一直在深圳做这行，回来就能上手")
    elif city == "ak":
        parts.append("在安康本地，通勤成本几乎为零")
    return "；".join(parts) + "。"

def main():
    now = datetime.datetime.now(CST)
    addAt = now.strftime("%Y-%m-%d %H:%M")
    rows = []
    ok_src = 0
    for src, city, url, enc in SOURCES:
        before = len(rows)
        try:
            html = fetch(url, enc)
            rows += parse_liepin(html, city) if src == "猎聘" else parse_51job(html, city)
            ok_src += 1
            print("[ok] %s %s 本页 %d 条 / 累计 %d" % (src, city, len(rows) - before, len(rows)))
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

    jobs = []
    for i, r in enumerate(uniq, 1):
        sc, eduOk, hits = judge(r["role"], r["edu"], r["pay"], r["city"])
        why = build_why(r["role"], r["co"], r["edu"], eduOk, r["pay"], r["city"], hits)
        chips = []
        if hits: chips.append(hits[0][:12].replace("、", "").replace("  ", ""))
        jobs.append(dict(
            id=i, city=r["city"], co=r["co"] or "（用人单位未展示）", coTag="",
            role=r["role"], area=r["area"], exp=r["exp"], edu=r["edu"] or "未标注",
            eduOk=eduOk, pay=r["pay"] or "面议", payNote="", score=sc,
            g="core" if sc >= 78 else "near", cls="g",
            chips=chips, why=why,
            src=r["src"], srcUrl=r["link"], link=r["link"],
            postAt="", addAt=addAt,
        ))
    jobs.sort(key=lambda j: (j["city"], -j["score"]))
    per_city, kept = {}, []
    for j in jobs:
        n = per_city.get(j["city"], 0)
        if n >= 20:
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
