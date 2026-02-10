# JobDetector 系统设计文档

> **文档说明**：本文档包含完整的生产级架构设计和MVP（最小可用产品）设计。  
> - **MVP设计**（第1-3节）：适合快速开发Demo，2-3周内可完成  
> - **完整架构**（第4节开始）：适合生产环境，功能完整的系统

---

## 0. 💡 当前实现架构 (Implemented Architecture)

目前项目已实现为 **Serverless Full-Stack** 架构，主要由以下三部分协同工作：

### 1. 技术栈协作 (Collaboration)
*   **Web (Frontend)**: 基于 **Vanilla JS** 的单页应用逻辑。负责用户交互、URL 路由、状态管理。通过 `fetch` API 与 Python 后端通信。
*   **Python (Backend)**: 基于 **FastAPI** 的 RESTful API。
    *   **API Runner**: 生产环境运行在 **Vercel Serverless Functions** 上；本地开发使用 **Uvicorn** (`port 8123`)。
    *   **Automation**: 爬虫脚本 (`scripts/`) 通过 **GitHub Actions** 每 6 小时定时运行。
*   **MongoDB (Database)**: 存储层。使用 **MongoDB Atlas** (云端) 或本地实例。作为 Scrapers (推数据) 和 API (读数据) 的中心枢纽。

### 2. 运行流程 (Runners)
| 环节 | 技术/运行器 | 说明 |
| :--- | :--- | :--- |
| **数据抓取** | **GitHub Actions** | 周期性运行 `prod_scraper.py` 抓取数据并存入 MongoDB。 |
| **API 服务** | **Vercel / Uvicorn** | 处理前端请求，执行 Auth、收藏、搜索等业务逻辑。 |
| **前端展现** | **Vercel CDN** | 静态分发 HTML/CSS/JS，极速加载。 |

> 详情请参阅专用文档：[Web_Architecture.md](./Web_Architecture.md)

---

# 📦 PART 1: MVP 设计（Demo阶段）

## 1. MVP 架构概述

### 1.1 设计目标
- ⚡ **快速验证**：2-3周内完成可用Demo
- 💰 **零成本**：使用免费云服务
- 🎯 **核心功能**：抓取 → 存储 → 匹配 → 通知
- 🔧 **易维护**：单体架构，降低复杂度

### 1.2 MVP 功能范围

**包含功能：**
- ✅ 支持1-2个数据源（LinkedIn + Indeed）
- ✅ 基础职位数据抓取
- ✅ 简单的关键词匹配
- ✅ 邮件通知
- ✅ 命令行界面（CLI）

**暂不包含：**
- ❌ Web 用户界面（可选：简单的静态HTML）
- ❌ 用户认证系统
- ❌ 复杂的评分算法
- ❌ 数据分析和可视化
- ❌ 多用户支持（仅支持单用户配置）

---

## 2. MVP 技术架构

### 2.1 简化架构图

```mermaid
graph TB
    subgraph "单体应用 Monolithic App"
        A[Python 主程序]
        
        subgraph "数据采集模块"
            B1[LinkedIn Scraper]
            B2[Indeed Scraper]
        end
        
        subgraph "核心逻辑"
            C1[数据解析器]
            C2[去重检查]
            C3[关键词匹配]
        end
        
        D[定时调度<br/>APScheduler]
        E[邮件发送<br/>SMTP]
    end
    
    F[(MongoDB Atlas<br/>免费512MB)]
    G[配置文件<br/>config.yaml]
    
    D --> B1
    D --> B2
    B1 --> C1
    B2 --> C1
    C1 --> C2
    C2 --> F
    F --> C3
    C3 --> E
    A --> D
    A --> G
    
    style F fill:#00C853
    style G fill:#FFB300
```

### 2.2 MVP 技术栈

| 层次 | 技术选型 | 说明 |
|-----|---------|------|
| **编程语言** | Python 3.11+ | 简单高效 |
| **爬虫框架** | Playwright | 支持动态网页 |
| **数据库** | MongoDB Atlas | 免费512MB，Schema灵活 |
| **ORM/ODM** | PyMongo / Motor | MongoDB官方驱动 |
| **调度** | APScheduler | 内嵌式调度，无需外部依赖 |
| **配置管理** | PyYAML | 简单的配置文件 |
| **通知** | smtplib (Gmail) | Python标准库 |
| **CLI** | Click / Typer | 命令行界面 |
| **部署** | 单机运行 | 个人电脑或单台VPS |

**核心依赖（requirements.txt）：**
```txt
playwright==1.40.0
pymongo==4.6.0
motor==3.3.2  # 异步MongoDB驱动（可选）
apscheduler==3.10.4
pyyaml==6.0.1
click==8.1.7
python-dotenv==1.0.0
beautifulsoup4==4.12.2
fake-useragent==1.4.0
```

### 2.3 为什么选择 MongoDB？

**对比分析：**

| 特性 | MongoDB | PostgreSQL | 评估 |
|-----|---------|-----------|------|
| **Schema 灵活性** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 职位数据格式不统一 ✅ |
| **快速迭代** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | MVP需要频繁调整结构 ✅ |
| **免费额度** | 512MB | 500MB | 相当 |
| **复杂查询** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | MVP仅需简单查询 |
| **ORM支持** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | PyMongo足够简单 |
| **数组/JSON** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 原生支持，非常适合 ✅ |

**结论**：MVP阶段选择 MongoDB，生产环境可以根据需求重新评估。

---

## 3. MVP 数据模型（MongoDB）

### 3.1 Collections 设计

```javascript
// Collection: jobs
{
  "_id": ObjectId("..."),
  "job_id": "linkedin_123456",  // 唯一标识
  "title": "Senior Software Engineer",
  "company": "Google",
  "location": "Mountain View, CA",
  "salary": {
    "min": 150000,
    "max": 200000,
    "currency": "USD"
  },
  "job_type": "Full-time",
  "remote_type": "Hybrid",
  "description": "We are looking for...",
  "requirements": ["5+ years Python", "AWS experience"],
  "skills": ["Python", "AWS", "Docker", "Kubernetes"],
  "source": "linkedin",
  "source_url": "https://linkedin.com/jobs/...",
  "posted_date": ISODate("2026-02-04T10:00:00Z"),
  "scraped_at": ISODate("2026-02-04T14:00:00Z"),
  "is_active": true,
  "raw_data": { /* 原始JSON */ }
}

// Collection: user_preferences (单用户配置)
{
  "_id": ObjectId("..."),
  "user_email": "your_email@gmail.com",
  "keywords": ["python", "backend", "AWS"],
  "exclude_keywords": ["frontend", "junior"],
  "locations": ["Remote", "San Francisco", "New York"],
  "min_salary": 120000,
  "job_types": ["Full-time", "Contract"],
  "required_skills": ["Python", "AWS"],
  "preferred_skills": ["Docker", "Kubernetes"],
  "min_match_score": 60,  // 0-100
  "notification_enabled": true,
  "created_at": ISODate("2026-02-04T00:00:00Z"),
  "updated_at": ISODate("2026-02-04T14:00:00Z")
}

// Collection: job_matches
{
  "_id": ObjectId("..."),
  "job_id": "linkedin_123456",
  "matched_at": ISODate("2026-02-04T14:30:00Z"),
  "match_score": 85,
  "matched_criteria": {
    "keywords": true,
    "location": true,
    "salary": true,
    "skills": 0.8  // 80%技能匹配
  },
  "is_notified": true,
  "notified_at": ISODate("2026-02-04T14:31:00Z")
}

// Collection: scraper_logs (可选：用于调试)
{
  "_id": ObjectId("..."),
  "source": "linkedin",
  "status": "success",  // success, failed
  "jobs_found": 25,
  "jobs_new": 3,
  "error_message": null,
  "started_at": ISODate("2026-02-04T14:00:00Z"),
  "completed_at": ISODate("2026-02-04T14:05:00Z")
}
```

### 3.2 索引设计

```javascript
// jobs collection 索引
db.jobs.createIndex({ "job_id": 1 }, { unique: true })
db.jobs.createIndex({ "source_url": 1 }, { unique: true })
db.jobs.createIndex({ "scraped_at": -1 })
db.jobs.createIndex({ "company": 1 })
db.jobs.createIndex({ "skills": 1 })

// job_matches collection 索引
db.job_matches.createIndex({ "job_id": 1 })
db.job_matches.createIndex({ "matched_at": -1 })
```

---

## 3. MVP 项目结构

```
JobDetector-MVP/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── config/
│   └── config.yaml          # 用户偏好配置
│
├── src/
│   ├── __init__.py
│   ├── main.py              # 主入口
│   │
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py          # 抽象基类
│   │   ├── linkedin.py      # LinkedIn爬虫
│   │   └── indeed.py        # Indeed爬虫
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py    # MongoDB连接
│   │   └── models.py        # 数据模型
│   │
│   ├── matcher/
│   │   ├── __init__.py
│   │   └── matcher.py       # 简单匹配逻辑
│   │
│   ├── notifier/
│   │   ├── __init__.py
│   │   └── email.py         # 邮件通知
│   │
│   └── utils/
│       ├── __init__.py
│       ├── config.py        # 配置加载
│       └── logger.py        # 日志工具
│
├── scripts/
│   ├── setup_db.py          # 初始化数据库
│   └── test_scraper.py      # 测试爬虫
│
└── logs/
    └── .gitkeep
```

### 3.1 核心代码示例

**main.py（简化版调度器）：**

```python
#!/usr/bin/env python3
"""
JobDetector MVP - 主程序
"""
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

from src.database.connection import get_db
from src.scrapers.linkedin import LinkedInScraper
from src.scrapers.indeed import IndeedScraper
from src.matcher.matcher import JobMatcher
from src.notifier.email import EmailNotifier
from src.utils.config import load_config
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class JobDetectorMVP:
    def __init__(self):
        self.config = load_config()
        self.db = get_db()
        self.scrapers = [
            LinkedInScraper(self.config),
            IndeedScraper(self.config)
        ]
        self.matcher = JobMatcher(self.config)
        self.notifier = EmailNotifier(self.config)
    
    def run_scraping_job(self):
        """执行一次完整的抓取-匹配-通知流程"""
        logger.info("=" * 50)
        logger.info(f"开始任务: {datetime.now()}")
        
        all_new_jobs = []
        
        # 1. 抓取数据
        for scraper in self.scrapers:
            try:
                logger.info(f"抓取 {scraper.name} ...")
                jobs = scraper.scrape(
                    keywords=self.config['search']['keywords'],
                    location=self.config['search']['location']
                )
                
                # 2. 保存到数据库（自动去重）
                new_jobs = self.save_jobs(jobs, scraper.name)
                all_new_jobs.extend(new_jobs)
                
                logger.info(f"{scraper.name}: 发现 {len(jobs)} 个职位, 新增 {len(new_jobs)} 个")
                
            except Exception as e:
                logger.error(f"{scraper.name} 抓取失败: {e}")
        
        # 3. 匹配和通知
        if all_new_jobs:
            self.match_and_notify(all_new_jobs)
        else:
            logger.info("没有新职位")
        
        logger.info(f"任务完成: {datetime.now()}\n")
    
    def save_jobs(self, jobs, source):
        """保存职位到数据库，返回新增职位"""
        new_jobs = []
        for job in jobs:
            # 检查是否已存在
            existing = self.db.jobs.find_one({"job_id": job['job_id']})
            if not existing:
                job['scraped_at'] = datetime.utcnow()
                job['is_active'] = True
                self.db.jobs.insert_one(job)
                new_jobs.append(job)
            else:
                # 更新 scraped_at
                self.db.jobs.update_one(
                    {"job_id": job['job_id']},
                    {"$set": {"scraped_at": datetime.utcnow()}}
                )
        return new_jobs
    
    def match_and_notify(self, jobs):
        """匹配职位并发送通知"""
        prefs = self.config['preferences']
        matched_jobs = []
        
        for job in jobs:
            score = self.matcher.calculate_score(job, prefs)
            if score >= prefs['min_match_score']:
                # 保存匹配结果
                match_record = {
                    "job_id": job['job_id'],
                    "matched_at": datetime.utcnow(),
                    "match_score": score,
                    "is_notified": False
                }
                self.db.job_matches.insert_one(match_record)
                
                job['match_score'] = score
                matched_jobs.append(job)
        
        # 发送通知
        if matched_jobs:
            logger.info(f"发现 {len(matched_jobs)} 个匹配职位，发送邮件...")
            success = self.notifier.send(
                to_email=prefs['user_email'],
                jobs=matched_jobs
            )
            
            if success:
                # 更新通知状态
                for job in matched_jobs:
                    self.db.job_matches.update_one(
                        {"job_id": job['job_id']},
                        {"$set": {
                            "is_notified": True,
                            "notified_at": datetime.utcnow()
                        }}
                    )
                logger.info(f"✅ 邮件发送成功")
            else:
                logger.error("❌ 邮件发送失败")

def main():
    """主函数"""
    detector = JobDetectorMVP()
    
    # 创建调度器
    scheduler = BlockingScheduler()
    
    # 每2小时运行一次
    scheduler.add_job(
        detector.run_scraping_job,
        CronTrigger(hour='*/2'),  # 每2小时
        id='job_scraping',
        name='职位抓取任务',
        replace_existing=True
    )
    
    # 立即执行一次
    logger.info("🚀 JobDetector MVP 启动")
    detector.run_scraping_job()
    
    # 启动调度器
    logger.info("⏰ 调度器已启动，每2小时运行一次")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("程序已停止")

if __name__ == "__main__":
    main()
```

**config.yaml 示例：**

```yaml
# MongoDB 连接
database:
  uri: "mongodb+srv://username:password@cluster.mongodb.net/"
  database_name: "jobdetector"

# 搜索配置
search:
  keywords:
    - "python developer"
    - "backend engineer"
  location: "Remote"

# 用户偏好
preferences:
  user_email: "your_email@gmail.com"
  
  # 必须包含的关键词（OR关系）
  keywords:
    - python
    - backend
    - django
    - fastapi
  
  # 排除关键词
  exclude_keywords:
    - junior
    - intern
    - frontend
  
  # 地点（OR关系）
  locations:
    - Remote
    - "San Francisco"
    - "New York"
  
  # 薪资要求（年薪USD）
  min_salary: 100000
  
  # 职位类型
  job_types:
    - Full-time
    - Contract
  
  # 必须技能（至少匹配50%）
  required_skills:
    - Python
    - AWS
  
  # 加分技能
  preferred_skills:
    - Docker
    - Kubernetes
    - PostgreSQL
  
  # 最低匹配分数（0-100）
  min_match_score: 60

# 邮件配置
email:
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  username: "your_email@gmail.com"
  password: "your_app_password"  # Gmail App Password

# 爬虫配置
scraper:
  headless: true
  timeout: 30
  max_jobs_per_search: 50
```

**简化的匹配器（matcher.py）：**

```python
from typing import Dict, List

class JobMatcher:
    """简单的职位匹配器"""
    
    def __init__(self, config):
        self.config = config
    
    def calculate_score(self, job: Dict, preferences: Dict) -> float:
        """
        计算匹配分数（0-100）
        
        评分标准：
        - 关键词匹配: 30分
        - 技能匹配: 30分
        - 地点匹配: 20分
        - 薪资匹配: 20分
        """
        score = 0
        
        # 1. 关键词匹配（30分）
        score += self._keyword_score(job, preferences) * 30
        
        # 2. 技能匹配（30分）
        score += self._skills_score(job, preferences) * 30
        
        # 3. 地点匹配（20分）
        score += self._location_score(job, preferences) * 20
        
        # 4. 薪资匹配（20分）
        score += self._salary_score(job, preferences) * 20
        
        # 排除关键词检查（一票否决）
        if self._has_excluded_keywords(job, preferences):
            return 0
        
        return round(score, 2)
    
    def _keyword_score(self, job: Dict, prefs: Dict) -> float:
        """关键词匹配分数 (0-1)"""
        text = f"{job.get('title', '')} {job.get('description', '')}".lower()
        keywords = prefs.get('keywords', [])
        
        if not keywords:
            return 1.0
        
        matched = sum(1 for kw in keywords if kw.lower() in text)
        return matched / len(keywords)
    
    def _skills_score(self, job: Dict, prefs: Dict) -> float:
        """技能匹配分数 (0-1)"""
        job_skills = [s.lower() for s in job.get('skills', [])]
        required = [s.lower() for s in prefs.get('required_skills', [])]
        preferred = [s.lower() for s in prefs.get('preferred_skills', [])]
        
        if not required and not preferred:
            return 1.0
        
        # 必须技能匹配度
        required_score = 0
        if required:
            matched = sum(1 for skill in required if skill in job_skills)
            required_score = matched / len(required)
            if required_score < 0.5:  # 必须技能至少匹配50%
                return 0
        else:
            required_score = 1.0
        
        # 加分技能匹配度
        preferred_score = 0
        if preferred:
            matched = sum(1 for skill in preferred if skill in job_skills)
            preferred_score = matched / len(preferred)
        else:
            preferred_score = 1.0
        
        # 7:3 权重
        return required_score * 0.7 + preferred_score * 0.3
    
    def _location_score(self, job: Dict, prefs: Dict) -> float:
        """地点匹配分数 (0-1)"""
        job_location = job.get('location', '').lower()
        preferred_locations = [loc.lower() for loc in prefs.get('locations', [])]
        
        if not preferred_locations:
            return 1.0
        
        # 完全匹配
        for loc in preferred_locations:
            if loc in job_location or job_location in loc:
                return 1.0
        
        # Remote 特殊处理
        if any('remote' in loc for loc in preferred_locations):
            if 'remote' in job_location or job.get('remote_type') == 'Remote':
                return 1.0
        
        return 0
    
    def _salary_score(self, job: Dict, prefs: Dict) -> float:
        """薪资匹配分数 (0-1)"""
        min_salary = prefs.get('min_salary', 0)
        if min_salary == 0:
            return 1.0
        
        salary_data = job.get('salary', {})
        job_min = salary_data.get('min', 0)
        job_max = salary_data.get('max', 0)
        
        # 没有薪资信息，给0.5分（不确定）
        if job_min == 0 and job_max == 0:
            return 0.5
        
        # 最低薪资满足要求
        if job_min >= min_salary:
            return 1.0
        # 最高薪资满足要求
        elif job_max >= min_salary:
            return 0.7
        else:
            return 0
    
    def _has_excluded_keywords(self, job: Dict, prefs: Dict) -> bool:
        """检查是否包含排除关键词"""
        text = f"{job.get('title', '')} {job.get('description', '')}".lower()
        excluded = prefs.get('exclude_keywords', [])
        
        return any(kw.lower() in text for kw in excluded)
```

---

## 3.3 MVP 开发步骤

### Step 1: 环境准备（1天）
```bash
# 1. 创建项目
mkdir JobDetector-MVP && cd JobDetector-MVP

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 安装 Playwright 浏览器
playwright install chromium

# 5. 注册 MongoDB Atlas（免费）
# https://www.mongodb.com/cloud/atlas/register
# 创建集群，获取连接URI

# 6. 配置 Gmail App Password
# https://myaccount.google.com/apppasswords
```

### Step 2: 实现爬虫（3-5天）
- 实现 LinkedIn 基础爬虫
- 实现 Indeed 基础爬虫
- 测试数据提取准确性

### Step 3: 数据库集成（1-2天）
- MongoDB 连接配置
- 数据模型定义
- CRUD 操作封装

### Step 4: 匹配和通知（2-3天）
- 实现简单匹配算法
- 实现邮件通知
- 配置文件加载

### Step 5: 调度和测试（2-3天）
- 集成 APScheduler
- 端到端测试
- 错误处理和日志

**总计：10-15天完成MVP**

---

## 3.4 快速启动命令

```bash
# 一次性运行
python src/main.py

# 后台运行（Linux/Mac）
nohup python src/main.py > logs/jobdetector.log 2>&1 &

# 使用 systemd（生产环境）
sudo systemctl start jobdetector
sudo systemctl enable jobdetector
```

---

## 3.5 MVP到完整版本的迁移路径

| 功能 | MVP | 完整版 | 迁移难度 |
|-----|-----|--------|---------|
| 数据库 | MongoDB | PostgreSQL | 中等（数据导出导入） |
| 缓存 | 无 | Redis | 简单（增量添加） |
| 调度 | APScheduler | Celery | 中等（重构任务） |
| 用户界面 | CLI | Web | 高（全新开发） |
| 部署 | 单机 | Docker | 简单（容器化） |

---

# 📊 PART 2: 完整架构设计（生产级）

> **以下为原完整设计，保持不变**

## 4. 系统概述（生产级）

### 1.1 项目目标
JobDetector 是一个自动化的职位信息收集和推荐系统，能够：
- 自动从多个招聘网站抓取最新职位信息
- 将职位数据存储到本地数据库
- 根据用户自定义的筛选条件匹配合适的职位
- 当发现匹配的职位时，通过邮件或其他方式发送提醒

### 1.2 核心功能
1. **多源数据抓取**：支持 LinkedIn、Indeed、Glassdoor、公司官网等多个数据源
2. **智能去重**：识别并过滤重复的职位信息
3. **个性化匹配**：基于技能、薪资、地点、职位类型等多维度筛选
4. **实时通知**：Email、Slack、Webhook 等多种通知方式
5. **数据分析**：职位趋势分析、薪资分析等

---

## 2. 系统架构设计

### 2.1 整体架构

```mermaid
graph TB
    subgraph "数据采集层 Data Collection Layer"
        A1[LinkedIn Scraper]
        A2[Indeed Scraper]
        A3[Glassdoor Scraper]
        A4[Company Sites Scraper]
        A5[API Integrations]
    end
    
    subgraph "调度层 Scheduler Layer"
        B1[Cron Jobs / APScheduler]
        B2[Rate Limiter]
    end
    
    subgraph "数据处理层 Data Processing Layer"
        C1[Data Parser]
        C2[Data Validator]
        C3[Deduplication Engine]
        C4[Job Matcher]
    end
    
    subgraph "存储层 Storage Layer"
        D1[(PostgreSQL / MySQL)]
        D2[(Redis Cache)]
    end
    
    subgraph "通知层 Notification Layer"
        E1[Email Service]
        E2[Slack Integration]
        E3[Webhook Handler]
    end
    
    subgraph "Web界面层 Web Interface"
        F1[Dashboard]
        F2[User Preferences]
        F3[Analytics]
    end
    
    A1 --> B2
    A2 --> B2
    A3 --> B2
    A4 --> B2
    A5 --> B2
    
    B1 --> A1
    B1 --> A2
    B1 --> A3
    B1 --> A4
    B1 --> A5
    
    B2 --> C1
    C1 --> C2
    C2 --> C3
    C3 --> D1
    D1 --> C4
    C4 --> E1
    C4 --> E2
    C4 --> E3
    
    D1 <--> D2
    F1 --> D1
    F2 --> D1
    F3 --> D1
```

### 2.2 技术架构层次

| 层次 | 技术选型 | 说明 |
|-----|---------|------|
| **数据采集** | Python + Scrapy/Playwright | 支持静态和动态网页抓取 |
| **任务调度** | APScheduler / Celery + Redis | 分布式任务调度 |
| **后端服务** | Python FastAPI / Flask | RESTful API 服务 |
| **数据库** | PostgreSQL | 主数据存储 |
| **缓存** | Redis | 缓存和消息队列 |
| **前端** | React / Vue.js | 用户配置界面 |
| **容器化** | Docker + Docker Compose | 环境一致性 |

---

## 3. 技术栈详细选型

### 3.1 数据抓取技术

#### 推荐方案：Python + 组合工具链

**核心库选择：**

1. **Scrapy** - 结构化数据抓取
   - 优点：高性能、内置去重、支持中间件
   - 适用场景：静态网页、API 接口
   
2. **Playwright / Selenium** - 动态网页抓取
   - 优点：完整浏览器环境、处理 JavaScript 渲染
   - 适用场景：React/Vue 等 SPA 应用、需要登录的网站
   
3. **BeautifulSoup4** - HTML 解析
   - 优点：简单易用、灵活
   - 适用场景：简单页面解析

4. **Requests-HTML** - 轻量级动态内容
   - 优点：介于 Requests 和 Playwright 之间
   - 适用场景：轻度 JavaScript 渲染

**反爬虫策略：**
```python
# 用户代理轮换
from fake_useragent import UserAgent
# 代理IP池
from rotating_proxies import RotatingProxyMiddleware
# 请求限流
from scrapy.extensions.throttle import AutoThrottle
# Captcha 处理
from anticaptchaofficial.recaptchav2proxyless import *
```

### 3.2 数据存储方案

#### PostgreSQL 数据库设计

**优势：**
- JSONB 支持：灵活存储非结构化职位描述
- 全文搜索：内置 FTS 支持技能和描述搜索
- 事务支持：数据一致性保证
- 成熟稳定：大量 ORM 支持

**Redis 缓存设计：**
- 已抓取 URL 缓存（去重）
- 匹配结果临时缓存
- 任务队列（Celery backend）

### 3.3 任务调度方案

#### 方案对比

| 方案 | 优点 | 缺点 | 适用场景 |
|-----|------|------|---------|
| **APScheduler** | 轻量级、易集成 | 单机运行 | 小型项目 |
| **Celery + Redis** | 分布式、可扩展 | 配置复杂 | 生产环境 |
| **Airflow** | 可视化管理、强大 | 重量级 | 复杂调度需求 |

**推荐：**
- 初期：APScheduler（快速开发）
- 生产：Celery + Redis（可扩展）

### 3.4 通知服务

**邮件服务：**
```python
# SMTP (Gmail, Outlook)
import smtplib
from email.mime.multipart import MIMEMultipart

# 第三方服务
# SendGrid API
from sendgrid import SendGridAPIClient
# AWS SES
import boto3
```

**即时通知：**
- Slack Webhooks
- Discord Webhooks
- Telegram Bot API
- 微信公众号/企业微信

### 3.5 前端技术

**推荐栈：**
- **框架**：React with TypeScript
- **UI 库**：Ant Design / Material-UI
- **状态管理**：Redux Toolkit / Zustand
- **数据可视化**：Recharts / Chart.js

---

## 4. 数据模型设计

### 4.1 数据库 Schema

```sql
-- 用户表
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 职位表
CREATE TABLE jobs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255) UNIQUE NOT NULL,  -- 外部职位ID
    title VARCHAR(500) NOT NULL,
    company VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    salary_min INTEGER,
    salary_max INTEGER,
    salary_currency VARCHAR(10) DEFAULT 'USD',
    job_type VARCHAR(50),  -- Full-time, Part-time, Contract, etc.
    remote_type VARCHAR(50),  -- Remote, Hybrid, On-site
    description TEXT,
    requirements TEXT,
    benefits TEXT,
    skills JSONB,  -- ["Python", "AWS", "Docker"]
    source VARCHAR(100) NOT NULL,  -- LinkedIn, Indeed, etc.
    source_url TEXT NOT NULL,
    posted_date TIMESTAMP,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    raw_data JSONB,  -- 原始抓取数据
    CONSTRAINT unique_job_source UNIQUE(source, source_url)
);

-- 用户偏好设置
CREATE TABLE user_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    preference_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_user_pref UNIQUE(user_id, preference_name)
);

-- 匹配条件
CREATE TABLE match_criteria (
    id SERIAL PRIMARY KEY,
    preference_id INTEGER REFERENCES user_preferences(id) ON DELETE CASCADE,
    criterion_type VARCHAR(50) NOT NULL,  -- keyword, location, salary, etc.
    criterion_value JSONB NOT NULL,  -- 灵活存储各种条件
    priority INTEGER DEFAULT 1,  -- 1-5 优先级
    is_required BOOLEAN DEFAULT FALSE  -- 是否必须满足
);

-- 匹配结果
CREATE TABLE job_matches (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    preference_id INTEGER REFERENCES user_preferences(id),
    match_score FLOAT,  -- 0-100 匹配分数
    matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_notified BOOLEAN DEFAULT FALSE,
    notified_at TIMESTAMP,
    user_feedback VARCHAR(50),  -- interested, not_interested, applied
    CONSTRAINT unique_user_job_match UNIQUE(user_id, job_id, preference_id)
);

-- 通知记录
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    match_id INTEGER REFERENCES job_matches(id) ON DELETE CASCADE,
    notification_type VARCHAR(50) NOT NULL,  -- email, slack, etc.
    status VARCHAR(50) DEFAULT 'pending',  -- pending, sent, failed
    sent_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 数据源配置
CREATE TABLE scraper_configs (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) UNIQUE NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    scrape_frequency_minutes INTEGER DEFAULT 60,
    last_scrape_at TIMESTAMP,
    config_data JSONB,  -- 特定配置参数
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引优化
CREATE INDEX idx_jobs_company ON jobs(company);
CREATE INDEX idx_jobs_location ON jobs(location);
CREATE INDEX idx_jobs_posted_date ON jobs(posted_date DESC);
CREATE INDEX idx_jobs_scraped_at ON jobs(scraped_at DESC);
CREATE INDEX idx_jobs_skills ON jobs USING GIN(skills);
CREATE INDEX idx_job_matches_user_id ON job_matches(user_id);
CREATE INDEX idx_job_matches_matched_at ON job_matches(matched_at DESC);
```

### 4.2 数据流图

```mermaid
sequenceDiagram
    participant Scheduler
    participant Scraper
    participant Parser
    participant DB
    participant Matcher
    participant Notifier
    
    Scheduler->>Scraper: 触发抓取任务
    Scraper->>Scraper: 访问目标网站
    Scraper->>Parser: 返回原始HTML/JSON
    Parser->>Parser: 提取结构化数据
    Parser->>DB: 检查是否重复
    alt 非重复数据
        Parser->>DB: 插入新职位
        DB->>Matcher: 触发匹配流程
        Matcher->>DB: 查询用户偏好
        Matcher->>Matcher: 计算匹配分数
        alt 匹配成功
            Matcher->>DB: 保存匹配结果
            Matcher->>Notifier: 发送通知请求
            Notifier->>Notifier: Email/Slack通知
            Notifier->>DB: 更新通知状态
        end
    else 重复数据
        Parser->>DB: 更新 scraped_at
    end
```

---

## 5. 核心模块设计

### 5.1 数据抓取模块

**目录结构：**
```
scrapers/
├── __init__.py
├── base_scraper.py          # 抽象基类
├── linkedin_scraper.py      # LinkedIn 实现
├── indeed_scraper.py        # Indeed 实现
├── glassdoor_scraper.py     # Glassdoor 实现
├── company_scraper.py       # 公司官网通用爬虫
├── utils/
│   ├── proxy_manager.py     # 代理管理
│   ├── user_agent.py        # UA 轮换
│   └── captcha_solver.py    # 验证码处理
└── middlewares/
    ├── rate_limit.py        # 限流中间件
    └── error_handler.py     # 错误处理
```

**核心代码示例：**

```python
# base_scraper.py
from abc import ABC, abstractmethod
from typing import List, Dict
import logging

class BaseScraper(ABC):
    """抓取器基类"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
    @abstractmethod
    async def scrape(self, keywords: List[str], location: str = None) -> List[Dict]:
        """
        抓取职位信息
        
        Args:
            keywords: 搜索关键词列表
            location: 地点
            
        Returns:
            职位列表
        """
        pass
    
    @abstractmethod
    def parse_job_detail(self, html: str) -> Dict:
        """解析职位详情"""
        pass
    
    def normalize_job_data(self, raw_data: Dict) -> Dict:
        """数据标准化"""
        return {
            'title': raw_data.get('title', '').strip(),
            'company': raw_data.get('company', '').strip(),
            'location': self._normalize_location(raw_data.get('location')),
            'salary_min': self._extract_salary(raw_data, 'min'),
            'salary_max': self._extract_salary(raw_data, 'max'),
            'description': raw_data.get('description', ''),
            'skills': self._extract_skills(raw_data.get('description', '')),
            'source': self.config['source_name'],
            'source_url': raw_data.get('url'),
            'posted_date': self._parse_date(raw_data.get('posted_date')),
            'raw_data': raw_data
        }
```

### 5.2 匹配引擎模块

**匹配算法：**

```python
# matcher.py
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class MatchCriterion:
    type: str  # keyword, location, salary, skills
    value: any
    priority: int  # 1-5
    is_required: bool

class JobMatcher:
    """职位匹配引擎"""
    
    def calculate_match_score(self, job: Dict, criteria: List[MatchCriterion]) -> float:
        """
        计算匹配分数
        
        算法：加权评分
        - 必须条件不满足：直接返回 0
        - 可选条件：根据优先级加权计算
        """
        total_score = 0
        max_possible_score = 0
        
        for criterion in criteria:
            weight = criterion.priority * 20  # 优先级转换为权重
            max_possible_score += weight
            
            if criterion.is_required:
                if not self._check_criterion(job, criterion):
                    return 0  # 必须条件不满足
                total_score += weight
            else:
                if self._check_criterion(job, criterion):
                    total_score += weight
        
        return (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0
    
    def _check_criterion(self, job: Dict, criterion: MatchCriterion) -> bool:
        """检查单个条件"""
        if criterion.type == 'keyword':
            return self._keyword_match(job, criterion.value)
        elif criterion.type == 'location':
            return self._location_match(job, criterion.value)
        elif criterion.type == 'salary':
            return self._salary_match(job, criterion.value)
        elif criterion.type == 'skills':
            return self._skills_match(job, criterion.value)
        return False
    
    def _keyword_match(self, job: Dict, keywords: List[str]) -> bool:
        """关键词匹配（标题 + 描述）"""
        text = f"{job['title']} {job['description']}".lower()
        return any(keyword.lower() in text for keyword in keywords)
    
    def _skills_match(self, job: Dict, required_skills: List[str]) -> bool:
        """技能匹配"""
        job_skills = [s.lower() for s in job.get('skills', [])]
        required = [s.lower() for s in required_skills]
        matched = sum(1 for skill in required if skill in job_skills)
        # 至少匹配 50% 的技能
        return matched >= len(required) * 0.5
```

### 5.3 通知服务模块

```python
# notifier.py
from abc import ABC, abstractmethod
from typing import Dict, List
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class BaseNotifier(ABC):
    @abstractmethod
    async def send(self, recipient: str, jobs: List[Dict]) -> bool:
        pass

class EmailNotifier(BaseNotifier):
    def __init__(self, smtp_config: Dict):
        self.smtp_host = smtp_config['host']
        self.smtp_port = smtp_config['port']
        self.username = smtp_config['username']
        self.password = smtp_config['password']
    
    async def send(self, recipient: str, jobs: List[Dict]) -> bool:
        """发送邮件通知"""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'🎯 发现 {len(jobs)} 个匹配职位'
        msg['From'] = self.username
        msg['To'] = recipient
        
        html_content = self._generate_email_html(jobs)
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            return True
        except Exception as e:
            print(f"Email send failed: {e}")
            return False
    
    def _generate_email_html(self, jobs: List[Dict]) -> str:
        """生成邮件HTML模板"""
        job_cards = ""
        for job in jobs:
            job_cards += f"""
            <div style="border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 16px 0;">
                <h3 style="margin: 0 0 8px 0;">{job['title']}</h3>
                <p style="margin: 4px 0;"><strong>公司:</strong> {job['company']}</p>
                <p style="margin: 4px 0;"><strong>地点:</strong> {job['location']}</p>
                <p style="margin: 4px 0;"><strong>薪资:</strong> ${job['salary_min']:,} - ${job['salary_max']:,}</p>
                <p style="margin: 4px 0;"><strong>匹配度:</strong> {job['match_score']:.1f}%</p>
                <a href="{job['source_url']}" style="display: inline-block; margin-top: 8px; 
                   padding: 8px 16px; background: #0066cc; color: white; text-decoration: none; 
                   border-radius: 4px;">查看详情</a>
            </div>
            """
        
        return f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>💼 JobDetector 职位推荐</h2>
                {job_cards}
            </body>
        </html>
        """

class SlackNotifier(BaseNotifier):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send(self, recipient: str, jobs: List[Dict]) -> bool:
        """发送 Slack 通知"""
        import aiohttp
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🎯 发现 {len(jobs)} 个匹配职位"
                }
            }
        ]
        
        for job in jobs[:5]:  # 限制最多5个
            blocks.append({
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*职位:*\n{job['title']}"},
                    {"type": "mrkdwn", "text": f"*公司:*\n{job['company']}"},
                    {"type": "mrkdwn", "text": f"*地点:*\n{job['location']}"},
                    {"type": "mrkdwn", "text": f"*匹配度:*\n{job['match_score']:.1f}%"}
                ]
            })
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "查看详情"},
                        "url": job['source_url']
                    }
                ]
            })
            blocks.append({"type": "divider"})
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json={"blocks": blocks}) as resp:
                return resp.status == 200
```

### 5.4 调度器模块

```python
# scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from typing import List
import asyncio

class JobScraperScheduler:
    def __init__(self, scrapers: List, db_manager, matcher, notifier):
        self.scheduler = AsyncIOScheduler()
        self.scrapers = scrapers
        self.db_manager = db_manager
        self.matcher = matcher
        self.notifier = notifier
    
    def start(self):
        """启动调度器"""
        # 每小时抓取一次 LinkedIn
        self.scheduler.add_job(
            self.run_scraper,
            CronTrigger(minute=0),
            args=['linkedin'],
            id='linkedin_hourly'
        )
        
        # 每2小时抓取一次 Indeed
        self.scheduler.add_job(
            self.run_scraper,
            CronTrigger(minute=0, hour='*/2'),
            args=['indeed'],
            id='indeed_bi_hourly'
        )
        
        # 每天早上8点发送汇总报告
        self.scheduler.add_job(
            self.send_daily_digest,
            CronTrigger(hour=8, minute=0),
            id='daily_digest'
        )
        
        self.scheduler.start()
    
    async def run_scraper(self, source_name: str):
        """运行指定爬虫"""
        scraper = next((s for s in self.scrapers if s.name == source_name), None)
        if not scraper:
            return
        
        # 从配置获取搜索参数
        search_configs = await self.db_manager.get_search_configs()
        
        for config in search_configs:
            jobs = await scraper.scrape(
                keywords=config['keywords'],
                location=config['location']
            )
            
            # 保存到数据库
            new_jobs = await self.db_manager.save_jobs(jobs)
            
            # 运行匹配
            if new_jobs:
                await self.run_matching(new_jobs)
    
    async def run_matching(self, jobs: List[Dict]):
        """运行匹配和通知"""
        users = await self.db_manager.get_active_users()
        
        for user in users:
            preferences = await self.db_manager.get_user_preferences(user['id'])
            
            for job in jobs:
                score = self.matcher.calculate_match_score(job, preferences['criteria'])
                
                if score >= preferences['min_score']:  # 默认 70 分以上
                    # 保存匹配结果
                    await self.db_manager.save_match(user['id'], job['id'], score)
                    
                    # 发送通知
                    await self.notifier.send(user['email'], [job])
```

---

## 6. 部署方案

### 6.1 Docker 容器化

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  # PostgreSQL 数据库
  postgres:
    image: postgres:15-alpine
    container_name: jobdetector_db
    environment:
      POSTGRES_DB: jobdetector
      POSTGRES_USER: jobuser
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    restart: unless-stopped
  
  # Redis 缓存
  redis:
    image: redis:7-alpine
    container_name: jobdetector_redis
    ports:
      - "6379:6379"
    restart: unless-stopped
  
  # 后端 API 服务
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    container_name: jobdetector_api
    environment:
      DATABASE_URL: postgresql://jobuser:${DB_PASSWORD}@postgres:5432/jobdetector
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: ${SECRET_KEY}
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
  
  # 爬虫调度服务
  scraper:
    build:
      context: .
      dockerfile: Dockerfile.scraper
    container_name: jobdetector_scraper
    environment:
      DATABASE_URL: postgresql://jobuser:${DB_PASSWORD}@postgres:5432/jobdetector
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
  
  # 前端服务
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: jobdetector_frontend
    ports:
      - "3000:80"
    depends_on:
      - api
    restart: unless-stopped

volumes:
  postgres_data:
```

**Dockerfile.scraper:**
```dockerfile
FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 设置 Playwright
RUN playwright install chromium

CMD ["python", "scheduler_main.py"]
```

### 6.2 环境配置

**.env 示例:**
```bash
# Database
DB_PASSWORD=your_secure_password
DATABASE_URL=postgresql://jobuser:password@localhost:5432/jobdetector

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your_secret_key_here

# Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password

# Slack (Optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Scraper Configuration
SCRAPER_USER_AGENT=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)
SCRAPER_HEADLESS=true
SCRAPER_PROXY_ENABLED=false

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_PERIOD=3600  # seconds
```

---

## 7. 开发提示词模板

### 7.1 初始化项目提示词

```
你是一个经验丰富的 Python 全栈工程师，擅长构建数据抓取和自动化系统。

项目需求：
构建一个 JobDetector 系统，具有以下功能：
1. 从多个招聘网站（LinkedIn, Indeed, Glassdoor）自动抓取职位信息
2. 使用 PostgreSQL 存储职位数据和用户偏好
3. 基于用户自定义条件匹配职位
4. 通过邮件和 Slack 发送通知

技术栈：
- 后端：Python 3.11 + FastAPI
- 爬虫：Scrapy + Playwright
- 数据库：PostgreSQL + SQLAlchemy
- 缓存：Redis
- 调度：APScheduler
- 前端：React + TypeScript + Ant Design
- 部署：Docker + Docker Compose

任务：
创建项目基础结构，包括：
1. 项目目录结构
2. requirements.txt 依赖文件
3. Docker 配置文件
4. 数据库初始化 SQL
5. 基础配置文件

请遵循最佳实践，使用清晰的代码注释和文档字符串。
```

### 7.2 实现爬虫模块提示词

```
基于 JobDetector 项目，实现 LinkedIn 职位爬虫模块。

需求：
1. 使用 Playwright 处理 JavaScript 渲染
2. 实现用户代理轮换和请求限流
3. 支持搜索参数：关键词、地点、职位类型
4. 解析职位详情：标题、公司、地点、薪资、描述、技能要求
5. 实现去重逻辑（基于职位URL）
6. 错误处理和重试机制
7. 日志记录

技术要求：
- 继承 BaseScraper 抽象类
- 使用异步编程（async/await）
- 遵守 robots.txt 和请求频率限制
- 使用 XPath 或 CSS 选择器精确定位元素

请提供完整的实现代码和使用示例。
```

### 7.3 实现匹配引擎提示词

```
为 JobDetector 实现智能职位匹配引擎。

核心功能：
1. 多维度匹配算法
   - 关键词匹配（标题 + 描述）
   - 技能匹配（支持同义词，如 "React" = "React.js"）
   - 地点匹配（支持远程、混合、现场）
   - 薪资范围匹配
   - 经验年限匹配

2. 评分系统
   - 必须条件：不满足直接淘汰
   - 优先级加权：1-5 级，影响总分
   - 输出 0-100 分的匹配度

3. 性能优化
   - 批量处理
   - 使用缓存避免重复计算
   - 数据库查询优化

技术实现：
- 使用 dataclass 定义数据模型
- 支持自然语言处理（可选：使用 spaCy）
- 单元测试覆盖率 > 80%

请提供完整实现和测试用例。
```

### 7.4 实现 API 服务提示词

```
使用 FastAPI 为 JobDetector 创建 RESTful API 服务。

API 端点需求：

1. 用户管理
   - POST /api/auth/register - 用户注册
   - POST /api/auth/login - 用户登录
   - GET /api/users/me - 获取当前用户信息

2. 偏好设置
   - GET /api/preferences - 获取用户偏好列表
   - POST /api/preferences - 创建新偏好
   - PUT /api/preferences/{id} - 更新偏好
   - DELETE /api/preferences/{id} - 删除偏好

3. 职位管理
   - GET /api/jobs - 获取职位列表（分页、筛选）
   - GET /api/jobs/{id} - 获取职位详情
   - GET /api/jobs/matches - 获取匹配的职位

4. 统计分析
   - GET /api/analytics/trends - 职位趋势
   - GET /api/analytics/salary - 薪资分析

技术要求：
- JWT 认证
- 请求验证（Pydantic models）
- 异常处理中间件
- CORS 配置
- API 文档（自动生成 OpenAPI）
- 日志和监控

请提供完整的 API 实现和数据模型。
```

### 7.5 实现前端界面提示词

```
使用 React + TypeScript + Ant Design 为 JobDetector 创建用户界面。

页面需求：

1. Dashboard（仪表盘）
   - 今日匹配职位数量
   - 本周趋势图表
   - 快速操作按钮

2. 偏好设置页面
   - 创建/编辑匹配条件
   - 多条件组合（AND/OR 逻辑）
   - 优先级设置
   - 通知方式配置

3. 职位列表页面
   - 职位卡片展示
   - 筛选和排序
   - 无限滚动或分页
   - 收藏和标记功能

4. 职位详情页面
   - 完整职位信息
   - 技能匹配高亮
   - 应用记录
   - 相似职位推荐

5. 分析页面
   - 职位趋势图
   - 薪资分布图
   - 技能需求排行

技术要求：
- 响应式设计（移动端适配）
- 状态管理（Redux Toolkit）
- API 集成（axios + React Query）
- 暗色模式支持
- 国际化（中英文）

请提供完整的组件实现和路由配置。
```

### 7.6 测试和优化提示词

```
为 JobDetector 项目编写全面的测试和性能优化方案。

测试需求：

1. 单元测试
   - 爬虫解析函数
   - 匹配算法
   - 数据验证
   - 工具函数

2. 集成测试
   - API 端点测试
   - 数据库操作
   - 外部服务集成

3. 端到端测试
   - 完整爬取流程
   - 匹配和通知流程
   - 用户交互流程

性能优化：

1. 数据库优化
   - 查询优化（explain analyze）
   - 索引优化
   - 连接池配置

2. 缓存策略
   - Redis 缓存热点数据
   - 查询结果缓存
   - 页面缓存

3. 爬虫优化
   - 并发控制
   - 代理池管理
   - 增量抓取

工具和框架：
- pytest + pytest-asyncio
- coverage.py
- locust（负载测试）
- pytest-mock

请提供测试代码和优化建议。
```

---

## 8. 实施路线图

### Phase 1: MVP (2-3 周)
- [x] 项目初始化和环境配置
- [ ] 数据库设计和实现
- [ ] 单一数据源爬虫（LinkedIn 或 Indeed）
- [ ] 基础匹配引擎
- [ ] 邮件通知功能
- [ ] 命令行界面

### Phase 2: 核心功能 (3-4 周)
- [ ] 多数据源支持（3+ 网站）
- [ ] 高级匹配算法
- [ ] FastAPI 后端服务
- [ ] 基础 Web 界面
- [ ] 用户认证系统
- [ ] 调度器集成

### Phase 3: 增强功能 (2-3 周)
- [ ] Slack/Telegram 通知
- [ ] 数据分析和可视化
- [ ] 职位推荐算法优化
- [ ] 移动端适配
- [ ] 性能优化

### Phase 4: 生产部署 (1-2 周)
- [ ] Docker 容器化
- [ ] CI/CD 流水线
- [ ] 监控和告警
- [ ] 文档完善
- [ ] 安全加固

---

## 9. 潜在风险和应对策略

| 风险 | 影响 | 应对策略 |
|-----|------|---------|
| **反爬虫机制** | 高 | 使用代理IP、降低请求频率、模拟真实浏览器行为 |
| **网站结构变化** | 中 | 抽象解析逻辑、快速适配机制、监控告警 |
| **API 限流** | 中 | 缓存结果、批量请求、付费API |
| **数据质量问题** | 中 | 数据验证、异常检测、人工审核 |
| **隐私和合规** | 高 | 遵守 robots.txt、用户数据加密、GDPR 合规 |
| **性能瓶颈** | 低 | 数据库优化、缓存、异步处理 |

---

## 10. 扩展方向

1. **AI 增强**
   - 使用 LLM 分析职位描述质量
   - 生成个性化求职信
   - 智能简历匹配

2. **社区功能**
   - 用户分享成功案例
   - 公司评价系统
   - 面试经验交流

3. **求职辅助**
   - 自动填写申请表单
   - 面试日程管理
   - Offer 比较工具

4. **数据产品**
   - 行业薪资报告
   - 技能趋势分析
   - 公司招聘动态监控

---

## 11. 参考资源

### 文档和教程
- [Scrapy 官方文档](https://docs.scrapy.org/)
- [Playwright Python 文档](https://playwright.dev/python/)
- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [PostgreSQL 性能优化](https://www.postgresql.org/docs/current/performance-tips.html)

### 开源项目参考
- [JobSpy](https://github.com/cullenwatson/JobSpy) - Python 职位搜索库
- [LinkedIn API](https://github.com/tomquirk/linkedin-api) - 非官方 LinkedIn API
- [Indeed Scraper](https://github.com/IndeedScraper/IndeedScraper)

### 工具和服务
- **代理服务**: ScraperAPI, Bright Data, Oxylabs
- **验证码服务**: 2Captcha, Anti-Captcha
- **邮件服务**: SendGrid, AWS SES, Mailgun
- **监控**: Sentry, DataDog, Prometheus

---

## 12. 总结

JobDetector 是一个综合性的职位监控和推荐系统，核心优势在于：

✅ **自动化**: 7x24 小时自动抓取和监控  
✅ **个性化**: 多维度自定义匹配条件  
✅ **实时性**: 第一时间发现新职位  
✅ **可扩展**: 模块化设计，易于添加新数据源  
✅ **开源**: 完全可控，数据隐私保护  

通过合理的架构设计和技术选型，本项目可以在 2-3 个月内完成 MVP 到生产部署的全流程开发。

**下一步行动**:
1. Review 并确认系统设计
2. 初始化项目代码仓库
3. 配置开发环境
4. 开始 Phase 1 开发

---

*文档版本: v1.0*  
*创建日期: 2026-02-04*  
*作者: Antigravity AI*
