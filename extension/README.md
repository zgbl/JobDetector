# JobDetector — 岗位源头校验（Chrome 扩展）

在 LinkedIn / Indeed 浏览职位时，自动去**雇主自己的 ATS**（Greenhouse / Lever / Ashby /
Workable / SmartRecruiters / Workday / Breezy / Recruitee 等）校验**原始岗位是否仍在招聘**，
把结果以一个徽章直接标注在职位标题旁边。

- 源头还在招 → 可以放心投递
- 源头已关闭 → 这个岗位很可能只是 LinkedIn / Indeed 上的僵尸岗位，**无需投递**
- 无法判定 → 网络、反爬或页面结构问题

除此之外还提供两个能力：**直达源头投递**（跳过中间平台，直接打开 ATS 申请页）和
**Ghost Job 风险分析**（按需调用你自己的后端 LLM 服务，给出幽灵岗位风险分）。

---

## 1. 安装（Load unpacked）

1. 打开 Chrome，访问 `chrome://extensions`
2. 右上角打开 **开发者模式**
3. 点击 **加载已解压的扩展程序**
4. 选择本仓库的 `extension/` 目录（即本 README 所在目录）
5. 打开任意 LinkedIn / Indeed 职位页，职位标题右侧会出现徽章

无需构建、无需 npm、无第三方依赖：所有代码都是 Chrome 直接加载的普通 ES Module。

> 若徽章没出现：确认页面是 `linkedin.com/jobs/*` 或 `indeed.com/viewjob*`，
> 然后在 `chrome://extensions` 里点一次「重新加载」并刷新页面。

---

## 2. 徽章含义

| 徽章 | 含义 |
| --- | --- |
| `校验中…` | 正在请求后端 / 本地校验 |
| `🟢 源头在招` | 源头 ATS 明确返回该岗位仍在招 |
| `⚠️ 源头已关闭 · 无需投递` | 源头 ATS 已下架该岗位（404 / board 列表无此 ID / 截止日期已过） |
| `❓ 无法判定` | 无法访问或无法解释源头响应 |
| `🟠 后端不可用（本地校验）` | 后端请求失败，结果由扩展内置的本地校验产生（置信度通常更低） |

点击徽章展开详情卡片：

- **原因**：人类可读的判定理由（与后端返回的 `reason` 一致）
- **源头**：识别到的 ATS 名称
- **源头链接**：`canonical_url`
- **直达源头投递 →**：在新标签页打开 `apply_url`（`rel="noopener"`）
- **Ghost Job 风险分析**：调用 `POST /api/ghost/analyze`，展示 `one_liner`、`ghost_score`、
  `risk_factors[]`、`recommendation`。后端不可用时该按钮会被禁用并提示「需要后端服务」。

工具栏图标上的角标：`✓`（绿色，在招）/ `!`（红色，已关闭）/ `?`（灰色，无法判定）。

---

## 3. 后端 HTTP 契约

默认后端地址 `https://jobdetector.blackrice.top`，可在设置页修改
（`chrome.storage.sync` → `settings.backendBaseUrl`）。所有接口均为 CORS 开放
（`Access-Control-Allow-Origin: *`）。

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| POST | `/api/verify/source` | `{urls: string[], company, title, location, refresh: bool}` | `{count, results: VerifyResult[], lookup: VerifyResult \| null}` |
| POST | `/api/verify/lookup` | `{company, title}` | `{result: VerifyResult \| null}` |
| POST | `/api/ghost/analyze` | `{job_title, company_name, post_age_days: number\|null, source_type, jd_text, source_status}` | `{ghost_score, is_ghost_job, risk_factors[], recommendation, one_liner, provider, cached}` |
| GET | `/api/health` | — | `{"status": "ok", ...}`（设置页「测试连接」使用） |

`VerifyResult`（所有字段始终存在，未知取空字符串 / `null`）：

```
{ input_url, status: "open"|"closed"|"unknown", ats, confidence: 0..1, reason,
  canonical_url, apply_url, matched_title, company, location, posted_at,
  http_status: int|null, checked_at: ISO8601, elapsed_ms: int, cached: bool }
```

`/api/verify/source` 的 `lookup` 是后端的兜底结果：当页面里没有找到 ATS 链接时，
后端会用自己的公司库按 `company + title` 反查，可能是 `null`。

### 请求流程

1. 内容脚本抓取职位标题、公司、地点、页面上**所有**指向 ATS 的外链
   （含 `a[href]`、内嵌 JSON `<script>`、`data-*` 属性；Indeed 额外解析 `#applyJobLinkContainer a`）。
2. 后台 `POST /api/verify/source`（`AbortController` 超时 8s）。
3. 成功 → 取 `results` + `lookup`，按 `open > closed > unknown`、再按 `confidence` 选最佳结果。
4. 失败（网络错误 / 超时 / 未配置后端）→ 回退到本地校验，并在返回载荷里标记 `degraded: true`。

### 本地（离线）校验覆盖范围

`lib/ats.js` 的 `verifyLocal()` 不依赖后端，覆盖：

- **Greenhouse**：`GET boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}`，
  200 = 在招；404/410 时再查 board 列表二次确认（列表里有 = unlisted job post，无 = 已关闭）
- **Lever**：`GET api.lever.co/v0/postings/{token}/{id}`，404 时回退 board 列表比对
- **Ashby**：`GET api.ashbyhq.com/posting-api/job-board/{org}`，在 `jobs[]` 中按 `id` 匹配
- **通用页面探针**：HTTP 状态码（404/410 = 已关闭）+ 失效提示文案 + 是否被重定向到列表页

其它 ATS（Workable / SmartRecruiters / Workday / Breezy / Recruitee 等）只在
**后端可用**时校验；后端不可用时它们会返回「无法判定」。

---

## 4. 缓存模型

- 存储位置：`chrome.storage.local`，键 `jd_cache_v1`
- 缓存键：可识别来源时用 `ats|token|jobId`，否则用规范化后的 URL
- TTL（后台常量，位于 `background.js` 顶部）：
  - `open` → **12 小时**（可招聘状态稳定，变化慢）
  - `closed` / `unknown` → **6 小时**（负面结果更可能变化，比如岗位重新开放）
  - 若在设置页把 `cacheTtlHours` 改成其它值，则 `open` 用该值，`closed`/`unknown` 用其一半
- 容量上限 **500 条**，超出时按 `checkedAt` 从旧到新淘汰
- 点击「重新校验」会带 `refresh: true` **跳过缓存**并刷新该条记录

---

## 5. 隐私说明

- 扩展不收集、不上传任何浏览历史或账号信息。
- 页面抓取（职位标题、公司、地点、外链、JD 文本）**只在本地内存中使用**。
- 只有在以下两种情况才会向**你自己配置的后端**发起网络请求：
  1. 自动校验：发送页面 URL 列表 + 公司 + 职位名到 `POST /api/verify/source`
     （用于判断源头岗位是否还在）；
  2. 你**手动点击**「Ghost Job 风险分析」：才会把 JD 文本（截断到 6000 字符）
     发送到 `POST /api/ghost/analyze`。
- 除此之外，本地 ATS 校验会直接访问 Greenhouse / Lever / Ashby 的公开 job board API。
- 清空缓存：设置页 →「清空本地缓存」（删除 `jd_cache_v1`）。

---

## 6. 常见问题排查

**徽章一直显示「🟠 后端不可用（本地校验）」**
- 检查后端地址是否填写正确（设置页 → 测试连接），应返回 `{"status":"ok"}`。
- 打开 DevTools Console 看是否有 CORS 报错；后端需允许 `Access-Control-Allow-Origin: *`，
  并允许 `POST` + `Content-Type: application/json`（预检请求 `OPTIONS` 要返回 204/200）。
- 自签证书 / HTTPS 证书错误也会导致请求失败。

**徽章不出现**
- 只有 `linkedin.com/jobs/*`（`/jobs/view/*`、`/jobs/search*`、`/jobs/collections/*`）
  和 `indeed.com/viewjob*` 会被注入。
- 在设置页确认对应站点开关是打开的。
- LinkedIn 是 SPA：扩展已 patch `history.pushState/replaceState`、监听 `popstate`、
  用 `MutationObserver`（800ms 防抖）+ 2.5s 轮询兜底；若仍不出现请刷新整页。

**LinkedIn / Indeed 改了 DOM 结构**
- 站点适配器位于 `content/extract.js`。选择器失效时徽章会退化为
  「❓ 无法判定」或抓不到 JD 文本，但**不会**破坏页面。
- 修复方式：更新该文件里的 `*_TITLE` / `*_COMPANY` / `*_LOCATION` / `*_JD` 选择器数组即可。

**Ghost 分析按钮是灰的**
- 说明后端不可用（`degraded`），鼠标悬停会提示「需要后端服务」；
  修复后端连接后点「重新校验」即可恢复。

---

## 7. 目录结构

```
extension/
├── manifest.json          # MV3 清单（无图标、无构建）
├── background.js          # Service Worker：校验编排、缓存、角标、消息路由
├── lib/ats.js             # 纯函数：identifyAts / verifyLocal（无 chrome.*，可被 node 测试）
├── content/
│   ├── extract.js         # LinkedIn / Indeed 站点适配器（经典脚本，挂到 globalThis）
│   ├── content.js         # Shadow DOM 徽章 + 详情卡片 + SPA 导航监听
│   └── content.css        # 仅宿主元素定位样式
├── popup/                 # 工具栏弹窗
├── options/               # 设置页
└── test/ats.test.mjs      # node --test 单元测试
```

运行测试：

```bash
node --test extension/test/*.test.mjs
```

> Node.js 24 起，`node --test` 不再接受「目录」作为参数（`node --test extension/test/`
> 会报 `Cannot find module .../extension/test`），因此请使用上面的 glob 写法。
