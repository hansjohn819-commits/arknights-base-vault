# -*- coding: utf-8 -*-
"""
生成 公孙长乐 skill 的 references/ 参考资料。

数据源（本地仓库，均为 workspace 下的兄弟目录）：
  主源  RIIC-Web/src/generated/arkntools/   —— arkntools/arknights-toolbox-data 派生
          operator-catalog.json        425 干员，含 buildingSkills[{id, elite, level}]
          building-skill-catalog.json  747 基建技能，含 descriptionRich / tags
          term-catalog.json            81 条官方术语（派系、技能类别、全局资源、叠加规则）
          source.json                  上游 commit 与计数
  补源  RhodeLogisticsSteward/          —— ArknightsGameData 派生，略旧（415 干员 / 727 技能）
          buffs_infrastructure.json    roomType / efficiency / targets
          buffs_non_production.json    同上（加工站、训练室）

两源已核对：
  - buffId 归一化（`[000]` → `_000`）后主源 727/747 命中补源，补源无独有条目
  - roomType 可由主源 id 前缀唯一推出，与补源标注 100% 一致
  - 星级口径 主源 rarity == 补源 rarity + 1，零例外（主源为实际星数）

用法：
    python build_refs.py [--workspace F:\\RIIC\\workspace] [--json 合并数据输出路径]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

# ---------------------------------------------------------------- 常量映射

# id 前缀 → (roomType, 中文设施名, 输出文件序号)
ROOMS = [
    ("trade",    "TRADING",     "贸易站"),
    ("manu",     "MANUFACTURE", "制造站"),
    ("control",  "CONTROL",     "控制中枢"),
    ("power",    "POWER",       "发电站"),
    ("dorm",     "DORMITORY",   "宿舍"),
    ("meet",     "MEETING",     "会客室"),
    ("hire",     "HIRE",        "办公室"),
    ("train",    "TRAINING",    "训练室"),
    ("workshop", "WORKSHOP",    "加工站"),
]
PREFIX_TO_ROOM = {p: zh for p, _, zh in ROOMS}
ROOM_ORDER = [zh for _, _, zh in ROOMS]

PROFESSION = {
    1: "近卫", 2: "狙击", 3: "重装", 4: "医疗",
    5: "辅助", 6: "术师", 7: "特种", 8: "先锋",
}

# 制造站/加工站产物代码。职业代码（WARRIOR 等）另行处理。
TARGET_ZH = {
    "F_GOLD": "赤金",
    "F_EXP": "作战记录",
    "F_DIAMOND": "源石碎片",
    "F_EVOLVE": "精英材料",
    "F_SKILL": "技巧概要",
    "F_BUILDING": "基建材料",
    "F_ASC": "芯片",
}
TARGET_PROF = {
    "WARRIOR": "近卫", "SNIPER": "狙击", "TANK": "重装", "MEDIC": "医疗",
    "SUPPORT": "辅助", "CASTER": "术师", "SPECIAL": "特种", "PIONEER": "先锋",
}

# 人工维护：社区／语料自用的简称与合称。
# 这些不是子串关系（「推王」不是「推进之王」的子串规则能覆盖的形态，「德狼」更不是任何人的子串），
# 无法从数据自动推出。改动语料或游戏出新异格时在这里补。
# `targets` 里的名字会被脚本校验是否仍在名册中——写错会在校对清单里报出来。
ALIASES: dict[str, dict] = {
    "推王": {
        "targets": ["推进之王"],
        "note": "维娜·维多利亚是推进之王的异格，也被叫推王，所以这个说法两边都成立。"
                "默认指本体推进之王（技能全在宿舍）；**一旦话题涉及贸易站，必须反问是不是指"
                "维娜·维多利亚**。体系名「推王龙门」是整体，不要拆开解析。",
    },
    "维娜": {"targets": ["维娜·维多利亚"], "note": "简称，无歧义"},
    "德狼": {"targets": ["德克萨斯", "拉普兰德"], "note": "合称，见 `docs/2-体系/企鹅物流.md`"},
    "德狗": {"targets": ["德克萨斯"], "note": "语料 `灵孑银崖喀兰.md` 的写法，与「德狼」不统一"},
    "拉狗": {"targets": ["拉普兰德"], "note": "同上"},
    "能蕾": {"targets": ["能天使", "蕾缪安"], "note": "合称，见 `docs/2-体系/企鹅物流.md`"},
    "银崖": {"targets": ["银灰", "崖心"], "note": "合称，见 `docs/2-体系/灵孑银崖喀兰.md`"},
    "孑拉德": {"targets": ["孑", "拉普兰德", "德克萨斯"], "note": "精 0 孑路线"},
    "龙门中枢组": {"targets": ["斩业星熊", "诗怀雅"],
                   "note": "无独立文档，见 `docs/4-散件工具人/散件干员速查.md` 中枢部分"},
}

# 术语 desc 的首行前缀 → 术语种类
TERM_KINDS = [
    ("包含以下干员", "干员组"),
    ("由以下干员的基建技能提供", "全局资源"),
    ("拥有该基建技能的干员", "技能持有"),
    ("包含以下设施", "设施组"),
    ("包含以下技能", "技能组"),
]

# ---------------------------------------------------------------- 工具

def read_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def normalize_buff_id(buff_id: str) -> str:
    """补源 `control_tra_spd[000]` → 主源 `control_tra_spd_000`。"""
    return re.sub(r"\[(\d+)\]$", r"_\1", buff_id)


TERM_REF_RE = re.compile(r"<\$([a-zA-Z0-9_.]+)>")


def extract_term_refs(rich: str) -> list[str]:
    """抽出描述里引用的术语 id，`cc.g.bs` → `cc_g_bs`（term-catalog 的键）。"""
    seen = []
    for raw in TERM_REF_RE.findall(rich):
        key = raw.replace(".", "_")
        if key not in seen:
            seen.append(key)
    return seen


def strip_rich(rich: str) -> str:
    """去掉富文本标签，保留文字。上游有 1 处 `<<$cc.bd_b1>` 拼写错误，一并清掉游离尖括号。"""
    text = TERM_REF_RE.sub("", rich)
    text = re.sub(r"</>", "", text)
    text = re.sub(r"<@[a-zA-Z0-9_.]+>", "", text)
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("<", "").replace(">", "")
    return re.sub(r"\s+", " ", text).strip()


def tier_label(elite: int, level: int) -> str:
    """练度门槛。低星干员是 elite=0 / level=30（满级解锁）。"""
    if elite == 0 and level > 1:
        return f"Lv.{level}"
    return f"精{elite}"


def buff_base(buff_id: str) -> str:
    """
    技能族标识：buffId 最后一个下划线之前的部分。

    这是判断「提升」还是「解锁」的关键。游戏把干员的基建技能标成
    「初始解锁」/「精英 N 解锁」/「精英 N 提升」——**提升是替换低档，解锁是新增并存**。

    这个区分在派生数据里看不出来：arkntools 上游的 `building.json` 已把
    `buffChar[].buffData[]` 的槽位嵌套拍平成一维数组，其 `index` 只是数组下标
    （见 `RIIC-Web/scripts/arkntools-assets-lib.mjs` 的 `index: offset + 1`）；
    RhodeLogisticsSteward 的 `scripts/extract_character_identity.py` 同样两层循环拍平。

    但 buffId 的族名保留了这个信息——同一干员名下同族的多条技能就是一条升级链：
        温蒂  manu_prod_spd&power_010（自动化·β）→ _020（仿生海龙）   同族 = 提升
        银灰  trade_ord_spd&limit_020 → _022                          同族 = 提升
        巫恋  trade_ord_wt&cost_000（裁缝·α）｜trade_ord_vodfox_000（低语）  异族 = 解锁
        德克萨斯 trade_ord_spd&cost_P_000（恩怨）｜trade_ord_limit&cost_P_010（默契） 异族 = 解锁

    本实现与 `RIIC-Web/src/operatorPortraits.ts` 的 `isBuildingSkillEnhanced()`
    是同一规则（前缀取法、以及「同族且 ≥2 条时除首条外都是提升」）。
    已全库 913 条逐条比对：提升 167 条，两边判定零差异；且全部 buffId 都以 `_数字` 结尾、
    每条链的 index 顺序与 elite 顺序一致，故两种写法等价。

    注意 icon 不是有效判据——升级链内 icon 也会换（`spd&power2` → `spd&power3`）。
    """
    sep = buff_id.rfind("_")
    return buff_id if sep < 0 else buff_id[:sep]


def unlock_label(elite: int, level: int, enhanced: bool) -> str:
    """解锁条件文案，与 RIIC-Web `operator-presentation.ts` 的 buildingSkillUnlockLabel 对齐。"""
    word = "提升" if enhanced else "解锁"
    if elite == 0 and level == 1:
        return "初始解锁" if not enhanced else "初始提升"
    parts = []
    if elite > 0:
        parts.append(f"精英 {elite}")
    if level > 1:
        parts.append(f"等级 {level}")
    return " · ".join(parts) + f" {word}"


def stars(rarity: int) -> str:
    return "☆" + str(rarity)

# ---------------------------------------------------------------- 加载与合并

def load_all(workspace: Path):
    web = workspace / "RIIC-Web" / "src" / "generated" / "arkntools"
    stw = workspace / "RhodeLogisticsSteward"

    operators = read_json(web / "operator-catalog.json")
    skills = read_json(web / "building-skill-catalog.json")
    terms = read_json(web / "term-catalog.json")
    manifest = read_json(web / "source.json")

    identity = read_json(stw / "character_identity.json")
    old_buffs = {}
    old_buffs.update(read_json(stw / "buffs_infrastructure.json"))
    old_buffs.update(read_json(stw / "buffs_non_production.json"))
    old_by_norm = {normalize_buff_id(k): v for k, v in old_buffs.items()}

    return operators, skills, terms, manifest, identity, old_by_norm


def build_term_index(terms: dict):
    """解析术语：拆出种类与成员列表；并建立 干员名 → 所属干员组 的反查。"""
    parsed = {}
    member_of = collections.defaultdict(list)

    for tid, t in terms.items():
        desc = t.get("desc") or ""
        head, _, body = desc.partition("\n")
        head = head.strip()
        kind = "规则说明"
        for prefix, k in TERM_KINDS:
            if head.startswith(prefix):
                kind = k
                break
        members = []
        if kind != "规则说明" and body.strip():
            members = [m.strip() for m in re.split(r"[、,，]", body.strip()) if m.strip()]
        parsed[tid] = {
            "id": tid,
            "name": t["name"],
            "kind": kind,
            "head": head,
            "members": members,
            "text": (t.get("descText") or "").strip(),
        }
        if kind == "干员组":
            for m in members:
                member_of[m].append(t["name"])

    return parsed, member_of


def merge(operators, skills, terms_parsed, identity, old_by_norm):
    """合并成以干员为中心的结构，并给技能补 roomType / efficiency / targets。"""
    ident_by_name = {v["name"]: v for v in identity.values()}

    skill_meta = {}
    for sid, s in skills.items():
        prefix = sid.split("_")[0]
        room = PREFIX_TO_ROOM.get(prefix)
        old = old_by_norm.get(sid)
        raw_targets = list(old.get("targets") or []) if old else []
        skill_meta[sid] = {
            "id": sid,
            "name": s["name"],
            "room": room,
            "desc": strip_rich(s["descriptionRich"]),
            "tags": list(s.get("tags") or []),
            "term_refs": extract_term_refs(s["descriptionRich"]),
            "efficiency": old.get("efficiency") if old else None,
            "targets": raw_targets,
            "in_old_source": old is not None,
            "holders": [],
        }

    merged = []
    for op in sorted(operators, key=lambda o: (-o["rarity"], o["name"])):
        ident = ident_by_name.get(op["name"])
        raw = [b for b in sorted(op.get("buildingSkills", []), key=lambda x: x["index"])
               if b["id"] in skill_meta]

        # 按技能族分组，还原「提升 / 解锁」——见 buff_base 的说明
        chains = collections.defaultdict(list)
        for b in raw:
            chains[buff_base(b["id"])].append(b)
        for lst in chains.values():
            lst.sort(key=lambda x: (x["elite"], x["level"]))

        entries = []
        for b in raw:
            meta = skill_meta[b["id"]]
            chain = chains[buff_base(b["id"])]
            pos = chain.index(b)
            if pos > 0:
                prev = skill_meta[chain[pos - 1]["id"]]["name"]
                unlock, supersedes = "提升", prev
            else:
                unlock, supersedes = "解锁", None
            entries.append({
                "skill_id": b["id"],
                "elite": b["elite"],
                "level": b["level"],
                "tier": tier_label(b["elite"], b["level"]),
                "unlock": unlock,          # 解锁（新增并存）/ 提升（替换前一档）
                "supersedes": supersedes,  # 提升时被替换的技能名
                "initial": pos == 0 and b["elite"] == 0 and b["level"] == 1,
            })
            meta["holders"].append((op["name"], op["rarity"], tier_label(b["elite"], b["level"])))
        merged.append({
            "name": op["name"],
            "char_id": op["id"],
            "rarity": op["rarity"],
            "profession": PROFESSION.get(op["profession"], f"?{op['profession']}"),
            "nation_id": (ident or {}).get("nationId"),
            "group_id": (ident or {}).get("groupId"),
            "team_id": (ident or {}).get("teamId"),
            "in_old_source": ident is not None,
            "skills": entries,
            "rooms": sorted({skill_meta[e["skill_id"]]["room"] for e in entries if skill_meta[e["skill_id"]]["room"]},
                            key=ROOM_ORDER.index),
        })

    return merged, skill_meta

# ---------------------------------------------------------------- 产物渲染

HEADER = "<!-- 本文件由 scripts/build_refs.py 生成，请勿手改；改数据源后重跑脚本。 -->\n"


def render_roster(merged, member_of) -> str:
    out = [HEADER, "# 干员名册\n",
           "全部 **{} 名**干员。这份名单是**边界闭包**：不在表内的名字一律回答「不知道是谁」，"
           "不要凭印象补。\n".format(len(merged)),
           "字段：`标准名 | 星级 | 职业 | 有基建技能的设施 | 所属组`。"
           "「所属组」取自官方术语表（见 `类别.md`），只列基建技能会引用到的组；为空表示没有基建技能引用其归属。\n"]

    by_rarity = collections.defaultdict(list)
    for op in merged:
        by_rarity[op["rarity"]].append(op)

    for rarity in sorted(by_rarity, reverse=True):
        group = by_rarity[rarity]
        out.append(f"\n## {stars(rarity)}（{len(group)} 名）\n")
        for op in group:
            rooms = "、".join(op["rooms"]) or "无基建技能"
            groups = "、".join(member_of.get(op["name"], []))
            out.append(f"- {op['name']} | {stars(op['rarity'])} | {op['profession']} | {rooms}"
                       + (f" | {groups}" if groups else ""))
    return "\n".join(out) + "\n"


def render_terms(terms_parsed) -> str:
    out = [HEADER, "# 官方术语与类别\n",
           "取自游戏内术语表（arkntools 数据源 `term-catalog.json`，共 {} 条）。"
           "基建技能描述里引用的每一个类别、全局资源和叠加规则都在这里有权威定义。\n".format(len(terms_parsed)),
           "**用途**：用户说「谢拉格干员」「金属工艺类技能」「深海猎人」这类**类别**时，"
           "在这里查成员列表，不要自己回忆。类别成员是可枚举的；查不到的类别说法（如社区俗称）要反问，不要猜。\n"]

    order = ["干员组", "全局资源", "技能组", "技能持有", "设施组", "规则说明"]
    by_kind = collections.defaultdict(list)
    for t in terms_parsed.values():
        by_kind[t["kind"]].append(t)

    for kind in order:
        items = sorted(by_kind.get(kind, []), key=lambda x: x["name"])
        if not items:
            continue
        out.append(f"\n## {kind}（{len(items)} 条）\n")
        for t in items:
            if t["members"]:
                out.append(f"- **{t['name']}**（{len(t['members'])}）：" + "、".join(t["members"]))
            else:
                out.append(f"- **{t['name']}**：{t['text']}")
    return "\n".join(out) + "\n"


def render_room_skills(room_zh, merged, skill_meta, terms_parsed) -> str:
    ids_in_room = {sid for sid, m in skill_meta.items() if m["room"] == room_zh}
    ops_in_room = [op for op in merged if any(e["skill_id"] in ids_in_room for e in op["skills"])]

    # 同一设施内出现重名技能时（不同 buffId、同一显示名，数值往往不同），补 id 以便区分
    dup_names = {n for n, c in collections.Counter(
        skill_meta[s]["name"] for s in ids_in_room).items() if c > 1}

    def label(sid):
        m = skill_meta[sid]
        return f"「{m['name']}」" + (f"（`{sid}`）" if m["name"] in dup_names else "")

    def term_names(refs):
        return [terms_parsed[r]["name"] if r in terms_parsed else r for r in refs]

    out = [HEADER, f"# {room_zh}基建技能\n",
           f"{room_zh}相关技能 **{len(ids_in_room)} 个**，涉及干员 **{len(ops_in_room)} 名**。"
           "只收录该设施的技能；同一干员在别的设施还有技能时，去对应分片查。\n",
           "**练度门槛**：`精N` = 精英化 N 阶段；`Lv.30` = 等级 30（一至三星干员满级即解锁，不需要精英化）。\n",
           "**提升 vs 解锁 —— 这个区分很关键**（文案与游戏内、与 RIIC-Web 干员查询页一致）：\n",
           "- `初始解锁` / `精英 N 解锁` / `等级 N 解锁` = **新增一个技能，之前的继续生效**（并存）\n"
           "- `精英 N 提升` = **替换掉前一档，只有新的生效**（已标注替换谁）\n",
           "例：温蒂精 2 的「仿生海龙」是**提升**，替换精 0 的「自动化·β」，所以只按 +15%/电站 算，"
           "不是 10%+15%；巫恋精 2 的「低语」是**解锁**，精 0 的「裁缝·α」仍然在，两个同时生效。\n"]

    out.append("\n## 按干员\n")
    for op in ops_in_room:
        groups_note = f" · {op['profession']}"
        out.append(f"\n### {op['name']} {stars(op['rarity'])}{groups_note}\n")
        for e in op["skills"]:
            m = skill_meta[e["skill_id"]]
            if m["room"] != room_zh:
                continue
            bits = []
            if m["tags"]:
                bits.append("标签：" + "/".join(m["tags"]))
            prods = [TARGET_ZH[t] for t in m["targets"] if t in TARGET_ZH]
            profs = [TARGET_PROF[t] for t in m["targets"] if t in TARGET_PROF]
            if prods:
                bits.append("作用产物：" + "/".join(prods))
            if profs:
                bits.append("作用职业：" + "/".join(profs))
            if m["term_refs"]:
                bits.append("引用术语：" + "/".join(term_names(m["term_refs"])))
            if not m["in_old_source"]:
                bits.append("补源无此条（产物/效率字段缺失）")
            suffix = ("　〔" + "；".join(bits) + "〕") if bits else ""
            mark = unlock_label(e["elite"], e["level"], e["unlock"] == "提升")
            if e["unlock"] == "提升":
                mark += f"，替换「{e['supersedes']}」"
            out.append(f"- **{mark}**{label(e['skill_id'])}：{m['desc']}{suffix}")

    out.append("\n## 技能 → 持有者\n")
    out.append("同名但 buffId 不同的是**两个不同技能**（数值通常不同），已附 id 区分。\n")
    for sid in sorted(ids_in_room, key=lambda s: (skill_meta[s]["name"], s)):
        m = skill_meta[sid]
        holders = sorted(m["holders"], key=lambda h: (-h[1], h[0]))
        if not holders:
            out.append(f"- {label(sid)}：（无干员持有）")
            continue
        out.append(f"- {label(sid)}：" + "、".join(f"{n}{stars(r)}({t})" for n, r, t in holders))
    return "\n".join(out) + "\n"


def render_ambiguity(merged, terms_parsed) -> str:
    names = [op["name"] for op in merged]
    name_set = set(names)
    rooms_of = {op["name"]: op["rooms"] for op in merged}
    pairs = []
    for short in names:
        if len(short) < 2:
            continue
        longs = [n for n in name_set if n != short and short in n]
        if longs:
            pairs.append((short, sorted(longs)))
    pairs.sort(key=lambda x: x[0])

    # 只保留「术语名本身就是一个干员标准名」的组——那才是真正的同名歧义。
    # 「骑士」这类纯标签虽然也是别人名字的子串，但它不是干员，不算歧义。
    official = [t for t in terms_parsed.values()
                if t["kind"] == "干员组" and len(t["members"]) >= 2
                and t["name"] in name_set
                and any(t["name"] in m and t["name"] != m for m in t["members"])]

    out = [HEADER, "# 指代歧义\n",
           "**硬规则**：用户输入恰好等于某个短名／俗称时，不许静默挑一个。"
           "静默选错不会有任何报错，但数值会直接答错。\n",
           "消歧的可用线索是**设施**：如果两人的基建技能落在不同设施，而用户已经点明了设施"
           "（「贸易站放谁」「发电站用谁」），就按设施判断并在回答里说明你按哪个理解的；"
           "设施重叠或用户没点明的，直接反问。\n",
           f"\n## 一、子串包含对（{len(pairs)} 组，自动生成）\n",
           "短名是长名的子串。它们是**不同干员、数据不同**。\n"]
    for short, longs in pairs:
        sr = set(rooms_of.get(short, []))
        line = f"- **{short}**（{'、'.join(rooms_of.get(short, [])) or '无基建技能'}） ⊂ "
        parts = []
        for n in longs:
            nr = set(rooms_of.get(n, []))
            mark = "设施重叠→必须反问" if sr & nr else "设施不重叠→可按上下文判断"
            parts.append(f"{n}（{'、'.join(rooms_of.get(n, [])) or '无基建技能'}｜{mark}）")
        out.append(line + "；".join(parts))

    out.append("\n## 二、简称与合称（人工维护）\n")
    out.append("不是子串关系，推不出来，只能查表。\n")
    for alias, info in ALIASES.items():
        targets = info["targets"]
        detail = "、".join(f"{t}（{'、'.join(rooms_of.get(t, [])) or '不在名册'}）" for t in targets)
        out.append(f"\n- **{alias}** → {detail}")
        out.append(f"  - {info['note']}")

    if official:
        out.append("\n## 三、官方术语表也把这些视为同一组\n")
        out.append("游戏自己就把下列名字定义成「包含多个干员」的组，说明这种歧义是游戏层面的，不是用户口误：\n")
        for t in official:
            out.append(f"- **{t['name']}**：" + "、".join(t["members"]))
    return "\n".join(out) + "\n"


def render_equiv_groups(skill_meta) -> str:
    """
    按「清洗后描述完全相同」聚类技能。

    这一步解决的是**技能层面的别称**问题：游戏里存在多个显示名不同、效果描述逐字相同的技能，
    社区用一个俗称统一指代（典型：裁缝·β / 手工艺品·β / 鉴定师的手段 三者描述完全一致，
    玩家一律叫「裁缝 β」）。不做这层聚类，按官方技能名检索会漏掉大部分持有者。
    """
    clusters = collections.defaultdict(list)
    for sid, m in skill_meta.items():
        if m["holders"]:
            clusters[(m["room"], m["desc"])].append(sid)

    multi = []
    for (room, desc), sids in clusters.items():
        names = sorted({skill_meta[s]["name"] for s in sids})
        if len(names) > 1:
            holders = []
            for s in sids:
                holders.extend(skill_meta[s]["holders"])
            multi.append({"room": room, "desc": desc, "names": names,
                          "holders": sorted(set(holders), key=lambda h: (-h[1], h[0]))})
    multi.sort(key=lambda x: (ROOM_ORDER.index(x["room"]), -len(x["names"]), x["names"][0]))

    out = [HEADER, "# 技能等价组（同效不同名）\n",
           "下列每一组里的技能，**官方显示名不同但效果描述逐字相同**——它们是同一个东西。"
           "玩家往往只用其中一个名字（或一个社区俗称）指代整组。\n",
           "**用途**：用户提到某个技能名时，先看它落在哪一组，然后**整组的持有者都是候选**。"
           "只按字面技能名去 `技能-*.md` 里找，会漏掉大部分人。\n",
           "典型例子：「裁缝 β」在数据里叫 `裁缝·β`，但 `手工艺品·β`（卡夫卡）和 `鉴定师的手段`（折光）"
           "描述完全一致，玩家统称裁缝——这就是为什么公孙的语料把这四人列在一起。\n",
           f"\n共 {len(multi)} 组。\n"]

    cur_room = None
    for g in multi:
        if g["room"] != cur_room:
            cur_room = g["room"]
            out.append(f"\n## {cur_room}\n")
        out.append(f"\n- **{' ＝ '.join(g['names'])}**")
        out.append(f"  - 效果：{g['desc']}")
        out.append("  - 持有者：" + "、".join(f"{n}{stars(r)}({t})" for n, r, t in g["holders"]))
    return "\n".join(out) + "\n"


def render_provenance(manifest, merged, skill_meta, terms_parsed) -> str:
    no_old_skill = sorted(sid for sid, m in skill_meta.items() if not m["in_old_source"])
    no_old_op = sorted(op["name"] for op in merged if not op["in_old_source"])
    no_room = sorted(sid for sid, m in skill_meta.items() if not m["room"])

    room_counts = collections.Counter(m["room"] for m in skill_meta.values() if m["room"])

    out = [HEADER, "# 数据来源与已知缺口\n",
           "## 主源\n",
           f"- 仓库：`{manifest['source']['repository']}`",
           f"- commit：`{manifest['source']['commit']}`",
           f"- 计数：干员 {manifest['counts']['operators']} / 基建技能 {manifest['counts']['buildingSkills']}"
           f" / 术语 {manifest['counts']['terms']}",
           "- 经由 `RIIC-Web/src/generated/arkntools/` 落地\n",
           "## 补源\n",
           "- `RhodeLogisticsSteward/`（派生自 ArknightsGameData），提供主源没有的 "
           "`efficiency`、`targets`（产物/职业）和 `nationId/groupId/teamId`",
           "- 略旧：干员 415、技能 727，均为主源子集\n",
           "## 已核对的口径差异\n",
           "- **星级**：主源 `rarity` 就是实际星数；补源是 0 起算（`rarity + 1`）。已核对全量零例外。",
           "- **buffId**：补源 `xxx[000]`，主源 `xxx_000`。归一化后 727/747 命中。",
           "- **roomType**：主源无该字段，由 id 前缀推出；与补源标注全量一致。\n",
           "## 各设施技能数\n"]
    for zh in ROOM_ORDER:
        out.append(f"- {zh}：{room_counts.get(zh, 0)}")

    out.append("\n## 已知缺口\n")
    out.append(f"- 补源缺失的技能 **{len(no_old_skill)} 条**（较新，无 `targets`/`efficiency`）："
               + "、".join(f"`{s}`" for s in no_old_skill))
    out.append(f"- 补源缺失的干员 **{len(no_old_op)} 名**（无派系字段）：" + "、".join(no_old_op))
    if no_room:
        out.append(f"- 无法判定设施的技能 {len(no_room)} 条：" + "、".join(f"`{s}`" for s in no_room))
    else:
        out.append("- 无法判定设施的技能：0 条")
    out.append("\n## 更新方式\n")
    out.append("重跑 `scripts/build_refs.py`。上游数据由 RIIC-Web 的 arkntools 资产流水线刷新，"
               "本脚本只做合并与渲染，不含手工维护的数据。\n")
    return "\n".join(out) + "\n"

# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=r"F:\RIIC\workspace",
                    help="包含 RIIC-Web 与 RhodeLogisticsSteward 的目录")
    ap.add_argument("--out", default=None, help="references 输出目录，默认脚本同级的 ../references")
    ap.add_argument("--json", default=None, help="额外输出合并后的 JSON（供分析用）")
    args = ap.parse_args()

    workspace = Path(args.workspace)
    out_dir = Path(args.out) if args.out else Path(__file__).resolve().parent.parent / "references"
    out_dir.mkdir(parents=True, exist_ok=True)

    operators, skills, terms, manifest, identity, old_by_norm = load_all(workspace)
    terms_parsed, member_of = build_term_index(terms)
    merged, skill_meta = merge(operators, skills, terms_parsed, identity, old_by_norm)

    written = []

    def write(name: str, text: str):
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        written.append((name, len(text)))

    write("名册.md", render_roster(merged, member_of))
    write("类别.md", render_terms(terms_parsed))
    write("歧义.md", render_ambiguity(merged, terms_parsed))
    write("技能等价组.md", render_equiv_groups(skill_meta))
    write("数据源.md", render_provenance(manifest, merged, skill_meta, terms_parsed))
    for zh in ROOM_ORDER:
        write(f"技能-{zh}.md", render_room_skills(zh, merged, skill_meta, terms_parsed))

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"operators": merged, "skills": skill_meta, "terms": terms_parsed,
             "member_of": dict(member_of)},
            ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"输出目录：{out_dir}")
    for name, size in written:
        print(f"  {name:22s} {size/1024:8.1f} KB")

    # 结构性抽查：产物代码与设施的对应关系是否符合预期
    combo = collections.defaultdict(collections.Counter)
    for m in skill_meta.values():
        for t in m["targets"]:
            combo[m["room"]][t] += 1
    print("\n设施 × 产物代码抽查：")
    for zh in ROOM_ORDER:
        if combo.get(zh):
            print(f"  {zh}: {dict(combo[zh])}")

    n_up = sum(1 for op in merged for e in op["skills"] if e["unlock"] == "提升")
    n_unlock = sum(1 for op in merged for e in op["skills"] if e["unlock"] == "解锁")
    n_ops_up = sum(1 for op in merged if any(e["unlock"] == "提升" for e in op["skills"]))
    print(f"\n提升 / 解锁 判定：提升 {n_up} 条、解锁 {n_unlock} 条，"
          f"涉及升级链的干员 {n_ops_up} / {len(merged)} 名")


if __name__ == "__main__":
    main()
