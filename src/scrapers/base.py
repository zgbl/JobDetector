"""
Base Scraper Abstract Class
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """抓取器基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"scraper.{name}")
    
    @abstractmethod
    async def scrape(self, company: Dict) -> List[Dict]:
        """
        抓取职位信息
        
        Args:
            company: 公司信息字典
            
        Returns:
            职位列表
        """
        pass
    
    def normalize_job_data(self, raw_data: Dict, company_name: str, source: str, company_location: Optional[str] = None) -> Dict:
        """
        标准化职位数据
        
        Args:
            raw_data: 原始数据
            company_name: 公司名称
            source: 数据源
            company_location: 公司所在地 (例如 "Japan")
            
        Returns:
            标准化的职位数据
        """
        # Generate content hash
        job_location = raw_data.get('location', '').strip()
        
        # Smart location tagging: if job location is vague, append company location
        if company_location and job_location:
            vague_terms = ['hybrid', 'remote', 'on-site', 'onsite']
            if job_location.lower() in vague_terms:
                job_location = f"{job_location} ({company_location})"
            elif company_location.lower() not in job_location.lower():
                # For startups, the city alone is often given (e.g. "Tokyo")
                # If "Japan" isn't in there, we can append it
                pass 
        elif company_location and not job_location:
            job_location = company_location

        content_hash = self.generate_content_hash(
            raw_data.get('title', ''),
            raw_data.get('description', ''),
            job_location
        )
        
        return {
            'job_id': raw_data.get('id', ''),
            'title': raw_data.get('title', '').strip(),
            'company': company_name,
            'location': job_location,
            'company_location': company_location,
            'description': raw_data.get('description', ''),
            'source': source,
            'source_url': raw_data.get('url', ''),
            'posted_date': raw_data.get('posted_date'),
            'scraped_at': datetime.utcnow(),
            'last_seen_at': datetime.utcnow(),
            'content_hash': content_hash,
            'is_active': True,
            'raw_data': raw_data
        }
    
    def generate_content_hash(self, title: str, description: str, location: str) -> str:
        """
        生成职位内容的唯一哈希值
        """
        import hashlib
        content = f"{title}|{description}|{location}".encode('utf-8')
        return hashlib.md5(content).hexdigest()
    
    def extract_salary(self, text: str) -> Optional[Dict]:
        """
        从文本中提取薪资信息
        
        Args:
            text: 包含薪资信息的文本
            
        Returns:
            薪资字典或None
        """
        # Simple salary extraction logic
        # Can be enhanced with regex patterns
        import re
        
        # Pattern: $100,000 - $150,000 or $100k - $150k
        pattern = r'\$(\d+)(?:,\d{3})*(?:k|K)?\s*-\s*\$(\d+)(?:,\d{3})*(?:k|K)?'
        match = re.search(pattern, text)
        
        if match:
            min_sal = match.group(1).replace(',', '')
            max_sal = match.group(2).replace(',', '')
            
            # Handle 'k' suffix
            if 'k' in match.group(0).lower():
                min_sal = int(min_sal) * 1000
                max_sal = int(max_sal) * 1000
            else:
                min_sal = int(min_sal)
                max_sal = int(max_sal)
            
            return {
                'min': min_sal,
                'max': max_sal,
                'currency': 'USD'
            }
        
        return None
    
    def extract_skills(self, description: str) -> List[str]:
        """
        从职位描述中提取技能关键词
        
        Args:
            description: 职位描述
            
        Returns:
            技能列表
        """
        # Common tech skills
        common_skills = [
            'python', 'java', 'javascript', 'typescript', 'go', 'rust', 'c++',
            'react', 'vue', 'angular', 'node.js', 'django', 'flask', 'fastapi',
            'aws', 'gcp', 'azure', 'docker', 'kubernetes', 'terraform',
            'postgresql', 'mysql', 'mongodb', 'redis',
            'git', 'ci/cd', 'agile', 'scrum',
            'machine learning', 'deep learning', 'nlp', 'computer vision',
            'data science', 'sql', 'nosql'
        ]
        
        description_lower = description.lower()
        found_skills = []
        
        for skill in common_skills:
            if skill in description_lower:
                found_skills.append(skill.title())
        
        return list(set(found_skills))  # Remove duplicates
