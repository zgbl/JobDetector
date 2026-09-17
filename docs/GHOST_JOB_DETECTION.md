# 反 Ghost Job / 真岗位过滤

两层判定，**硬信号优先、软信号补充**：

```
        ┌──────────────────────────────────────────────┐
        │ ① 事实层  source_verify                      │
        │   源头 ATS 已下架？ → 直接 95~100 分，结案    │
        └──────────────────────────────────────────────┘
                          │ 源头还在（或未知）
                          ▼
        ┌──────────────────────────────────────────────┐
        │ ② 特征层  规则引擎（永远可用）                │
        │   挂单时长 / 源头可追溯性 / JD 泛化 / 常设招聘  │
        └──────────────────────────────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────────────────┐
        │ ③ 语义层  LLM（OpenRouter → DeepSeek → Gemini）│
        │   复核规则信号，输出一句话结论 + 投递建议      │
        └──────────────────────────────────────────────┘
```

代码：`src/services/ghost_score.py`，HTTP：`POST /api/ghost/analyze`。

---

## 1. 硬信号：源头状态

如果 `source_status == "closed"`，说明雇主自己的 ATS 已经没有这个 requisition 了——这不是概率问题，是事实。此时**不调用 LLM**，直接返回：

```json
{
  "ghost_score": 100,
  "is_ghost_job": true,
  "risk_factors": ["源头 ATS 已下架该岗位，招聘流程已结束"],
  "recommendation": "建议忽略",
  "one_liner": "源头 ATS 已下架该岗位，Indeed/LinkedIn 上属于陈旧挂单，不必投递。",
  "provider": "source_ats"
}
```

省一次 LLM 调用，也避免模型"讲和"。

## 2. 软信号：规则引擎（扣分制，累加后截断 0–100）

| 维度 | 触发条件 | 扣分 |
| --- | --- | --- |
| 发布时间 | 挂单 > 60 天 | +50 |
| | 挂单 > 30 天 | +30 |
| 源头可追溯性 | 无 ATS 直投入口 / 仅平台内一键投递 | +20 |
| | 疑似中介/聚合站二次抓取 | +25 |
| JD 泛化 | 内容 < 200 字，缺团队/技术栈细节 | +20 |
| | 命中 ≥2 个模板套话且 0 个具体技术栈 | +20 |
| 常设招聘 | 命中 `talent pool` / `evergreen` / `always hiring` / `人才库` 等 | +30 |
| 中介口吻 | 命中 `our client` / `on behalf of our client` / `猎头` / `代招` | +20 |
| **源头状态** | ATS 已下架 | **≥95（直接封顶）** |

判级：`>50` ⇒ `is_ghost_job = true`；`≥80` ⇒ 建议忽略；`50–80` ⇒ 建议去官网核实；`≤50` ⇒ 直接投递。

`risk_factors` 按扣分权重从高到低取前 3 条，保证用户看到的是**最关键**的理由，而不是碰巧先匹配到的规则。

## 3. 语义层：LLM 提示词

### 3.1 结构化评分（后端 API 使用，`SYSTEM_PROMPT`）

```
你是一个专业的招聘行业数据分析师和求职防诈骗专家。你的任务是分析给定的职位描述（Job Description）
及元数据，评估该岗位是否为"Ghost Job（幽灵岗位/虚假挂单）"或"中介二次抓取防失效岗位"。

评估标准（扣分制，累加后截断到 0-100）：
1. 发布时间：超过 30 天且无更新标识 +30；超过 60 天 +50。
2. 源头追溯性：无明确 ATS 跳转链接、仅平台内一键投递、或第三方中介抓取 +20。
3. JD 泛化程度：充斥模板化套话，缺乏具体团队、产品架构、明确技术栈要求 +20。
4. 招聘常设性：包含 "continuous talent pipeline"、"talent pool"、"general application"、
   "evergreen"、"always hiring" 等收集简历特征词 +30。
5. 源头状态：若已知源头 ATS 已下架该岗位，ghost_score 直接 >= 95。

只输出严格的 JSON，不要 markdown 代码块，不要解释：
{
  "ghost_score": 0-100 的整数,
  "is_ghost_job": true/false,
  "risk_factors": ["最多 3 条具体扣分原因"],
  "recommendation": "直接投递" | "建议去官网核实" | "建议忽略",
  "one_liner": "不超过 2 句话的直白评语，直接点出痛点，不要废话"
}
```

User prompt 会把**规则引擎的初步结论**一并交给模型复核（"若不同意可调整分数"），
这比让模型从零判断更稳定，也大幅降低了漏判。

### 3.2 前端极简版（Prompt 2）

插件侧不需要独立调用：`one_liner` 就是"不超过 2 句话的直白评语"，直接渲染在徽章卡片里。
若只想做轻量判别（不落库、不要 JSON），把 `provider` 设为 `heuristic` 即可拿到纯规则结论，零成本。

## 4. API 用法

```bash
# 让后端自己决定用哪个模型（AI_PROVIDER → 失败自动降级 DeepSeek → Gemini → 规则引擎）
curl -X POST https://jobdetector.blackrice.top/api/ghost/analyze \
  -H 'Content-Type: application/json' \
  -d '{
        "job_title": "Senior Platform Engineer",
        "company_name": "Mystery Staffing",
        "post_age_days": 75,
        "source_type": "unknown",
        "source_status": "unknown",
        "jd_text": "Our client is seeking a rockstar ninja for a fast-paced environment..."
      }'
```

```json
{
  "ghost_score": 100,
  "is_ghost_job": true,
  "risk_factors": [
    "挂单已 75 天，远超 60 天红线",
    "含常设招聘/人才库特征词：talent pool",
    "无明确源头 ATS 投递入口，仅平台内一键投递"
  ],
  "recommendation": "建议忽略",
  "one_liner": "典型中介抓取的幽灵岗位：75 天未更新、无 ATS 入口、JD 全是套话且明说进人才库，投了也大概率没人看。",
  "provider": "deepseek",
  "cached": false
}
```

| 端点 | 说明 |
| --- | --- |
| `POST /api/ghost/analyze` | 任意职位文本 → 评分 |
| `GET /api/ghost/analyze?job_id=<job_id>` | 直接对库里已抓取的岗位评分（自动取 posted_date / description / source） |

结果按 `md5(title|company|source_status|source_type|age|jd[:1500])` 缓存 **24 小时**（集合 `ghost_analyses`），避免同一岗位反复烧 token。

## 5. 模型降级链

```
payload.provider  ──┐
AI_PROVIDER（.env）─┴─▶ openrouter → deepseek → gemini → 规则引擎
```

- 任一 provider 抛错/返回不可解析内容 → 自动尝试下一个。
- 全挂 → 规则引擎兜底，接口**永远返回 200 和一个可用结论**（`provider: "heuristic"`）。
- `provider: "keyword"` 可强制只用规则引擎（省钱、离线可用）。

> ⚠️ 当前 `.env` 里 `OPENROUTER_MODEL=minimax/minimax-m2.5:free` 已被 OpenRouter 下架（404：
> "This model is unavailable for free"）。系统会自动降级到 `deepseek` 并正常工作；
> 若想继续用 OpenRouter，把该变量换成当前可用的免费模型即可。

## 6. 与主站的联动

| 数据 | 位置 | 用途 |
| --- | --- | --- |
| `source_status` | `jobs` 文档 | 前端可加"源头在招"标记 |
| `stale_reason` | `jobs` 文档 | 说明为什么被下架 |
| `is_active: false` | `jobs` 文档 | 推荐/摘要（`/api/recommendations`、daily digest）自动过滤 |
| `source_checks` | 独立集合 | 跨用户共享校验缓存 |
| `ghost_analyses` | 独立集合 | LLM 结果缓存 |

批量回填见 `scripts/verify_active_jobs.py`（`docs/SOURCE_VERIFICATION.md` 第 6 节）。

## 7. 后续可做的增强

1. **JD 指纹去重**：同一份 JD 在多个公司/中介下重复出现 ⇒ 强 Ghost 信号（`content_hash` 已存在，可直接聚合）。
2. **复用率检测**：中介把同一条岗位挂到 20 个城市 ⇒ 用 `content_hash + company` 统计。
3. **更新频率**：每次复检记录 `updated_at`，如果 ATS 记录的更新时间超过 90 天但岗位仍挂着，加权。
4. **用户反馈闭环**：把插件里的"投递后无人回复"回传，作为监督信号校准权重。
