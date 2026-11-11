# -*- coding: utf-8 -*-
"""工作看板·岗位采集器
数据源（均为公开可访问的招聘列表页，服务器端可直接读取）：
  猎聘 城市机械设计专场页 / 前程无忧工程师招聘网城市机械页
只收录机械/结构/非标相关岗位，字段缺失一律留空，不编造。
"""
import re, json, datetime, urllib.request, urllib.parse, sys, time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CST = datetime.timezone(datetime.timedelta(hours=8))

SOURCES = [
    ("猎聘", "xa", "https://www.liepin.com/city-xian/zpjixieyanfasheji112/", "utf-8"),
    ("猎聘", "xa", "https://www.liepin.com/city-xian/zpjixiesheji/", "utf-8"),
    ("猎聘", "xa", "https://www.liepin.com/city-xian/zpjiegousheji/", "utf-8"),
    ("猎聘", "xa", "https://www.liepin.com/city-xian/zpjixiegongchengshi/", "utf-8"),
    ("猎聘", "xa", "https://www.liepin.com/city-xian/zpjigongchengshi/", "utf-8"),
    ("猎聘", "xa", "https://www.liepin.com/city-xian/zpjixiezhizao/", "utf-8"),
    ("猎聘", "sz", "https://www.liepin.com/city-sz/zpjixieyanfasheji112/", "utf-8"),
    ("猎聘", "sz", "https://www.liepin.com/city-sz/zpjixiesheji/", "utf-8"),
    ("猎聘", "sz", "https://www.liepin.com/city-sz/zpjiegousheji/", "utf-8"),
    ("猎聘", "sz", "https://www.liepin.com/city-sz/zpjixiegongchengshi/", "utf-8"),
    ("猎聘", "sz", "https://www.liepin.com/city-sz/zpjigongchengshi/", "utf-8"),
    ("猎聘", "sz", "https://www.liepin.com/city-sz/zpjixiezhizao/", "utf-8"),
    ("前程无忧", "xa", "https://mgongchengshi.51job.com/xian/jixiegcs/", "gbk"),
    ("前程无忧", "sz", "https://mgongchengshi.51job.com/shenzhen/jixiegcs/", "gbk"),
    ("前程无忧", "ak", "https://mgongchengshi.51job.com/ankang/jixiegcs/", "gbk"),
]

# ===== BOSS 直聘：第一优先来源 =====
# 机房 IP 直连 BOSS 会被风控（wapi/joblist.json 返回 code=37「环境存在异常」，
# SEO 详情页与搜索收录也拿不到岗位），因此 BOSS 岗位由杜哥手机截图批量录入
# jobs-boss.json，服务端每轮「最先读取 + 各城置顶 + 永不过期」。
BOSS_FILE = "jobs-boss.json"
BOSS_CITY_CODE = {"xa": "101110100", "sz": "101280600", "ak": "101110900"}

def boss_search_url(co, city):
    """BOSS 岗位没有可直连详情页时，给一个公司名直达搜索链接，方便手机一键去投"""
    return "https://www.zhipin.com/web/geek/job?query=%s&city=%s" % (
        urllib.parse.quote(co or ""), BOSS_CITY_CODE.get(city, "100010000"))

# 只收机械/结构/治具相关，挡掉「选矿工程师」这类同名不同行的噪声
INCLUDE = ("机械", "结构", "夹具", "治具", "工装", "非标", "自动化", "设备",
           "设计", "工艺", "机电", "模具", "CNC", "cnc", "研发", "制图",
           "测试", "ICT", "FCT", "装配", "产品", "调试", "数控")
EXCLUDE_JOB = ("销售", "采购", "文员", "行政", "财务", "会计", "市场", "客服",
               "司机", "仓管", "业务员", "跟单", "选矿", "采矿", "护士", "教师",
               "厨师", "保安", "美容", "房产", "保险", "快递", "服务员",
               # 含「设计」但不属于机械/结构/治具的跨行岗，别把薪资上限拉虚
               "SoC", "AI Core", "数字设计", "建筑师", "芯片", "IC设计",
               "半导体", "验证工程师", "测试开发", "算法工程师", "软件工程师",
               "前端", "后端", "Java", "java", "Python")

def load_boss(addAt):
    """读 BOSS 岗位池：分数/理由/话术均已人工核对，服务端不重算，只做规范化"""
    try:
        with open(BOSS_FILE, encoding="utf-8") as f:
            src = json.load(f)
    except Exception as e:
        print("[fail] BOSS 岗位池读取失败 %s" % str(e)[:60], file=sys.stderr)
        return []
    out = []
    for j in src.get("jobs", []):
        co = (j.get("co") or "").strip()
        role = (j.get("role") or "").strip()
        if not co or not role or any(k in role for k in EXCLUDE_JOB):
            continue
        link = j.get("link") or boss_search_url(co, j.get("city"))
        sc = int(j.get("score") or 70)
        item = dict(j)
        item.update(
            src="BOSS直聘", srcUrl=link, link=link, boss=True, coTag="",
            pay=j.get("pay") or "面议", payNote=j.get("payNote") or "",
            edu=j.get("edu") or "未标注", eduOk=j.get("eduOk", True), score=sc,
            g=j.get("g") or ("core" if sc >= 78 else "near"), cls=j.get("cls") or "g",
            chips=j.get("chips") or (j.get("tags") or [])[:2],
            why=j.get("why") or "BOSS直聘在招，岗位与你的非标自动化/治具设计主线相关，点开原站看详情。",
            msg=j.get("msg") or "", postAt=j.get("postAt") or "",
            isNew=False, stale=False, addAt=j.get("addAt") or addAt,
            firstSeen=j.get("firstSeen") or j.get("addAt") or addAt, lastSeen=addAt,
        )
        out.append(item)
    return out


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

def build_msg(role, co, city, hits):
    """每个岗位一条定制话术：按岗位名 + 命中的真实简历事实拼，不依赖前端预置库。
    云端每轮都会重编号，写进数据里才不会出现「话术串到别的公司」。"""
    fact = ("其中" + hits[0]) if hits else "主做 ICT/FCT 测试治具与非标整机方案"
    where = {"xa": "在西安正是我的期望城市",
             "sz": "在深圳做了十多年这行，回来就能上手",
             "ak": "安康本地通勤方便"}.get(city, "")
    return ("您好，看到贵司在招「%s」。我有 16 年非标自动化机械设计经验，%s；"
            "SolidWorks 建模出图、BOM 和整机装配调试都能独立跟。%s，学历是大专，"
            "想先把简历和作品集发您看看，方便的话约个时间聊。") % (
            role.replace("（", "(").replace("）", ")")[:24], fact, where)

def parse_dt(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=CST)
    except Exception:
        return None

def job_key(co, role, city):
    return (co or "", role or "", city or "")

def is_boss(j):
    return bool(j.get("boss")) or j.get("src") == "BOSS直聘"

def main():
    now = datetime.datetime.now(CST)
    addAt = now.strftime("%Y-%m-%d %H:%M")

    # 旧快照：源站偶发失败时保住手机上已有的岗位
    old_map = {}
    try:
        with open("jobs.json", encoding="utf-8") as f:
            for j in json.load(f).get("jobs", []):
                old_map[job_key(j.get("co"), j.get("role"), j.get("city"))] = j
    except Exception:
        pass

    # ① BOSS 直聘：第一优先，先入池、置顶、不参与 3 天过期
    boss_rows = load_boss(addAt)
    print("[boss] BOSS直聘优先池 %d 条" % len(boss_rows))

    # ② 其余公开源（猎聘 12 + 前程无忧 3）
    rows, ok_src = [], 0
    for src, city, url, enc in SOURCES:
        before = len(rows)
        try:
            html = fetch(url, enc)
            rows += parse_liepin(html, city) if src == "猎聘" else parse_51job(html, city)
            ok_src += 1
            print("[ok] %s %s 本页 %d 条 / 累计 %d" % (src, city, len(rows) - before, len(rows)))
        except Exception as e:
            print("[fail]", src, city, str(e)[:60], file=sys.stderr)

    # 外部源全挂也照常输出（BOSS 优先池 + 旧快照），不让手机空白
    if not ok_src:
        print("外部源全部失败，仅输出 BOSS 优先池与旧快照", file=sys.stderr)

    # 去重 + 相关性过滤（挡掉「选矿工程师」这类同名不同行噪声）
    seen, uniq = set(), []
    for r in rows:
        role = r["role"]
        # 安康本地机械岗极少：宽口径保留并低分标注，别让这一页空着
        if r["city"] == "ak":
            if any(k in role for k in EXCLUDE_JOB[:12]):
                continue
        elif any(k in role for k in EXCLUDE_JOB) or not any(k in role for k in INCLUDE):
            continue
        k = job_key(r["co"], role, r["city"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)

    fresh = {}
    for r in uniq:
        k = job_key(r["co"], r["role"], r["city"])
        old = old_map.get(k)
        sc, eduOk, hits = judge(r["role"], r["edu"], r["pay"], r["city"])
        why = build_why(r["role"], r["co"], r["edu"], eduOk, r["pay"], r["city"], hits)
        if r["city"] == "ak" and not hits:
            sc = min(sc, 55)
            why += " 安康本地机械岗很少，这条是宽口径抓到的低相关岗位，只作参考，建议同时看西安和深圳。"
        chips = []
        if hits: chips.append(hits[0][:12].replace("、", "").replace("  ", ""))
        fresh[k] = dict(
            id=0, city=r["city"], co=r["co"] or "（用人单位未展示）", coTag="",
            role=r["role"], area=r["area"], exp=r["exp"], edu=r["edu"] or "未标注",
            eduOk=eduOk, pay=r["pay"] or "面议", payNote="", score=sc,
            g="core" if sc >= 78 else "near", cls="g", chips=chips, why=why,
            msg=build_msg(r["role"], r["co"], r["city"], hits),
            src=r["src"], srcUrl=r["link"], link=r["link"], boss=False,
            postAt="", addAt=addAt, lastSeen=addAt,
            firstSeen=(old or {}).get("firstSeen") or addAt,
            isNew=(old is None), stale=False,
        )

    # BOSS 岗位覆盖同名条目：同名时以 BOSS 为准，这就是「优先」
    for b in boss_rows:
        k = job_key(b["co"], b["role"], b["city"])
        old = old_map.get(k)
        b["id"] = 0
        b["isNew"] = old is None
        b["firstSeen"] = (old or {}).get("firstSeen") or b["firstSeen"]
        fresh[k] = b

    # 旧岗位本轮没抓到 → 保留 3 天（BOSS 只认岗位池，避免旧噪声残留）
    merged = dict(fresh)
    for k, oldj in old_map.items():
        if k in merged or is_boss(oldj):
            continue
        role = oldj.get("role") or ""
        if oldj.get("city") == "ak":
            if any(x in role for x in EXCLUDE_JOB[:12]):
                continue
        elif any(x in role for x in EXCLUDE_JOB) or not any(x in role for x in INCLUDE):
            continue
        last = parse_dt(oldj.get("lastSeen") or oldj.get("addAt") or "")
        if last and (now - last).total_seconds() > 3 * 24 * 3600:
            continue
        keep = dict(oldj)
        keep["stale"] = True
        keep["isNew"] = False
        keep["boss"] = False
        keep.setdefault("msg", build_msg(role, oldj.get("co", ""), oldj.get("city", ""), []))
        if oldj.get("city") == "ak" and "宽口径" not in (keep.get("why") or ""):
            keep["score"] = min(int(keep.get("score") or 55), 55)
            keep["why"] = (keep.get("why") or "") + " 安康本地机械岗很少，这条是宽口径抓到的低相关岗位，只作参考。"
        merged[k] = keep

    # BOSS 全部置顶，其余按匹配度；每城 40 条（给 12 条 BOSS 留足位置）
    allj = sorted(merged.values(), key=lambda j: (
        0 if is_boss(j) else 1, -int(j.get("score", 0)), j.get("co", "")))
    per_city, kept = {}, []
    for j in allj:
        n = per_city.get(j["city"], 0)
        if n >= 40:
            continue
        per_city[j["city"]] = n + 1
        kept.append(j)
    kept.sort(key=lambda j: (j["city"], 0 if is_boss(j) else 1,
                             -int(j.get("score", 0))))
    for i, j in enumerate(kept, 1):
        j["id"] = i
    boss_cnt = len([j for j in kept if is_boss(j)])
    data = dict(updated=addAt, round=0, bossCount=boss_cnt, jobs=kept)
    with open("jobs.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    by_city = {}
    for j in kept:
        by_city[j["city"]] = by_city.get(j["city"], 0) + 1
    print("采集完成：外部源 %d/%d，岗位 %d 条（BOSS 置顶 %d 条），城市 %s" %
          (ok_src, len(SOURCES), len(kept), boss_cnt, by_city))
    return 0

if __name__ == "__main__":
    sys.exit(main())
