# -*- coding: utf-8 -*-
"""把 2026-11-11 端产出的 BOSS直聘「收录快照」CSV 清洗成看板字段。

数据源：搜索引擎收录的 zhipin.com 公开列表页 / 岗位详情页正文快照，
不是实时在招数据。原始 11 列全部保留，不做推测填充。

产出 boss-snapshot.json：
  rows       原始 11 列 + 数据时间（等价 JSON 数组，主清单）
  backup     备选 18 岗原始 11 列 + 数据时间
  jobs       已映射到工作看板字段的岗位数组（供 collect_jobs.py 直接读取）

增量主键：(公司, 岗位名称, 薪资)。已存在的条目只更新
「来源页 / Boss直聘投递入口 / 数据时间」，不重复插入。
"""
import csv, io, json, os, re, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = r"F:\WorkBuddy\2026-11-11-11-35-07"
MAIN_CSV = os.path.join(SRC_DIR, "2026-11-11_电脑WorkBuddy_西安Boss直聘机械设计50岗.csv")
BACK_CSV = os.path.join(SRC_DIR, "2026-11-11_电脑WorkBuddy_西安Boss直聘机械设计备选18岗.csv")
OUT = os.path.join(HERE, "boss-snapshot.json")

SNAP_DATE = "2026-11-11"          # 收录快照日期（数据时间）
CST = datetime.timezone(datetime.timedelta(hours=8))
ADD_AT = datetime.datetime.now(CST).strftime("%Y-%m-%d %H:%M")

COLS = ["序号", "岗位名称", "公司", "薪资", "区域", "经验", "学历", "行业",
        "岗位亮点", "来源页", "Boss直聘投递入口"]

# 公司名原页面未显示时的占位前缀：不是真实公司名，禁止写进公司列当真名
PLACEHOLDER = "Boss列表页·"

# 非设计岗过滤（复用方法文档 4.7）
# 「机加工装夹具设计工程师」这种岗位名里带「机加工」的其实是设计岗，
# 所以含「设计 / 研发」的一律放行，只对纯操作/职能岗生效。
BAD_ROLE = ("室内设计师", "主案设计师", "项目监理", "注册结构工程师", "装配工",
            "质检员", "钳工", "机加工", "设备维修", "电气监理", "装配工程师",
            "装修", "土木", "销售", "采购", "文员", "客服")


def is_bad_role(role):
    if "设计" in role or "研发" in role:
        return False
    return any(k in role for k in BAD_ROLE)


PROFILE_FACT = ("16 年非标机械设计，10 年 3C 测试治具 / ICT / FCT 工装夹具"
                "（华为 / OPPO / 小米 / 比亚迪），SolidWorks 出图、BOM、装配调试独立闭环")


def read_csv(path, has_seq):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        d = {k: (r.get(k) or "").strip() for k in COLS}
        if not has_seq:
            d["序号"] = ""
        if not d["岗位名称"] or not d["公司"]:
            continue
        out.append(d)
    return out


def norm(v):
    """原文没有的字段写「—」或「面议」，不编造"""
    v = (v or "").strip()
    return "—" if v in ("", "—", "-") else v


def pay_num(s):
    """从薪资文本取上限（元/月），用于质量分；不改动展示原文"""
    t = (s or "").replace("万", "0000").replace("千", "000").replace("K", "000").replace("k", "000")
    nums = [int(x) for x in re.findall(r"\d+", t)]
    if not nums:
        return 0
    hi = max(nums)
    if "元/天" in (s or ""):
        hi = hi * 21
    if "年" in (s or ""):
        hi = int(hi / 12)
    return hi


def quality_score(d):
    """方法文档 6.3：只用于排序，不删数据"""
    hi = pay_num(d["薪资"])
    q = 30 if hi >= 20000 else 22 if hi >= 15000 else 14 if hi >= 10000 else (6 if hi > 0 else 0)
    if d["公司"] and not d["公司"].startswith(PLACEHOLDER):
        q += 12
    if d["学历"] in ("大专", "学历不限", "经验不限"):
        q += 10
    if "/job_detail/" in d["Boss直聘投递入口"]:
        q += 8
    if any(k in d["岗位名称"] for k in ("非标", "工装夹具", "机械设计", "夹具", "治具")):
        q += 6
    return q


def hit_facts(text):
    """岗位亮点 + 岗位名 命中简历能力簇，返回 [(完整事实, 短标签)]"""
    t = (text or "").lower()
    clusters = [
        (("测试治具", "测试夹具", "ict", "fct", "功能测试", "测试设备"), "ICT/FCT 测试治具与整机测试设备", "ICT/FCT 测试治具"),
        (("工装夹具", "治具", "夹具", "工装"), "3C 类非标测试治具与工装夹具设计", "工装夹具设计"),
        (("非标", "专机", "自动化设备", "产线", "装配线"), "非标自动化整机与产线设备开发", "非标自动化设备"),
        (("solidworks", "三维建模", "3d建模", "工程图", "bom", "图纸"), "SolidWorks 三维建模、工程图与 BOM 出图", "SolidWorks 出图"),
        (("气动", "伺服", "丝杆", "导轨", "电机", "选型", "传动"), "气动/伺服/导轨丝杆标准件选型", "气动伺服选型"),
        (("结构", "整机", "堆叠", "钣金", "机加工", "注塑"), "整机结构设计与加工工艺", "整机结构设计"),
        (("3c", "手机", "消费电子", "穿戴", "pcba", "平板"), "服务华为/OPPO/小米/比亚迪等 3C 客户", "3C 客户项目"),
        (("机床", "加工中心", "数控", "cnc"), "机床/数控设备与机加工工艺", "机床数控设计"),
    ]
    facts = [(f, short) for kws, f, short in clusters if any(k in t for k in kws)]
    return facts[:3]


def cut_text(s, n):
    """在标点处截断，避免把中文词切成半截"""
    s = (s or "").strip().rstrip("；;。")
    if len(s) <= n:
        return s
    head = s[:n]
    for p in ("；", ";", "，", ",", "、"):
        i = head.rfind(p)
        if i >= n // 2:
            return head[:i].rstrip("，,、；;")
    return head


def build_why(d, q):
    facts = hit_facts(d["岗位名称"] + " " + d["岗位亮点"])
    parts = []
    if facts:
        parts.append("岗位里的" + "、".join(f for f, _ in facts) + "，你都实打实做过，属于主线直接对口")
    else:
        parts.append("这个岗和你非标自动化/结构设计的主线沾边，属于保守试投")
    hi = pay_num(d["薪资"])
    if hi >= 25000:
        parts.append("薪资上限 %s，是这批里的天花板档，值得优先投" % d["薪资"])
    elif 0 < hi < 10000:
        parts.append("薪资 %s 偏低，低于 16 年经验的合理区间，当兜底" % d["薪资"])
    elif hi == 0:
        parts.append("薪资标「面议」，沟通时按 16 年经验谈")
    edu = d["学历"]
    if edu in ("大专", "学历不限", "经验不限", "—"):
        parts.append("学历门槛不卡大专")
    else:
        parts.append("学历标「%s」，只是明面要求，用 16 年经验和作品集开路" % edu)
    parts.append("在西安，正是简历写的期望城市")
    parts.append("岗位亮点：" + (d["岗位亮点"] or "—")[:60])
    parts.append("数据来自 BOSS直聘收录快照（%s），投递前点开原站核对是否仍在招" % SNAP_DATE)
    return "；".join(parts) + "。"


def build_msg(d):
    """每家公司一条精准话术：公司名 + 岗位名 + 亮点 + 简历事实，防止串话术"""
    co = d["公司"]
    unnamed = co.startswith(PLACEHOLDER)
    greet = ("您好，看到贵司在招「%s」" % d["岗位名称"]) if unnamed else \
            ("您好，%s的「%s」" % (co, d["岗位名称"]))
    light = cut_text(d["岗位亮点"], 30)
    facts = hit_facts(d["岗位名称"] + " " + d["岗位亮点"])
    tail = ("正对我的%s主线" % facts[0][1]) if facts else "和我的非标整机主线同一条线"
    edu = d["学历"]
    edu_txt = ("学历大专" if edu in ("大专", "学历不限", "经验不限", "—")
               else "岗位写%s，我学历大专，想用经验补" % edu)
    return ("%s，%s。我做 %s，%s。%s，人在西安，"
            "想先发简历和作品集，方便约个时间聊？") % (
        greet, light or "职责方向和我的经历很接近", PROFILE_FACT, tail, edu_txt)


def to_job(d):
    q = quality_score(d)
    facts = hit_facts(d["岗位名称"] + " " + d["岗位亮点"])
    hi = pay_num(d["薪资"])
    # 看板匹配度：快照质量分（薪资/公司名/学历/直链/工种）+ 简历能力簇命中，
    # 保留梯度，避免所有岗位都顶到 96 分导致「高匹配」筛选失效
    score = 45 + round(q * 0.7) + len(facts) * 3 + (3 if hi >= 20000 else 0)
    score = max(35, min(95, int(score)))
    unnamed = d["公司"].startswith(PLACEHOLDER)
    link = d["Boss直聘投递入口"] or "https://www.zhipin.com/web/geek/jobs?query=&city=101110100"
    edu = d["学历"]
    chips = [x for x in (d["经验"], edu, d["区域"]) if x not in ("", "—")][:2]
    return {
        "city": "xa",
        "co": d["公司"],
        "coTag": "公司名未显示" if unnamed else "",
        "role": d["岗位名称"],
        "area": d["区域"] if d["区域"] != "—" else "西安",
        "exp": d["经验"] if d["经验"] != "—" else "",
        "edu": edu if edu != "—" else "未标注",
        "eduOk": True,
        "pay": d["薪资"] if d["薪资"] not in ("—", "") else "面议",
        "payNote": "",
        "score": score,
        "g": "core" if score >= 78 else "near",
        "cls": "g",
        "chips": chips,
        "why": build_why(d, q),
        "msg": build_msg(d),
        "src": "BOSS直聘",
        "srcUrl": link,
        "link": link,
        "boss": True,
        "postAt": "",
        "addAt": ADD_AT,
        "firstSeen": ADD_AT,
        "lastSeen": ADD_AT,
        "isNew": True,
        "stale": False,
        "tags": ([f for f, _ in facts[:2]] + ([d["行业"]] if d["行业"] not in ("", "—") else []))[:3],
        # ↓ 原始 11 列字段保留，前端忽略；口径可追溯
        "行业": norm(d["行业"]),
        "岗位亮点": norm(d["岗位亮点"]),
        "来源页": norm(d["来源页"]),
        "Boss直聘投递入口": link,
        "数据时间": SNAP_DATE,
        "快照": True,
        "公司名未显示": unnamed,
        "质量分": q,
    }


def main():
    main_rows = read_csv(MAIN_CSV, True)
    back_rows = read_csv(BACK_CSV, False)
    print("[in] 主清单 %d 条，备选 %d 条" % (len(main_rows), len(back_rows)))

    # 4.7 过滤非设计岗 + (公司,岗位,薪资) 主键去重
    def clean(rows):
        seen, out = set(), []
        for d in rows:
            if is_bad_role(d["岗位名称"]):
                print("  [过滤非设计岗]", d["序号"], d["公司"], d["岗位名称"])
                continue
            k = (d["公司"], d["岗位名称"], d["薪资"])
            if k in seen:
                continue
            seen.add(k)
            out.append(d)
        return out

    main_rows, back_rows = clean(main_rows), clean(back_rows)
    # 备选里与主清单重复的丢掉
    mk = {(d["公司"], d["岗位名称"], d["薪资"]) for d in main_rows}
    back_rows = [d for d in back_rows if (d["公司"], d["岗位名称"], d["薪资"]) not in mk]
    print("[clean] 去重/过滤后 主清单 %d 条，备选 %d 条" % (len(main_rows), len(back_rows)))

    def rows_out(rows):
        return [dict(d, 数据时间=SNAP_DATE) for d in rows]

    jobs = [to_job(d) for d in main_rows]
    data = {
        "口径": "BOSS直聘（zhipin.com）公开招聘页的搜索引擎收录快照，非实时在招数据",
        "数据时间": SNAP_DATE,
        "生成时间": ADD_AT,
        "主键": ["公司", "岗位名称", "薪资"],
        "增量规则": "已存在条目只更新 来源页 / Boss直聘投递入口 / 数据时间，不重复插入；下架岗位标待核对，不直接删除",
        "列": COLS + ["数据时间"],
        "rows": rows_out(main_rows),
        "backup": rows_out(back_rows),
        "jobs": jobs,
    }
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    unnamed = [j for j in jobs if j["公司名未显示"]]
    dcz = [j for j in jobs if j["edu"] in ("大专", "学历不限", "经验不限")]
    hi20 = [j for j in jobs if pay_num(j["pay"]) >= 20000]
    detail = [j for j in jobs if "/job_detail/" in j["link"]]
    print("[out] %s" % OUT)
    print("  映射岗位 %d 条｜大专可投 %d｜20K+ %d｜详情页直链 %d｜公司名未显示 %d" %
          (len(jobs), len(dcz), len(hi20), len(detail), len(unnamed)))
    print("  前 5 条：%s" % " / ".join("%s %s %s" % (j["co"], j["role"], j["pay"]) for j in jobs[:5]))
    print("  话术长度 min/max = %d/%d" % (min(len(j["msg"]) for j in jobs), max(len(j["msg"]) for j in jobs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
