# 数据库初始化步骤说明

## 已配置的数据库信息

- **数据库名称**: JobDetector
- **MongoDB集群**: blackricemongo.t7k7zg3.mongodb.net
- **连接方式**: 通过环境变量（.env文件），不硬编码

## 将要创建的Collections

系统会自动创建以下5个collections：

### 1. companies（公司信息）
**用途**: 存储监控的公司列表和配置
**字段**:
- name: 公司名称
- domain: 公司域名（唯一）
- careers_url: Career页面URL
- ats_system: ATS系统信息（type, api_endpoint等）
- schedule: 抓取调度配置
- stats: 统计信息
- metadata: 元数据（行业、标签等）

**索引**:
- domain (unique) - 确保公司不重复
- name
- is_active
- metadata.tags

---

### 2. jobs（职位信息）
**用途**: 存储抓取的职位数据
**字段**:
- job_id: 职位唯一ID（唯一）
- title: 职位标题
- company: 公司名称
- location: 地点
- salary: 薪资范围
- description: 职位描述
- skills: 技能要求（数组）
- source: 来源（greenhouse, lever等）
- source_url: 原始链接（唯一）
- posted_date: 发布日期
- scraped_at: 抓取时间

**索引**:
- job_id (unique)
- source_url (unique)
- scraped_at (降序)
- company
- location
- skills
- posted_date (降序)
- (is_active, scraped_at) 复合索引

---

### 3. user_preferences（用户偏好）
**用途**: 存储用户的职位匹配偏好（MVP单用户模式）
**字段**:
- user_email: 用户邮箱
- keywords: 关键词列表
- exclude_keywords: 排除关键词
- locations: 地点偏好
- min_salary: 最低薪资要求
- required_skills: 必须技能
- preferred_skills: 加分技能
- min_match_score: 最低匹配分数

**默认值**: 系统会自动创建一个默认配置

---

### 4. job_matches（匹配结果）
**用途**: 存储职位匹配记录
**字段**:
- job_id: 关联的职位ID
- matched_at: 匹配时间
- match_score: 匹配分数（0-100）
- matched_criteria: 匹配的具体条件
- is_notified: 是否已发送通知
- notified_at: 通知时间

**索引**:
- job_id
- matched_at (降序)
- is_notified

---

### 5. scraper_logs（抓取日志）
**用途**: 记录每次抓取任务的执行情况
**字段**:
- source: 数据源（公司名）
- status: 状态（success/failed）
- jobs_found: 发现的职位数
- jobs_new: 新增职位数
- error_message: 错误信息
- started_at: 开始时间
- completed_at: 完成时间

**索引**:
- started_at (降序)
- source
- status

---

## 执行步骤

### 准备工作
请确保您已经：
1. ✅ 在MongoDB Atlas创建了JobDetector数据库
2. ✅ .env文件已配置好连接信息

### 步骤1: 激活虚拟环境

```bash
cd /Users/tuxy/Codes/Github2/JobDetector
source venv/bin/activate
```

### 步骤2: 运行数据库初始化脚本

```bash
python scripts/init_database.py
```

**脚本会自动执行以下操作**:
1. 连接到MongoDB Atlas的JobDetector数据库
2. 创建5个collections（如果不存在）
3. 为每个collection创建优化索引（共15+个索引）
4. 初始化默认用户偏好配置
5. 验证并显示统计信息

**预期输出**:
```
🚀 Starting database initialization...

📦 Step 1: Creating collections...
✅ Created collection: companies
✅ Created collection: jobs
✅ Created collection: user_preferences
✅ Created collection: job_matches
✅ Created collection: scraper_logs

📊 Step 2: Creating indexes...
✅ Created indexes for 'companies' collection
✅ Created indexes for 'jobs' collection
✅ Created indexes for 'job_matches' collection
✅ Created indexes for 'scraper_logs' collection

⚙️  Step 3: Initializing default data...
✅ Created default user preferences

==================================================
Database Verification
==================================================
Collections (5): companies, jobs, user_preferences, job_matches, scraper_logs
  - companies: 0 documents
  - jobs: 0 documents
  - user_preferences: 1 documents
  - job_matches: 0 documents
  - scraper_logs: 0 documents

Indexes:
  - companies: _id_, domain_1, name_1, is_active_1, metadata.tags_1
  - jobs: _id_, job_id_1, source_url_1, scraped_at_-1, company_1, location_1, skills_1, posted_date_-1, is_active_1_scraped_at_-1
  - job_matches: _id_, job_id_1, matched_at_-1, is_notified_1
  - scraper_logs: _id_, started_at_-1, source_1, status_1
==================================================
✅ Database initialization completed successfully!

🎉 Database is ready to use!
```

### 步骤3: 验证连接

```bash
python scripts/test_connection.py
```

**预期输出**:
```
✅ Database connection successful
📋 Collections: ['companies', 'jobs', 'user_preferences', 'job_matches', 'scraper_logs']
📊 Companies in database: 0
```

---

## 连接安全说明

✅ **安全措施已到位**:
1. **不硬编码**: 数据库连接字符串存储在`.env`文件中
2. **Git忽略**: `.env`文件已添加到`.gitignore`，不会被提交到Git
3. **环境变量**: 代码通过`os.getenv()`读取，支持生产环境配置
4. **模板文件**: `.env.example`提供配置模板，不包含真实密码

## 代码工作原理

`connection.py`中的连接管理器：
```python
# 从环境变量读取（不硬编码）
mongo_uri = os.getenv('MONGODB_URI')
db_name = os.getenv('MONGODB_DATABASE', 'jobdetector')

# 连接数据库
self._client = MongoClient(mongo_uri)
self._db = self._client[db_name]
```

## 下一步

初始化完成后，您可以：
1. 导入50家公司数据：`python scripts/import_companies.py`
2. 查看统计信息：`python scripts/import_companies.py --stats`

---

**注意**: 如果遇到错误，请检查：
- MongoDB Atlas中IP白名单设置（添加0.0.0.0/0允许所有IP访问，仅测试用）
- 数据库用户权限（确保用户有读写权限）
- 连接字符串格式正确
