# JobDetector — User Guide

> 所有功能在 Web 页面上的入口地图。作者自己也能快速找到东西。

---

## 🌐 站点 URL

| 环境 | 地址 |
|------|------|
| 生产 | https://jobdetector.blackrice.top |
| 本地 | http://localhost:8123 |

---

## 📍 页面入口地图

### 顶部导航栏（所有用户可见）

| 导航项 | URL | 功能 |
|--------|-----|------|
| **Jobs** | `/` | 主职位列表，搜索 + 筛选 |
| **Favorites** | `/favorites.html` | 收藏的公司 + 该公司职位 |
| **Companies** | `/?view=companies` | 所有公司列表（点顶部 "Companies" 或公司数量卡片） |
| **🎯 My Digest** | `/my_digest.html` | 个人 AI 求职推送控制台 (登录后可见) ← **今天新加** |
| **My Searches** | 点击弹窗 | 已保存的搜索条件 + Email Alert 管理 |
| **Feedback** | `/feedback.html` | 用户反馈表单 |

### 顶部导航栏（仅 Admin 登录后可见）

| 导航项 | URL | 功能 |
|--------|-----|------|
| **Admin Dashboard** | `/admin_stats.html` | 访客统计 + 用户反馈管理 + 公司申请 |

> Admin 账户 = `.env` 中 `ADMIN_EMAIL` 对应的账户。登录后导航栏自动出现 Admin 入口。

---

## 🔍 功能详解

### 1. 职位搜索（主页 `/`）

**入口路径：** 顶部 Nav → Jobs → 搜索框 / 筛选栏

| 操作 | 方法 |
|------|------|
| 关键词搜索 | Hero 搜索框 或 Filter 栏 Keyword 输入框 |
| 多关键词 AND | 输入词后按 **Enter** 形成 Tag，可叠加 |
| 地区筛选 | Location 输入框 + Enter，支持 USA / Japan / Remote 等 |
| 类别筛选 | Category 下拉（Engineering / AI / Product 等）|
| 时间筛选 | "Any Time" 下拉 → Last 24h / 3d / 7d / 30d |
| 远程 Only | 顶部 pill 按钮 "Remote Only" |
| 按公司筛选 | 点击职位卡片上的公司名 → 公司详情 → 公司职位列表 |
| 保存搜索 | Filter 栏右侧 🔖 按钮 或 "Create Job Alert" |

---

### 2. 保存搜索 & Email Alert

**入口路径：** 主页 → Filter 栏 → 🔖 书签按钮 / "Create Job Alert" 按钮

| 步骤 | 说明 |
|------|------|
| 1. 设置好筛选条件 | 关键词、地区、类别等 |
| 2. 点击 🔖 或 "Create Job Alert" | 弹出保存框 |
| 3. 填写名称，勾选 "Send email alerts" | 每次 scraper 运行后匹配新职位自动发邮件 |
| 4. 管理已保存搜索 | Nav → "My Searches" → 查看 / 删除 / 开关 Alert |

> ⚠️ 需要登录账户。最多保存 5 条搜索。

---

### 3. 公司收藏（Favorites）

**入口路径：** Nav → Favorites，或在 Companies 页面点击 ⭐ 按钮

- 收藏的公司会在 Favorites 页面展示其所有 Active 职位
- 需要登录账户

---

### 4. 🎯 My Career Digest（个人 AI 求职推送）← **今天新加**

**入口路径：** 主页顶部 Nav → **"🎯 My Digest"**（登录后出现）

**功能：**
- 手动触发 AI Digest：从数据库最新职位中用 Gemini / MiniMax / Keyword 打分
- 过滤出符合自己赛道的岗位，生成精美 HTML 邮件发给自己
- 查看历次运行历史（时间 / 匹配数 / 是否成功 / 发送地址）
- 配置：Lookback 天数、最多显示数量、最低 AI 分数、AI 提供商

**自动调度：** GitHub Actions 每天 8:00 AM ET 自动运行（需要设置 Secrets）

详细配置见：[DEVELOPMENT.md → 本地测试](./DEVELOPMENT.md) | [SystemDesign.md §0.2](../Design/SystemDesign.md)

---

### 5. Admin Dashboard

**入口路径：** Nav → **Admin Dashboard**（Admin 登录后出现）

| 功能 | 说明 |
|------|------|
| 访客统计 | 总访问数、唯一访客、Top Referrer |
| 用户反馈 | 查看所有 Feedback 条目 |
| 公司申请 | 查看用户申请新增爬取的公司 |

---

### 6. 用户注册 / 登录

**入口路径：** 右上角 "Sign In" 按钮

| 操作 | 说明 |
|------|------|
| 登录 | 输入 Email + 密码 |
| 注册 | 点 "Register" → 填写信息 → 查邮件验证 |
| 忘记密码 | 登录框 → "Forgot Password?" → 输入 Email → 查邮件重置 |

---

## 🔗 快速链接速查

```
主页          /
公司列表      /?view=companies
收藏夹        /favorites.html
反馈          /feedback.html
Admin 统计    /admin_stats.html       ← Admin Only
My Digest     /my_digest.html         ← Admin Only
API 健康检查  /api/health
```

---

## 💡 关于 User Guide 的建议

> 这份 User Guide 放在 `docs/USER_GUIDE.md` 是合适的。理由：
>
> - **`Design/`** 目录 = 技术架构 / 系统设计文档（给开发者）
> - **`docs/`** 目录 = 使用指南 / 操作手册（给用户 / 自己）
>
> 两者目标读者不同，不要混在一起。当功能增加时，记得先更新这里。
