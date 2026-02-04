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
    
    def normalize_job_data(self, raw_data: Dict, company_name: str, source: str) -> Dict:
        """
        标准化职位数据
        
        Args:
            raw_data: 原始数据
            company_name: 公司名称
            source: 数据源
            
        Returns:
            标准化的职位数据
        """
        return {
            'job_id': raw_data.get('id', ''),
            'title': raw_data.get('title', '').strip(),
            'company': company_name,
            'location': raw_data.get('location', ''),
            'description': raw_data.get('description', ''),
            'source': source,
            'source_url': raw_data.get('url', ''),
            'posted_date': raw_data.get('posted_date'),
            'scraped_at': datetime.utcnow(),
            'is_active': True,
            'raw_data': raw_data
        }
    
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
