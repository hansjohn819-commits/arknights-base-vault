# Arknights Base Vault

明日方舟基建 RAG 知识库。当前语料以机制说明、体系论证和散件速查为主，供后续问答、检索增强和人工校对使用。

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

`.claude/skills/gongsun-changle/` 是基于本知识库的基建问答 skill（Claude Code）。

### 安装

前置：[Claude Code](https://claude.com/claude-code)。

**只想用它回答问题** —— `references/` 已随仓库提供，开箱即用，**不需要 Python，也不需要另外两个数据仓库**：

```bash
git clone https://github.com/hansjohn819-commits/arknights-base-vault.git
```

```bash
cd arknights-base-vault
```

```bash
claude
```

**必须在仓库根目录启动**。skill 装在仓库自己的 `.claude/skills/` 下，如果你在**上层目录**启动，Claude Code 不会在启动时加载它——嵌套目录里的 skill 要等读写过该目录下的文件之后才可用，命令也不会出现在 `/` 菜单里。

**想重新生成 `references/`**（游戏版本更新之后）—— 额外需要 Python 3.10+，以及两个数据仓库与本仓库**互为兄弟目录**：

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

**装成全局 skill？** 技术上可以把 `gongsun-changle/` 复制到 `~/.claude/skills/`，但 `SKILL.md` 里的语料路径是相对本仓库写的（`docs/...`），复制走之后要自己改成绝对路径，否则读不到语料。不推荐。

### 怎么用

两种触发方式：

- **手动**：输入 `/gongsun-changle`
- **自动**：直接问基建问题即可，Claude 会自己判断要不要加载。比如「贸易站放谁」「巫恋核缺人怎么办」「243 怎么排」「为什么巫恋归零不影响裁缝」「XX 干员基建怎么样」

回答范围限定在基建：排班、干员搭配、体系选择、设施效率、布局、缺人降级、基建机制。不涉及战斗、关卡、抽卡和战斗向的练度规划。需要精确产量或最优排班时会引导到 [可露希尔基建终端工具](https://riic.autos/)。

### 目录结构

| 路径 | 内容 |
|------|------|
| `SKILL.md` | 回答方针、指代解析流程、约束检查清单、计算政策 |
| `references/` | **机器生成，请勿手改**。425 干员名册、747 基建技能（按设施分片，标注解锁/提升）、81 条官方术语、82 组同效技能、指代歧义表 |
| `guides/` | 人工维护。基建物流链、截图读法 |
| `scripts/build_refs.py` | 从 `RIIC-Web` 与 `RhodeLogisticsSteward` 的本地数据合并生成 `references/` |
| `scripts/check_corpus.py` | 把 `docs/` 与全量数据对照，生成 `语料校对清单.md` |

数据更新后重跑：

```bash
python .claude/skills/gongsun-changle/scripts/build_refs.py
```

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

