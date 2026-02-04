"""
Data models for JobDetector
"""
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class ATSSystem:
    """ATS系统信息"""
    type: str  # greenhouse, lever, workday, custom
    detected_at: datetime = field(default_factory=datetime.utcnow)
    api_endpoint: Optional[str] = None
    confidence: float = 1.0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScraperConfig:
    """爬虫配置"""
    method: str = "api"  # api, rss, html, structured_data
    selectors: Dict[str, str] = field(default_factory=dict)
    pagination: Dict[str, any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Schedule:
    """调度配置"""
    frequency_hours: int = 12
    last_scraped_at: Optional[datetime] = None
    next_scrape_at: Optional[datetime] = None
    priority: int = 1  # 1-5
    
    def to_dict(self) -> dict:
        data = asdict(self)
        return data


@dataclass
class CompanyStats:
    """公司统计信息"""
    total_jobs_found: int = 0
    active_jobs: int = 0
    avg_new_jobs_per_week: float = 0.0
    scrape_success_rate: float = 1.0
    last_error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompanyMetadata:
    """公司元数据"""
    industry: Optional[str] = None
    size: Optional[str] = None
    headquarters: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    added_by: str = "system"
    added_at: datetime = field(default_factory=datetime.utcnow)
    verified: bool = False
    
    def to_dict(self) -> dict:
        data = asdict(self)
        return data


@dataclass
class Company:
    """公司信息"""
    name: str
    domain: str
    careers_url: Optional[str] = None
    ats_system: Optional[ATSSystem] = None
    scraper_config: Optional[ScraperConfig] = None
    schedule: Schedule = field(default_factory=Schedule)
    stats: CompanyStats = field(default_factory=CompanyStats)
    metadata: Optional[CompanyMetadata] = None
    is_active: bool = True
    
    def to_dict(self) -> dict:
        """转换为字典格式（用于MongoDB存储）"""
        data = {
            'name': self.name,
            'domain': self.domain,
            'careers_url': self.careers_url,
            'is_active': self.is_active,
        }
        
        if self.ats_system:
            data['ats_system'] = self.ats_system.to_dict()
        
        if self.scraper_config:
            data['scraper_config'] = self.scraper_config.to_dict()
        
        data['schedule'] = self.schedule.to_dict()
        data['stats'] = self.stats.to_dict()
        
        if self.metadata:
            data['metadata'] = self.metadata.to_dict()
        
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Company':
        """从字典创建Company对象"""
        ats_data = data.get('ats_system')
        ats_system = ATSSystem(**ats_data) if ats_data else None
        
        scraper_data = data.get('scraper_config')
        scraper_config = ScraperConfig(**scraper_data) if scraper_data else None
        
        schedule_data = data.get('schedule', {})
        schedule = Schedule(**schedule_data) if schedule_data else Schedule()
        
        stats_data = data.get('stats', {})
        stats = CompanyStats(**stats_data) if stats_data else CompanyStats()
        
        metadata_data = data.get('metadata')
        metadata = CompanyMetadata(**metadata_data) if metadata_data else None
        
        return cls(
            name=data['name'],
            domain=data['domain'],
            careers_url=data.get('careers_url'),
            ats_system=ats_system,
            scraper_config=scraper_config,
            schedule=schedule,
            stats=stats,
            metadata=metadata,
            is_active=data.get('is_active', True)
        )


@dataclass
class Salary:
    """薪资信息"""
    min: Optional[int] = None
    max: Optional[int] = None
    currency: str = "USD"
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Job:
    """职位信息"""
    job_id: str
    title: str
    company: str
    source: str
    source_url: str
    location: Optional[str] = None
    salary: Optional[Salary] = None
    job_type: Optional[str] = None
    remote_type: Optional[str] = None
    description: Optional[str] = None
    requirements: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    benefits: Optional[str] = None
    posted_date: Optional[datetime] = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    raw_data: Dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        data = asdict(self)
        if self.salary:
            data['salary'] = self.salary.to_dict()
        return data
