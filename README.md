# Arknights Base Vault

明日方舟基建知识库 + 问答 skill。语料以机制说明、体系论证和散件速查为主，供问答、检索增强和人工校对使用。

AI agent 在本仓库工作请先读 [`AGENTS.md`](AGENTS.md)。

## 校对入口

- 体系总览：`docs/2-体系/体系总览.md`
- 规则机制：`docs/0-规则/`
- 体系文档：`docs/2-体系/`
- 散件速查：`docs/4-散件工具人/散件干员速查.md`

建议先从体系总览看全局互斥和 243 示例，再按体系文件逐篇校对数值、练度门槛、互斥关系和缺人降级路径。

## 语料边界

- `docs/**/*.md` 是知识库正文，适合进入 RAG 索引。
- `meta/templates/` 是写作模板和系统提示词，不应作为玩家知识正文直接入库。
- `语料校对清单.md` 由脚本生成，供人工校对，不入库。

## 问答 skill

`.claude/skills/gongsun-changle/` 是基于本知识库的基建问答 skill。

**不绑定特定宿主。** 除 frontmatter 外，skill 全部是纯 markdown 与相对仓库根的路径——任何能读文件、能把一段 markdown 当指令执行的 agent 都可以用。

### 组成

| 路径 | 内容 | 维护方式 |
|------|------|---------|
| `SKILL.md` | 回答方针：作用域判定、指代解析、约束检查清单、边界判定、计算政策 | 人工 |
| `references/` | 425 干员名册、747 基建技能（按 9 设施分片，逐条标注解锁/提升）、81 条官方术语、82 组同效不同名技能、指代歧义表 | **机器生成，勿手改** |
| `guides/` | 基建物流链、截图读法 | 人工 |
| `scripts/` | `build_refs.py` 生成 references；`check_corpus.py` 生成语料校对清单 | 人工 |

### 安装

`references/` 已随仓库提供，**开箱即用——不需要 Python，也不需要另外两个数据仓库**。

```bash
git clone https://github.com/hansjohn819-commits/arknights-base-vault.git
```

按宿主分三种情况：

- **支持 Agent Skills 规范的** —— 把 `gongsun-changle/` 放进宿主的 skill 目录即可。注意 frontmatter 里的 `when_to_use` 是扩展字段，不在规范允许列表（`allowed-tools` / `compatibility` / `description` / `license` / `metadata` / `name`）内；严格校验的宿主需要把它的内容并进 `description`。
- **有自己的规则机制、格式不同的** —— skill 正文一个字都不用改，只换 frontmatter。
- **没有 skill 机制的** —— 仓库根的 [`AGENTS.md`](AGENTS.md) 已写好入口指令，宿主读到它就会去读 `SKILL.md`。或者直接告诉 agent：「读 `.claude/skills/gongsun-changle/SKILL.md`，按它的要求回答」。

**在仓库根目录启动 agent。** `SKILL.md` 里的路径都相对仓库根；在上层目录启动时它会退回 `arknights-base-vault/` 前缀，但部分宿主的 skill 发现机制不会加载嵌套目录里的 skill（Claude Code 就是这样——要等读写过该目录下的文件之后才可用，命令也不会出现在 `/` 菜单里）。

同理，**不建议复制到宿主的全局 skill 目录**：`SKILL.md` 的语料路径是相对本仓库写的（`docs/...`），复制走之后读不到语料，得自己改成绝对路径。

### 怎么用

直接问基建问题就行：「贸易站放谁」「巫恋核缺人怎么办」「243 怎么排」「为什么巫恋归零不影响裁缝」「XX 干员基建怎么样」。

宿主支持斜杠命令时也可以显式调用，命令名取自 skill 的目录名（在 Claude Code 下是 `/gongsun-changle`）。

回答范围限定在基建：排班、干员搭配、体系选择、设施效率、布局、缺人降级、基建机制。不涉及战斗、关卡、抽卡和战斗向的练度规划。需要精确产量或最优排班时会引导到 [可露希尔基建终端工具](https://riic.autos/)。

### 重新生成 references/

游戏版本更新之后需要。额外要 Python 3.10+，以及两个数据仓库与本仓库**互为兄弟目录**：

```
<任意父目录>/
  ├── arknights-base-vault/     本仓库
  ├── RIIC-Web/                 主源：干员目录、基建技能目录、官方术语表
  └── RhodeLogisticsSteward/    补源：roomType / efficiency / targets / 派系归属
```

```bash
python .claude/skills/gongsun-changle/scripts/build_refs.py
```

按上面的布局放好就不用带参数；放在别处用 `--workspace <公共父目录>` 指定。目录缺失时脚本会直接报错并提示，不会生成半成品。

### 校对语料

```bash
python .claude/skills/gongsun-changle/scripts/check_corpus.py
```

把 `docs/` 与全量数据逐项对照，在仓库根生成 `语料校对清单.md`：干员名与星级核对、练度记法、简称合称、技能名与官方数据的对应、派系归属断言核对、数值口径不一致、同效干员漏收。每条都带出处，改完语料重跑即可复查。

### 维护分工

**语料改 `docs/`，数据改上游后重跑脚本，两条线互不干扰。**

`references/` 是游戏客观数据（技能描述、派系归属、星级、解锁门槛），不是公孙的沉淀，所以放在 skill 侧而不是 `docs/`；`guides/` 是人工维护的读图与物流链说明，同理。

## 当前未覆盖

- `docs/3-单站组合/` 尚未补齐，用于后续整理双人/三人固定组合。真实提问里「六星一堆但体系核心一个没有」是高频场景，这块缺失时 13 篇体系文档对这类玩家基本不适用。
- 布局规划与参考产量尚未建立：252 在全语料只出现 2 次，也没有任何「产能算什么水平」的参考基准。
- 养成成本与回本参考尚未建立。
- `base_systems.json` 尚未建立，当前体系关系主要写在 Markdown front matter 和正文中。
- ~~`docs/5-cli求解器/`~~ 已废弃：求解器方案改为引导用户到 [可露希尔基建终端工具](https://riic.autos/)。

另有若干待裁决的语料问题（数值口径不一致、同效干员漏收等），由 `check_corpus.py` 生成的 `语料校对清单.md` 逐条列出并附出处。

