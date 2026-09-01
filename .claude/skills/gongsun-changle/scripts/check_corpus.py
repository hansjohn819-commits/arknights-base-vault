# -*- coding: utf-8 -*-
"""
语料校对：把 docs/ 的内容与全量游戏数据逐项对照，输出 `语料校对清单.md`。

与 build_refs.py 的分工：
  build_refs.py   生成 skill 运行时要读的 references/（面向 LLM）
  check_corpus.py 生成给人看的校对清单（面向公孙 / KnightCode）

语料改动后重跑即可复查。用法：
    python check_corpus.py [--workspace F:\\RIIC\\workspace] [--out 输出路径]
"""

from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path

import build_refs as B

CJK = "\u4e00-\u9fa5"
# 名字里可以出现间隔号（凯尔希·思衡托、维娜·维多利亚、Miss.Christine），切词时不能在这里断开
NAME_CHARS = f"[{CJK}A-Za-z0-9\\-.\u00b7\u00b2\u00b3]"
SEP = re.compile(f"[^{CJK}A-Za-z0-9\\-.\u00b7\u00b2\u00b3]+")
STAR_RE = re.compile(f"({NAME_CHARS}+)\\s*[（(]\\s*\u2606\\s*(\\d)\\s*[)）]")
QUOTED_RE = re.compile(r"[\u300c\u300e]([^\u300d\u300f]{2,20})[\u300d\u300f]")

# 简称表复用 build_refs.ALIASES，避免两处维护（那边同时渲染进 references/歧义.md）
CORPUS_ALIASES = B.ALIASES


def norm_skill(s: str) -> str:
    return re.sub(r"[\s\u00b7\u2022\u30fb\-\u2014]", "", s)


ASSERT_RE = re.compile(r"都是|同为|属于|也是|均为|皆为|都属于")


def check_faction_assertions(corpus, rel, ops, terms_parsed):
    """
    扫语料里的派系归属断言，与官方术语表比对。

    动机：`推王龙门.md:32` 断言「维娜和摩根都是格拉斯哥帮」，但官方术语表里
    格拉斯哥帮 = 推进之王、摩根、达格达、因陀罗，不含维娜·维多利亚。整段推导因此失效。
    这类错误无法靠通读发现——名字看着就该是一伙的。

    只在句子同时满足两个条件时才检查，以压低噪声：
      1. 句中出现某个官方干员组的名字
      2. 句中出现归属断言词（都是 / 属于 / 同为 …）

    仅提供 buff 的干员（如戴菲恩对格拉斯哥帮）通常不带断言词，因此不会被误报。
    """
    groups = {t["name"]: set(t["members"])
              for t in terms_parsed.values()
              if t["kind"] == "干员组" and t["members"]}
    findings = []

    for f, text in corpus.items():
        for sent in re.split(r"[。；\n]", text):
            sent = sent.strip()
            if not sent or not ASSERT_RE.search(sent):
                continue
            for gname, members in groups.items():
                if gname not in sent:
                    continue
                # 找句中提到的干员：先剔除被更长名字包含造成的假命中
                probe = sent
                mentioned = []
                for n in sorted(ops, key=len, reverse=True):
                    if n in probe:
                        mentioned.append(n)
                        probe = probe.replace(n, "　" * len(n))
                # 简称也算（维娜 → 维娜·维多利亚）
                for alias, info in B.ALIASES.items():
                    if alias in probe:
                        mentioned.extend(t for t in info["targets"] if t in ops)
                bad = sorted({n for n in mentioned if n not in members})
                if bad:
                    findings.append({
                        "file": rel(f), "group": gname, "bad": bad,
                        "members": sorted(members), "sent": sent[:120],
                    })
    return findings


def candidates_from(text: str) -> set[str]:
    """
    只从高可信的结构化位置抽干员名候选，避免把表头、量词、机制名误判成干员：
      1. front matter 的 operators 数组
      2. `名（☆N）` 星级标注
      3. 表头首列明确是「干员」的表格，取其首列单元格
    """
    out: set[str] = set()
    for m in re.finditer(r"^operators:\s*\[(.*?)\]", text, re.M):
        out |= {t.strip() for t in m.group(1).split(",") if t.strip()}
    for m in STAR_RE.finditer(text):
        out.add(m.group(1))

    in_op_table = False
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            in_op_table = False
            continue
        cells = [c.strip().strip("*` ") for c in s.strip("|").split("|")]
        if not cells:
            continue
        head = cells[0]
        if head in ("\u5e72\u5458", "\u7b2c\u4e09\u4eba", "\u5e72\u5458\u540d"):
            in_op_table = True
            continue
        if set(head) <= {"-", ":", " ", ""}:
            continue
        if not in_op_table:
            continue
        for tok in SEP.split(head):
            tok = tok.strip("*` ")
            if 2 <= len(tok) <= 10 and re.fullmatch(f"{NAME_CHARS}+", tok):
                out.add(tok)
    return {t for t in out if t}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=r"F:\RIIC\workspace")
    ap.add_argument("--out", default=None,
                    help="输出路径，默认仓库根目录下的 语料校对清单.md")
    args = ap.parse_args()

    # scripts / gongsun-changle / skills / .claude / <仓库根>
    repo = Path(__file__).resolve().parents[4]
    docs = repo / "docs"
    out_path = Path(args.out) if args.out else repo / "\u8bed\u6599\u6821\u5bf9\u6e05\u5355.md"

    # --- 数据侧
    operators, skills_raw, terms, manifest, identity, old_by_norm = B.load_all(Path(args.workspace))
    terms_parsed, member_of = B.build_term_index(terms)
    merged, skill_meta = B.merge(operators, skills_raw, terms_parsed, identity, old_by_norm)
    ops = {o["name"]: o for o in merged}

    # --- 语料侧
    corpus = {f: f.read_text(encoding="utf-8") for f in sorted(docs.rglob("*.md"))}
    all_text = "\n".join(corpus.values())

    def rel(p: Path) -> str:
        return str(p.relative_to(repo)).replace("\\", "/")

    # 1. 名字
    cand_src: dict[str, set[str]] = collections.defaultdict(set)
    for f, text in corpus.items():
        for c in candidates_from(text):
            cand_src[c].add(rel(f))
    unknown = sorted(c for c in cand_src if c not in ops)

    # 覆盖度：剔除被更长名字包含造成的假命中（"银灰" 命中于 "凛御银灰"）
    covered = set()
    for n in ops:
        text = all_text
        for m in (x for x in ops if x != n and n in x):
            text = text.replace(m, "")
        if n in text:
            covered.add(n)

    # 2. 练度记法
    tier_src: dict[str, set[str]] = collections.defaultdict(set)
    for f, text in corpus.items():
        for name in ops:
            for suffix in ("II", "I", "0"):
                if re.search(re.escape(name) + suffix + r"(?![A-Za-z0-9])", text):
                    tier_src[name + suffix].add(rel(f))
    tier_notation = sorted(tier_src.items())

    # 3. 星级
    star_issues = []
    for f, text in corpus.items():
        for m in STAR_RE.finditer(text):
            name, s = m.group(1), int(m.group(2))
            if name in ops and ops[name]["rarity"] != s:
                star_issues.append((rel(f), name, s, ops[name]["rarity"]))

    # 4/5. 技能名
    official: dict[str, list[str]] = collections.defaultdict(list)
    for sid, m in skill_meta.items():
        official[norm_skill(m["name"])].append(sid)
    by_desc: dict[tuple, set[str]] = collections.defaultdict(set)
    for sid, m in skill_meta.items():
        if m["holders"]:
            by_desc[(m["room"], m["desc"])].add(sid)
    group_of = {sid: sids for sids in by_desc.values() for sid in sids}

    quoted: dict[str, set[str]] = collections.defaultdict(set)
    for f, text in corpus.items():
        for m in QUOTED_RE.finditer(text):
            quoted[m.group(1)].add(rel(f))

    # 语料的「」里也常引用官方**术语**（感知信息、木天蓼、天道酬勤·α 等），
    # 这些不在技能名里但在 term-catalog 里，要一并认掉，否则会被误报成查不到。
    term_by_norm = {norm_skill(t["name"]): t for t in terms_parsed.values()}

    # 语料常用「族名」指代整族技能（天道酬勤 = 天道酬勤·α/β，莱茵科技 = ·α/β/γ）。
    # 这类不是错误，但解析层要能从族名展开到具体档位。
    all_names = ({norm_skill(m["name"]): m["name"] for m in skill_meta.values()}
                 | {norm_skill(t["name"]): t["name"] for t in terms_parsed.values()})

    skill_hit, term_hit, family_hit, skill_miss = [], [], [], []
    for q, srcs in sorted(quoted.items()):
        nq = norm_skill(q)
        if nq not in official:
            if nq in term_by_norm:
                t = term_by_norm[nq]
                term_hit.append((q, t["kind"], t["members"], t["text"], sorted(srcs)))
                continue
            family = sorted({full for n, full in all_names.items()
                             if n != nq and n.startswith(nq)})
            if family:
                family_hit.append((q, family, sorted(srcs)))
            else:
                skill_miss.append((q, sorted(srcs)))
            continue
        sids: set[str] = set()
        for sid in official[nq]:
            sids |= group_of.get(sid, {sid})
        extra = sorted({skill_meta[s]["name"] for s in sids if norm_skill(skill_meta[s]["name"]) != nq})
        holders = sorted({h[0] for s in sids for h in skill_meta[s]["holders"]},
                         key=lambda n: (-ops[n]["rarity"], n) if n in ops else (0, n))
        skill_hit.append((q, extra, holders, sorted(srcs)))

    # 6. 数值锚点
    ov_path = docs / "2-\u4f53\u7cfb" / "\u4f53\u7cfb\u603b\u89c8.md"
    ov_rows = {}
    for line in corpus[ov_path].splitlines():
        if line.startswith("|") and line.count("|") >= 4:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[0] != "\u4f53\u7cfb" and not set(cells[0]) <= {"-", ":", " "}:
                ov_rows[cells[0]] = (cells[2], set(re.findall(r"\d+(?:\.\d+)?", cells[2])))
    sys_docs = {f.stem: t for f, t in corpus.items()
                if "2-\u4f53\u7cfb" in rel(f) and f.stem != "\u4f53\u7cfb\u603b\u89c8"}
    anchor_issues = []
    for sysname, (blurb, nums) in ov_rows.items():
        body = sys_docs.get(sysname)
        if body is None:
            anchor_issues.append((sysname, blurb, "\u603b\u89c8\u6709\u6b64\u4f53\u7cfb\uff0c"
                                                  "\u4f46\u6ca1\u6709\u540c\u540d\u6587\u6863", None))
            continue
        body_nums = set(re.findall(r"\d+(?:\.\d+)?", body))
        missing = sorted(n for n in nums if n not in body_nums and len(n) >= 2)
        if missing:
            anchor_issues.append((sysname, blurb,
                                  "\u603b\u89c8\u6570\u5b57\u5728\u672c\u4f53\u7cfb"
                                  "\u6587\u6863\u4e2d\u67e5\u4e0d\u5230", missing))

    # 7. 同效漏收
    rooms_of_interest = ("\u8d38\u6613\u7ad9", "\u5236\u9020\u7ad9",
                         "\u53d1\u7535\u7ad9", "\u63a7\u5236\u4e2d\u67a2")
    gaps = []
    for (room, desc), sids in by_desc.items():
        if room not in rooms_of_interest:
            continue
        holders = sorted({h[0] for s in sids for h in skill_meta[s]["holders"]})
        if len(holders) < 2:
            continue
        listed = [h for h in holders if h in covered]
        absent = [h for h in holders if h not in covered]
        if listed and absent:
            gaps.append({"room": room, "desc": desc,
                         "names": sorted({skill_meta[s]["name"] for s in sids}),
                         "listed": listed,
                         "absent": sorted(absent, key=lambda n: (-ops[n]["rarity"], n))})
    gaps.sort(key=lambda g: (rooms_of_interest.index(g["room"]), -len(g["absent"])))

    # 7.5 派系断言核对
    faction_issues = check_faction_assertions(corpus, rel, ops, terms_parsed)

    # 8. 简称自检
    alias_rows = []
    for alias, info in sorted(CORPUS_ALIASES.items()):
        targets, note = info["targets"], info["note"]
        bad = [t for t in targets if t not in ops]
        used = sorted(rel(f) for f, t in corpus.items() if alias in t)
        alias_rows.append((alias, targets, note, bad, used))

    # ---------------------------------------------------------------- 渲染
    L: list[str] = []
    w = L.append

    w("# 语料校对清单")
    w("")
    w("由 `.claude/skills/gongsun-changle/scripts/check_corpus.py` 生成——把 `docs/` 语料与全量")
    w(f"游戏数据（{len(ops)} 干员 / {len(skill_meta)} 基建技能 / {len(terms_parsed)} 官方术语，")
    w("来源见 `.claude/skills/gongsun-changle/references/数据源.md`）逐项对照。")
    w("")
    w("每条都带出处。改完语料重跑脚本即可复查。**本文件不是语料，不入问答索引。**")
    w("")

    w("## 0. 覆盖度")
    w("")
    w(f"- 名册 **{len(ops)}** 名干员，语料提到过 **{len(covered)}** 名"
      f"（{len(covered) * 100 // len(ops)}%）")
    w(f"- 未提及 **{len(ops) - len(covered)}** 名 —— 这部分只能答客观技能，不能给体系评价")
    class_terms = {t["name"] for t in terms_parsed.values() if t["kind"] == "\u5e72\u5458\u7ec4"}
    used_classes = sorted(t for t in class_terms if t in all_text)
    w(f"- 官方干员组 {len(class_terms)} 个，语料出现过 {len(used_classes)} 个："
      + "\u3001".join(used_classes))
    w("")

    w("## 1. 语料出现、名册没有的名字")
    w("")
    w("需逐条判断是错字、旧名、简称，还是根本不是干员名。")
    w("")
    for u in unknown:
        w(f"- `{u}` —— " + "\u3001".join(sorted(cand_src[u])))
    if not unknown:
        w("无。")
    w("")

    w("## 2. 练度记法（不是错误，但解析层必须认）")
    w("")
    w("语料用 `名II` 表示精 2、`名0` 表示白板。指代解析要能剥掉后缀，")
    w("否则这些写法会被当成不存在的干员。")
    w("")
    for c, srcs in tier_notation:
        w(f"- `{c}` —— " + "\u3001".join(sorted(srcs)))
    if not tier_notation:
        w("无。")
    w("")

    w("## 3. 星级标注错误")
    w("")
    if star_issues:
        w("| 文件 | 干员 | 语料 | 实际 |")
        w("|------|------|------|------|")
        for f, n, s, r in sorted(star_issues):
            w(f"| {f} | {n} | \u2606{s} | **\u2606{r}** |")
    else:
        w("无。")
    w("")

    w("## 4. 语料自用的简称与合称（人工维护）")
    w("")
    w("这些不是子串关系，无法从数据推出，维护在 `build_refs.py` 的 `ALIASES`")
    w("（同一份表也渲染进 `references/歧义.md` 供 skill 运行时查）。")
    w("「校验」列检查映射目标是否仍在名册中。")
    w("")
    w("| 简称 | 指向 | 校验 | 出处 | 备注 |")
    w("|------|------|------|------|------|")
    for alias, targets, note, bad, used in alias_rows:
        check = "OK" if not bad else "**目标不在名册：** " + "\u3001".join(bad)
        w(f"| {alias} | " + " + ".join(targets) + f" | {check} | "
          + ("\u3001".join(used) if used else "语料未出现") + f" | {note} |")
    w("")

    w("## 5. 语料引用的技能名 —— 与官方数据对上的")
    w("")
    w("`＝` 后是**效果描述逐字相同**的其他官方技能名（玩家会混用）；持有者是整组的，")
    w("可能多于语料所列。")
    w("")
    for q, extra, holders, srcs in skill_hit:
        w(f"- \u300c{q}\u300d" + ("\uff1d" + "\u3001".join(extra) if extra else ""))
        w("  - 持有者：" + "\u3001".join(holders))
        w("  - 出处：" + "\u3001".join(srcs))
    w("")

    w("## 6. 语料引用的官方术语（不是技能名，在术语表里）")
    w("")
    w("这些「」词条对应游戏内术语，权威成员列表见 `references/类别.md`。")
    w("")
    for q, kind, members, text, srcs in term_hit:
        w(f"- 「{q}」（{kind}）：" + ("、".join(members) if members else text))
        w("  - 出处：" + "、".join(srcs))
    if not term_hit:
        w("无。")
    w("")

    w("## 7. 族名引用（语料用族名指代整族技能）")
    w("")
    w("不是错误。语料写族名、官方名带 ·α/·β/·γ 档位后缀，解析层要能从族名展开到具体档位。")
    w("")
    for q, family, srcs in family_hit:
        w(f"- 「{q}」 → " + "、".join(family))
        w("  - 出处：" + "、".join(srcs))
    if not family_hit:
        w("无。")
    w("")

    w("## 8. 技能名和术语表都查不到的「」词条")
    w("")
    w("需人工分类：社区俗称要进 skill 的术语层；普通引号（强调、口语）忽略。")
    w("")
    for q, srcs in skill_miss:
        w(f"- \u300c{q}\u300d —— " + "\u3001".join(srcs))
    w("")

    w("## 9. 派系归属断言核对")
    w("")
    w("扫语料里带归属断言词（都是 / 属于 / 同为…）且提到官方干员组的句子，")
    w("检查被断言的干员是否真在该组成员表里。**异格干员经常不在本体的派系里**，")
    w("这类错误光靠通读发现不了——名字看着就该是一伙的。")
    w("")
    if faction_issues:
        for it in faction_issues:
            w(f"- **{it['file']}** ｜ 组：{it['group']}")
            w(f"  - 句子：{it['sent']}")
            w(f"  - **不在该组的干员**：" + "、".join(it["bad"]))
            w(f"  - 官方成员：" + "、".join(it["members"]))
    else:
        w("无。")
    w("")

    w("## 10. 体系总览 与 各体系文档 的数值不一致")
    w("")
    if anchor_issues:
        for sysname, blurb, kind, missing in anchor_issues:
            w(f"- **{sysname}** —— {kind}")
            w(f"  - 总览：{blurb}")
            if missing:
                w("  - 本文档查不到的数字：" + "\u3001".join(missing))
    else:
        w("无。")
    w("")

    w("## 11. 同效干员漏收")
    w("")
    w("每组内技能**效果描述逐字相同**。语料收了其中若干人却漏掉其余——效果一样，")
    w("缺人时可直接替换，多半是 `散件干员速查` 的补充机会。")
    w("")
    for g in gaps:
        w(f"- **{g['room']}** \uff5c" + "\uff1d".join(g["names"]))
        w(f"  - 效果：{g['desc']}")
        w("  - 语料已收：" + "\u3001".join(g["listed"]))
        w("  - **语料未收：**" + "\u3001".join(f"{n}\u2606{ops[n]['rarity']}" for n in g["absent"]))
    w("")

    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"写出 {out_path}")
    print(f"覆盖 {len(covered)}/{len(ops)}\uff5c未知名 {len(unknown)}\uff5c练度记法 {len(tier_notation)}"
          f"\uff5c星级 {len(star_issues)}\uff5c简称 {len(alias_rows)}\uff5c技能命中 {len(skill_hit)}"
          f"\uff5c未命中 {len(skill_miss)}\uff5c锚点 {len(anchor_issues)}\uff5c漏收组 {len(gaps)}")


if __name__ == "__main__":
    main()
