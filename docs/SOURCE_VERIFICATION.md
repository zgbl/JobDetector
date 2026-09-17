# 源头校验层（Source Verification）

> 一句话：**脱离中间商二次抓取，直接比对源头 ATS 状态。**
> 求职者在 Indeed / LinkedIn 上刷岗位时，插件直接标注"源头已关闭，无需投递"。

本文件描述后端部分（校验引擎 + API）。前端浏览器插件见 [`extension/README.md`](../extension/README.md)。

---

## 1. 为什么要做这一层

Indeed / LinkedIn 上的岗位有两类：

| 类型 | 表现 | 真相 |
| --- | --- | --- |
| 实时同步 | "Apply on company site" 直接跳转到雇主 ATS | 源头在招，可以投 |
| 陈旧挂单 / Ghost Job | 岗位早就招满或取消，页面仍然挂着 | 投了没人看，纯浪费简历 |

聚合站不会主动下线职位（下线等于损失流量和广告库存）。唯一可靠的事实来源是**雇主自己的 ATS**。
所以核心逻辑只有一句：**拿到申请链接 → 识别 ATS → 问源头 API → 还在不在。**

## 2. 覆盖的 ATS 与判定依据

| ATS | 识别特征 | 判定接口 | 判"已关闭"的依据 |
| --- | --- | --- | --- |
| Greenhouse | `boards.greenhouse.io`、`job-boards.greenhouse.io`、任意带 `?gh_jid=` 的官网链接 | `boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}` | 详情 404 **且** board 列表无此 ID |
| Lever | `jobs.lever.co/{token}/{uuid}` | `api.lever.co/v0/postings/{token}/{id}` | 详情 404 **且** 列表无此 ID |
| Ashby | `jobs.ashbyhq.com/{org}/{uuid}` | `api.ashbyhq.com/posting-api/job-board/{org}` | board 返回的 `jobs[]` 中无该 id（含 `isListed=false` 降级处理） |
| Workable | `apply.workable.com/{token}/j/{code}`、`/j/{code}` 短链 | `apply.workable.com/api/v1/widget/accounts/{token}?details=true` | 列表无此 shortcode；短链重定向到 `/oops` |
| SmartRecruiters | `jobs.smartrecruiters.com/{Company}/{id}` | `api.smartrecruiters.com/v1/companies/{token}/postings/{id}` | 404 |
| Workday | `{tenant}.wdN.myworkdayjobs.com/{locale}/{site}/job/...` | `{host}/wday/cxs/{tenant}/{site}{externalPath}` | 404；或 `endDate` 已过期 |
| Breezy | `{token}.breezy.hr/p/{id}` | `{board}/json` | 列表无此 id |
| Recruitee | `{token}.recruitee.com/o/{slug}` | `{token}.recruitee.com/api/offers/` | 列表无此 slug |
| Personio | `{token}.jobs.personio.de/job/{id}` | XML feed | feed 中无此 id |
| Teamtailor | `{token}.teamtailor.com/jobs/{id}` | `jobs.json` feed | feed 中无此 id |
| 其它 / 自建 career page | 兜底 | 真实 HTTP 请求 | HTTP 404/410；失效文案；重定向到列表页；JSON-LD `validThrough` 过期 |

所有接口都是 ATS 厂商自己渲染岗位页用的公开 endpoint，**不需要任何 API Key**。

### 安全设计：绝不误报"已关闭"

误报的代价很高（用户会放弃一个真实岗位）。因此：

- 详情 404 时**必须**再用 board 列表二次确认；列表读不到就返回 `unknown` 而不是 `closed`。
- 只有列表明确不含该 ID 才判 `closed`，此时 `confidence ≈ 0.95+`。
- 兜底页探测最多给 `confidence 0.5–0.75`，并在 `reason` 里写明依据。
- `confidence` 会一路透传到插件 UI，低置信度显示为"疑似"。

## 3. 目录与代码位置

| 文件 | 作用 |
| --- | --- |
| `src/services/source_verify.py` | 校验引擎：URL 识别、10 家 ATS handler、兜底页面探测、`VerifyResult` 模型 |
| `api/index.py` | HTTP 层：`/api/verify/source`、`/api/verify/lookup`、`/api/verify/stats` + MongoDB 共享缓存 |
| `scripts/verify_active_jobs.py` | 批量复检：把库里已失效的岗位 `is_active=False` |
| `extension/` | Chrome MV3 插件（实时标注） |

## 4. API

### `POST /api/verify/source`

```bash
curl -X POST https://jobdetector.blackrice.top/api/verify/source \
  -H 'Content-Type: application/json' \
  -d '{
        "urls": ["https://job-boards.greenhouse.io/stripe/jobs/999999999"],
        "company": "Stripe",
        "title": "Abuse Investigator"
      }'
```

```jsonc
{
  "count": 1,
  "results": [ { "status": "closed", "ats": "greenhouse", "confidence": 0.97,
                 "reason": "Greenhouse 源头已下架该岗位（详情 404 且 board 列表无此 ID）",
                 "checked_at": "2026-09-17T20:06:46+00:00", "cached": false } ],
  "lookup":  { "status": "open", "ats": "greenhouse", "confidence": 0.98,
               "matched_title": "Abuse Investigator", "match_source": "greenhouse_board",
               "apply_url": "https://stripe.com/jobs/search?gh_jid=8172487" },
  "best":    { "...": "results 与 lookup 中信息量最大的那条" },
  "alternative": null,
  "company_known": true
}
```

**`best` 的选择规则（避免误报）：**

1. 只要页面里存在**明确的单岗位链接**（URL 里带 job id）且高置信度（≥0.85），就以它为准 —— 即使它说 `closed`，也不会被模糊匹配到的"同类在招岗位"覆盖。
2. 这种情况下如果 `lookup` 找到了另一个**在招**的相似职位，会放进 `alternative`，插件会显示"同类在招：<职位> 投这个 →"。
3. 页面里没有明确的单岗位链接时（Indeed/LinkedIn 站内页很常见），才使用 `lookup` 的结果。

- `results`：对传入的每个候选链接逐一校验。
- 每条结果都同时带 `reason`（中文，插件用）和 `reason_en`（英文，网页用）。两条语言由
  `src/services/source_verify.py` 的 `_REASON_EN_RULES` 统一生成，`tests/test_source_verify.py::test_every_reason_has_an_english_rule`
  会扫描源码里所有中文 reason 字面量，漏翻译直接让 CI 失败。
- `lookup`：**当 URL 里没有 ATS 信息时（Indeed/LinkedIn 常见）的后备路径**——用公司名+职位名去查：
  1. 先查 JobDetector 自己的 `jobs` 库（我们早就抓过这条岗位，直接拿 `source_url` 复检）；
  2. 再查该公司的实时 ATS board 列表，做标题模糊匹配（token 相似度 ≥ 0.55）；
  3. board 活着但找不到该职位 → 判定 `closed`（`confidence 0.6`，理由会写明"board 在招 N 个但没有这个"）。
  4. **两条路径都会执行，`open` 优先**：库里那条可能已经下架，而 board 上还有一条标题略有差别的在招职位 —— 只报"已关闭"会是误判。
- 公司 → board token 的映射来自 `companies` 集合（`ats_url` / `ats_system.api_endpoint`，缺失时用公司名/域名推导）。

### 其它端点

| 端点 | 说明 |
| --- | --- |
| `GET /api/verify/source?url=&company=&title=` | 单 URL 便捷版 |
| `POST /api/verify/lookup` | 只做公司+职位定位，返回 `{result, company_known}` |
| `GET /api/verify/stats` | 缓存量、按状态/ATS 分布、最近判定为关闭的岗位 |

## 5. 三级缓存

```
① 插件本地   chrome.storage.local   同岗位 12h（closed 6h），即时渲染，零网络
② 服务端     MongoDB source_checks  open 12h / closed 24h / unknown 1h，键 = ats|token|jobId
③ 事实来源   ATS API                真实状态，只在缓存过期或 refresh=true 时打
```

`source_checks` 文档结构：

```js
{ key: "greenhouse|stripe|8172487", status: "open", ats: "greenhouse",
  result: { /* 完整 VerifyResult */ }, checked_at: ISODate(...), hits: 42 }
```

用户 A 校验过的热门岗位，用户 B 浏览时直接命中（毫秒级返回）。

## 6. 批量复检（写入主库）

```bash
# 先看会改什么（不写库）
python scripts/verify_active_jobs.py --limit 200 --dry-run

# 复检最近 30 天抓到的岗位，8 并发
python scripts/verify_active_jobs.py --days 30 --workers 8

# 单公司、绕过 24h 内的重复校验
python scripts/verify_active_jobs.py --company Stripe --recheck-after 0
```

判定为 `closed` 的岗位会写入：

```js
{ is_active: false, source_status: "closed",
  stale_reason: "Greenhouse 源头已下架该岗位（详情 404 且 board 列表无此 ID）",
  source_checked_at: ISODate(...), deactivated_by: "source_verify" }
```

在招的岗位写入 `source_status: "open"` + `source_checked_at`。
可选：把 `scripts/verify_active_jobs.py` 加进 cron / GitHub Action，每天跑一次增量复检。

> 实测（2026-09-17，最新 150 条在招岗位）：145 open / 3 closed / 2 unknown ⇒ **约 2% 的在库岗位源头已经关闭**。

## 7. 已知边界

- **Workable 的 `jobs.workable.com/view/{id}`** 形式拿不到 board token，只能走兜底页探测。
- **iCIMS / Eightfold / 自建系统**没有统一公开接口，只能靠兜底页探测（JS 渲染页面容易返回 `unknown`）。
- **Workday** 详情接口依赖 URL 里的 `site`；若公司改过站点名会返回 404（此时会被判 `unknown` 而非 `closed`，不会误报）。
- 高频调用可能被 ATS 限流；批量脚本请把 `--workers` 控制在 10 以内。
