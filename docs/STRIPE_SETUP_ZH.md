# JobDetector：Vercel / Stripe 配置步骤

## 1. 配置 Production 环境变量

打开 https://vercel.com/xtus-projects/job-detector/settings/environment-variables 。

逐项添加变量，Environment 选择 **Production**。密钥变量使用 Sensitive/Secret（如果界面提供）。

| 变量名 | 值 |
| --- | --- |
| `STRIPE_SECRET_KEY` | JobDetector 专用的正式环境 `sk_live_…`，不要使用 TensuGo 的 key |
| `STRIPE_WEBHOOK_SECRET` | JobDetector webhook 对应的 `whsec_…` |
| `BILLING_ENABLED` | `false`（配置检查完成后改成 `true`） |

确认已有的 `BASE_URL` 为 `https://jobdetector.blackrice.top`，`ADMIN_EMAIL` 为 Tuxy 已验证登录账号的邮箱；不要覆盖其他现有配置。

Webhook 地址：https://dashboard.stripe.com/acct_1UCW9tFC3kxu6kUO/workbench/webhooks/we_1USU2cFC3kxu6kUO0K4VnhqR 。在 Signing secret 处查看或复制签名密钥。它与 API secret key 不同。

月付和年付 Price ID 已在服务端配置，无需重复添加：

- 月付 $1：`price_1USTeLFC3kxu6kUOBgyDTB6A`
- 年付 $9.99：`price_1USTfIFC3kxu6kUOZksDu146`

Stripe 托管 Checkout 不需要前端 Publishable key。

## 2. 重新部署

保存变量后，进入 JobDetector → **Deployments** → 最新 Production 部署 → **… → Redeploy**，等待 Ready。

仅保存环境变量不会更新已经运行的部署。

## 3. 检查配置

以 Tuxy 账号登录 https://jobdetector.blackrice.top/admin-traffic.html ，点击 **Check Stripe setup**。

应验证月付 USD $1.00/month、年付 USD $9.99/year，且为 Live mode；此检查不会扣款。

在 Stripe Workbench 的 JobDetector webhook 中发送签名测试事件，确认投递响应成功。真实支付、取消订阅及权益开通仍需完成端到端验证。

## 4. 开启收费

检查完成后，把 Production 的 `BILLING_ENABLED` 改为 `true`，再执行一次 Redeploy。

开启后，普通用户可免费预览 10 个搜索，订阅后解锁全部搜索。Tuxy 管理员拥有全部搜索权限。

## 入口

- 搜索 Console：https://jobdetector.blackrice.top/linkedin-search.html
- Tuxy 流量后台：https://jobdetector.blackrice.top/admin-traffic.html

## 当前已核验状态

- 正式月付、年付 Stripe 价格已经 API 验证。
- JobDetector webhook 已启用，配置了所需的 8 项订阅事件。
- Vercel 环境变量是否保存、部署是否完成，必须在 Vercel 中核实；不能由 Stripe 配置成功推断。
- 文档不包含任何完整密钥。

## Webhook 页面要勾选的项目（完整保留）

- Events from：**Your account**
- Payload style：**Snapshot**（不要选 Thin）
- API version：`2026-08-26.dahlia`
- Endpoint URL：`https://jobdetector.blackrice.top/api/billing/webhook`
- Destination name：`JobDetector subscriptions`
- Selected events：以下 **8 项**全部勾选：

```text
checkout.session.completed
checkout.session.async_payment_succeeded
checkout.session.async_payment_failed
customer.subscription.created
customer.subscription.updated
customer.subscription.deleted
invoice.paid
invoice.payment_failed
```

现有 JobDetector webhook 已补齐这 8 项，不需要重新创建。用户已决定直接开启收费：`BILLING_ENABLED=true`，保存后 Redeploy。

## 管理订阅

管理员入口：https://jobdetector.blackrice.top/admin-traffic.html#subscriptions 。

订阅管理展示用户、套餐及周期金额、状态与权限、最新账单实收、开始日期、到期或下次续费时间。支持搜索、状态/套餐筛选、CSV 导出、逐人分页账单，以及 Stripe 管理入口。只有配置的 Tuxy 账号可访问真实数据。
