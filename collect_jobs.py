# -*- coding: utf-8 -*-
"""工作看板·岗位采集器
数据源（均为公开可访问的招聘列表页，服务器端可直接读取）：
  猎聘 城市机械设计专场页 / 前程无忧工程师招聘网城市机械页
  BOSS直聘收录快照 boss-snapshot.json（搜索引擎收录的 zhipin.com 公开页原文，
    由 import_boss_snapshot.py 从 11 列 CSV 清洗生成，非实时在招数据）
只收录机械/结构/非标相关岗位，字段缺失一律留空，不编造。
"""
import re, json, datetime, urllib.request, urllib.parse, sys, time, os

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

# ===== BOSS 直聘：普通来源之一，不置顶、不按时间下架 =====
# 机房 IP 直连 BOSS 会被风控（wapi/joblist.json 返回 code=37「环境存在异常」），
# 因此 BOSS 岗位由杜哥手机截图批量录入 jobs-boss.json。
# 它和猎聘／前程无忧一视同仁：按首次收录时间排先后，只在超过每城上限时被挤掉。
BOSS_FILE = "jobs-boss.json"
BOSS_CITY_CODE = {"xa": "101110100", "sz": "101280600", "ak": "101110900"}

# 2026-11-11 收录快照：50 条西安机械设计岗（原 11 列全部保留 + 看板映射字段）。
# 每轮采集都重新读入，避免 Actions 定时跑时把这批岗位冲掉。
SNAPSHOT_FILE = "boss-snapshot.json"

# 首次收录台账：记录所有「见过」的岗位 (公司,岗位,城市) 及首次时间。
# 没有它时，外部源每轮抓到的上百个岗位只要在上一版 jobs.json 里没出现过，
# 就会被重新当成「本轮新岗位」，10 分钟一轮把看板整批翻一遍。
# 台账让「新」只属于真正第一次出现的岗位；老岗位沿用首次时间，不刷新。
SEEN_LOG = "seen-log.json"
SEEN_LOG_MAX = 6000

# ===== 看板容量规则（用户 2026-11-11 12:25 明确要求） =====
# 取消「7 天自动下架」：任何岗位都不因「多久没出现」而下架。
# 西安 / 深圳 / 安康各自最多 50 条；超过 50 时按首次收录时间倒序，
# 最新的留下、最旧的被挤掉 —— 这是「以新换旧」唯一的淘汰方式。
NEW_WINDOW_DAYS = 1   # 24 小时内首次收录标「新」，只用于展示
PER_CITY = 50         # 每城上限（xa / sz / ak 各自独立计算）

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
               "前端", "后端", "Java", "java", "Python",
               "投研", "行业研究", "分析师", "投资经理")

def load_boss(addAt):
    """读 BOSS 岗位池：分数/理由/话术均已人工核对，服务端不重算，只做规范化。
    addAt / firstSeen / lastSeen 全部固定为录入时间，绝不每轮刷新，
    否则岗位会一直被当成「刚抓到」，排序会失真。"""
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
            isNew=False, stale=False,
            addAt=j.get("addAt") or addAt,
            firstSeen=j.get("firstSeen") or j.get("addAt") or addAt,
            lastSeen=j.get("lastSeen") or j.get("addAt") or addAt,
        )
        out.append(item)
    return out


def load_snapshot():
    """读 BOSS 收录快照（已是看板字段），只做规范化，不重算分数/理由/话术。
    数据来自搜索引擎收录的 zhipin.com 公开页原文，不是实时在招数据。"""
    try:
        with open(SNAPSHOT_FILE, encoding="utf-8") as f:
            src = json.load(f)
    except Exception as e:
        print("[fail] BOSS 收录快照读取失败 %s" % str(e)[:60], file=sys.stderr)
        return []
    out = []
    for j in src.get("jobs", []):
        co = (j.get("co") or "").strip()
        role = (j.get("role") or "").strip()
        if not co or not role:
            continue
        item = dict(j)
        link = j.get("link") or boss_search_url(co, j.get("city"))
        item.update(src="BOSS直聘", srcUrl=link, link=link, boss=True,
                    快照=True, 公司名未显示=bool(j.get("公司名未显示")),
                    Boss直聘投递入口=link)
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

# ===== 排序与容量：首次收录时间决定先后，超过每城上限才淘汰 =====
def seen_time(j):
    return parse_dt(j.get("firstSeen") or j.get("addAt") or "")

def new_days(j, now):
    t = seen_time(j)
    if not t:
        return 999.0
    return (now - t).total_seconds() / 86400.0

def is_fresh(j, now):
    return 0 <= new_days(j, now) <= NEW_WINDOW_DAYS

def on_board_days(j, now):
    """在榜天数：从首次收录算起，仅用于手机端展示，不触发任何下架"""
    t = seen_time(j)
    if not t:
        return 0
    return max(0, int((now - t).total_seconds() / 86400.0))

def rank_key(j, now):
    """排序规则（2026-11-11 杜哥定，压过旧的「最新收录优先」）：
    ① 来源优先 —— BOSS直聘（含收录快照 / 岗位池）永远排在其它源前面；
    ② 组内按简历匹配度 score 降序 —— 越贴杜全龙非标自动化/治具主线的越靠前；
    ③ 同分再按首次收录时间倒序（新的在前）；
    ④ 最后按公司名，保证结果稳定可复现。
    注意：score 必须两套口径可比 —— BOSS 快照由 import_boss_snapshot.py 算、
    外部源由 judge() 算，均落在 35~97 区间。"""
    t = seen_time(j)
    return (0 if is_boss(j) else 1,
            -int(j.get("score") or 0),
            -(t.timestamp() if t else 0),
            j.get("co") or "")

def main():
    now = datetime.datetime.now(CST)
    addAt = now.strftime("%Y-%m-%d %H:%M")

    # 旧快照：源站偶发失败时保住手机上已有的岗位
    old_map, old_updated = {}, None
    try:
        with open("jobs.json", encoding="utf-8") as f:
            old_data = json.load(f)
        old_updated = old_data.get("updated")
        for j in old_data.get("jobs", []):
            old_map[job_key(j.get("co"), j.get("role"), j.get("city"))] = j
    except Exception:
        pass

    # 首次收录台账。首次建立时，把本轮之前就已抓到过的岗位统一记为
    # 上一版 jobs.json 的更新时间，避免台账初始化瞬间把上百个老岗位全标成「新」。
    log_existed = os.path.exists(SEEN_LOG)
    seen_log = {}
    if log_existed:
        try:
            with open(SEEN_LOG, encoding="utf-8") as f:
                raw_log = json.load(f).get("seen", {})
            seen_log = {tuple(k.split("\t", 2)): v for k, v in raw_log.items()}
        except Exception:
            seen_log = {}
    legacy_time = addAt if log_existed else (old_updated or addAt)

    def first_seen_of(k, old, fallback):
        t = seen_log.get(k) or (old or {}).get("firstSeen") or legacy_time or fallback
        seen_log[k] = t
        return t

    # ① BOSS 岗位池 + 收录快照：都是普通来源，不按时间下架、不置顶
    boss_rows = load_boss(addAt)
    snap_rows = load_snapshot()
    print("[boss] BOSS岗位池 %d 条 + 收录快照 %d 条（不置顶、不按时间下架）" %
          (len(boss_rows), len(snap_rows)))

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

    # 外部源全挂也照常输出（BOSS 池 + 旧快照），不让手机空白
    if not ok_src:
        print("外部源全部失败，仅输出 BOSS 池与旧快照", file=sys.stderr)

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
            firstSeen=first_seen_of(k, old, addAt),
            isNew=(old is None), stale=False,
        )

    # BOSS 岗位没有特权：同名条目以本轮公开源实抓结果为准，BOSS 只补空缺。
    # 收录快照按文档增量规则：主键 (公司, 岗位, 薪资) 已存在的条目，
    # 只刷新「来源页 / 投递入口 / 数据时间」，沿用原 firstSeen，不重复插入。
    for b in boss_rows + snap_rows:
        k = job_key(b["co"], b["role"], b["city"])
        if k in fresh:
            continue
        old = old_map.get(k)
        if old and b.get("快照"):
            keep = dict(old)
            keep.update(
                link=b["link"], srcUrl=b["srcUrl"],
                Boss直聘投递入口=b.get("Boss直聘投递入口") or b["link"],
                来源页=b.get("来源页") or keep.get("来源页", ""),
                数据时间=b.get("数据时间") or "2026-11-11",
                快照=True, 公司名未显示=bool(b.get("公司名未显示")),
                stale=False,
            )
            keep.setdefault("firstSeen", keep.get("addAt") or addAt)
            seen_log.setdefault(k, keep["firstSeen"])
            fresh[k] = keep
            continue
        b["id"] = 0
        # BOSS 池 / 收录快照自带固定的首次收录时间，不用台账初始化时间覆盖，
        # 否则刚灌入的 BOSS 快照会被降级成「上一轮老岗位」。
        b["firstSeen"] = seen_log.get(k) or (old or {}).get("firstSeen") or b["firstSeen"]
        seen_log[k] = b["firstSeen"]
        fresh[k] = b

    # 旧岗位本轮没抓到 → 照样留在看板。时间再久也不自动下架，
    # 也不二次过滤（进快照时已过滤过）；唯一淘汰方式＝超过每城上限被挤掉。
    merged = dict(fresh)
    for k, oldj in old_map.items():
        if k in merged:
            continue
        role = oldj.get("role") or ""
        keep = dict(oldj)
        keep["stale"] = True
        keep["isNew"] = False
        keep.setdefault("firstSeen", keep.get("addAt") or addAt)
        keep.setdefault("msg", build_msg(role, oldj.get("co", ""), oldj.get("city", ""), []))
        if oldj.get("city") == "ak" and "宽口径" not in (keep.get("why") or ""):
            keep["score"] = min(int(keep.get("score") or 55), 55)
            keep["why"] = (keep.get("why") or "") + " 安康本地机械岗很少，这条是宽口径抓到的低相关岗位，只作参考。"
        merged[k] = keep

    # 每条岗位只标「是不是 24 小时内新收录」，不再写「剩余天数」——没有有效期
    for j in merged.values():
        j["isNew"] = is_fresh(j, now)
        j["在榜天数"] = on_board_days(j, now)
        j.pop("剩余天数", None)

    # 排序：首次收录时间倒序（新在前）→ 同批按匹配度；来源完全不参与排序（无置顶）
    # 每城最多 PER_CITY 条，只有超过上限才会把最旧的岗位挤掉
    allj = sorted(merged.values(), key=lambda j: (j["city"],) + rank_key(j, now))
    per_city, kept = {}, []
    for j in allj:
        n = per_city.get(j["city"], 0)
        if n >= PER_CITY:
            continue
        per_city[j["city"]] = n + 1
        kept.append(j)
    for i, j in enumerate(kept, 1):
        j["id"] = i
    boss_cnt = len([j for j in kept if is_boss(j)])
    snap_cnt = len([j for j in kept if j.get("快照")])
    new_cnt = len([j for j in kept if j["isNew"]])
    evicted = len(merged) - len(kept)      # 超过每城上限、被新岗位挤掉的旧岗位
    data = dict(updated=addAt, round=0, bossCount=boss_cnt, newCount=new_cnt,
                snapshotCount=snap_cnt, snapshotDate="2026-11-11",
                newDays=NEW_WINDOW_DAYS, perCity=PER_CITY,
                evicted=evicted, jobs=kept)
    with open("jobs.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 台账落盘：只按 (公司,岗位,城市) 存首次时间，超量时保留最近收录的
    if len(seen_log) > SEEN_LOG_MAX:
        recent = sorted(seen_log.items(), key=lambda kv: kv[1], reverse=True)[:SEEN_LOG_MAX]
        seen_log = dict(recent)
    with open(SEEN_LOG, "w", encoding="utf-8") as f:
        json.dump({"updated": addAt, "count": len(seen_log),
                   "seen": {"\t".join(k): v for k, v in seen_log.items()}},
                  f, ensure_ascii=False, indent=1)
    by_city = {}
    for j in kept:
        by_city[j["city"]] = by_city.get(j["city"], 0) + 1
    print("采集完成：外部源 %d/%d，岗位 %d 条（新岗位 %d，BOSS %d 条 / 其中收录快照 %d 条，"
          "均不置顶；超过每城 %d 条挤掉 %d 条旧岗位），城市 %s" %
          (ok_src, len(SOURCES), len(kept), new_cnt, boss_cnt, snap_cnt,
           PER_CITY, evicted, by_city))
    return 0

if __name__ == "__main__":
    sys.exit(main())
