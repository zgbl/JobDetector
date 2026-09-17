# 自动公司发现（Company Discovery）

> 一句话：**让系统自己找新公司** —— 从外部招聘信息里挖出库里没有的公司，解析出它用的 ATS，
> 存进待审表，人工确认后再进主库被抓取。

之前整条管线的"喂料"是写死的清单（`companies_initial.yaml`、Ben Lang 名单），
所以系统永远不会自己长大。这个进程补上了最前面那一步。

```
外部源 ──▶ ① seed ──▶ ② resolve ──▶ ③ 待审表 ──▶ [人工批准] ──▶ companies ──▶ 已有的抓取管线
 HN / YC      候选公司     解析 ATS       company_candidates      review CLI      is_active=True     prod_scraper
```

---

## 1. 两个外部源

| 源 | 是什么 | 为什么选它 | 实测产出 |
| --- | --- | --- | --- |
| `hn` | Hacker News **"Ask HN: Who is hiring?"**（Algolia API，无需 key） | 每月一期，全是工程岗，正好对上 AI/Infra 方向；**约 19% 的帖子直接贴了 ATS 链接** | 单期 262 条顶层帖 → 246 家公司、188 个域名、47 个 ATS 直链 |
| `yc` | YC 公司目录（社区镜像 `yc-oss.github.io`，无需 key） | 6225 家，带 `isHiring`、批次、行业，可按行业筛 | 可按批次/行业精确取用 |

## 2. ATS 解析：三条路径，按可靠性排序

| 顺序 | 方式 | 说明 | 置信度 |
| --- | --- | --- | --- |
| 1 | `post_link` | 帖子里就带了 ATS 链接，直接取 token | 0.95 |
| 2 | `slug_probe` | 用公司名/域名/YC slug 并发探测 7 家 ATS 的公开 board API | 0.5 ~ 0.9 |
| 3 | `careers_crawl` | 复用 `ats_discovery.py` 爬官网 → careers 页 → 找 ATS 链接 | 0.8 |

**支持的 ATS**：Greenhouse、Lever、Ashby、Workable、Recruitee、SmartRecruiters、BambooHR
（BambooHR 是这次为发现流程新加的，同时补进了校验层和抓取层）。

**只有 board 真返回 ≥1 个岗位才算解析成功** —— 避免把猜错的 token 写进库。

## 3. 反污染设计

自动发现最大的风险是把垃圾写进库。所以：

- **候选不直接进 `companies`**，先落 `company_candidates`，状态 `pending`
- **去重**：按 board token、公司名、域名三重比对现有 `companies`，同批次内也去重
- **置信度**：猜出来的 token 分数更低（0.5），会显示在审核列表里
- **名称/token 不一致告警**：例如 `Neon Commerce → token "Neon"`，会标 ⚠️ 提醒人工确认
- **相关性打分**（0–10）：基于目标赛道关键词（platform / infra / cloud / k8s / LLM…）+ 资深级别词
- **`--min-jobs` / `--min-relevance`** 双重门槛
- **`--dry-run`** 完全不写库

## 4. 怎么用

```bash
# 只看看会找到什么（不写库）
python scripts/discover_companies.py --source hn --months 1 --max-resolve 40 --dry-run

# 正式跑：最近 2 期 HN，最多解析 70 家，只要 ≥2 个岗位且相关性 ≥2
python scripts/discover_companies.py --source hn --months 2 --max-resolve 70 \
    --workers 10 --min-jobs 2 --min-relevance 2

# YC 源：按批次 + 行业
python scripts/discover_companies.py --source yc \
    --batches "Winter 2026,Fall 2025" --industries "Artificial Intelligence,Developer Tools"

# 两个源一起
python scripts/discover_companies.py --source hn,yc --max-resolve 120
```

审核（这一步是必须的）：

```bash
python scripts/review_candidates.py --stats                        # 总体情况
python scripts/review_candidates.py --list --min-jobs 5            # 看候选
python scripts/review_candidates.py --approve-all --min-jobs 5 --min-relevance 4
python scripts/review_candidates.py --approve <id> [<id>...]       # 单条批准
python scripts/review_candidates.py --reject <id>                  # 拒绝（不会再被自动更新覆盖）
python scripts/review_candidates.py --approve-all --min-jobs 5 --scrape-now   # 批准后立刻抓
```

批准会把公司按现有 `Company` 模型写入 `companies`（`is_active=True`），
**之后走的就是原有的抓取管线**：下一个 6 小时周期 `prod_scraper.py` 会自动抓它，
再经过 IT 过滤 / 英文过滤 / 去重后写入 `jobs`。

## 5. 定时

`.github/workflows/discover_companies.yml` 每周一跑一次，只做"发现 + 落待审表"，
**不会自动批准**。也可以手动触发（`workflow_dispatch`）并指定源和期数。

## 6. 数据结构

`company_candidates`：

```js
{
  name, normalized_name, domain,
  source: "hn_whoishiring" | "yc_directory",
  source_url, source_title, source_context,   // 可追溯到原始帖子
  ats, ats_url, board_token, open_jobs, sample_titles,
  relevance_score, matched_keywords, it_jobs,
  resolve_method, confidence, warning,
  status: "pending" | "approved" | "rejected" | "duplicate",
  fingerprint,                                 // ats|token / domain|x / name|x
  discovered_at, resolved_at, reviewed_at, notes
}
```

公司侧新增字段：`discovered_via`、`discovered_at`、`discovery_confidence`、`discovery_resolve_method`。

## 7. 实测数据（2026-09-17，HN 最近 2 期）

- 解析 70 家候选 → **31 家解析出 ATS**（22 个 post_link + 9 个 slug_probe）
- 过滤后保留 **24 家**，去重后新增 **20 条待审候选**
- ATS 分布：ashby 15、greenhouse 3、lever 1、recruitee 1
- 典型产出：SentiLink（56 岗）、Prior Labs（24 岗）、Langfuse（6 岗）、vCluster Labs（22 岗）

## 8. 已知边界

- **大厂走不通 slug 探测**：Google/Meta/Apple 这类用 Workday/自建系统，公司名猜 token 必然失败，
  要靠 `careers_crawl` 或人工补 `ats_url`。
- **小初创可能根本没有 ATS**（用 Notion 表单/邮件收简历），解析不出来是正常的。
- **知乎式误判**：HN 帖子格式自由，偶尔会把地点当公司名（已针对性修复 `NYC | ONSITE ...`、
  `Remote (US) Close (...)`、`Bethesda MD ...` 等模式，并有单测覆盖）。
- **slug 探测有撞名风险**：`Tether`、`Vitalize` 这类通用词可能撞到别家公司，
  所以置信度低、会进待审表而不是直接入库。
- **HN 是英文社区**，只适合补充英语岗位；非英语市场需要别的源。
