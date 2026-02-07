"""
Language Filter Service
Detects if a job role requires Japanese proficiency.
"""
import re
from typing import Tuple

class LanguageFilterService:
    
    # Keywords that indicate Japanese proficiency is required
    JAPANESE_REQUIRED_KEYWORDS = [
        r'jlpt',
        r'n1',
        r'n2',
        r'n3',
        r'japanese[:\s]+business',
        r'japanese[:\s]+fluent',
        r'native[:\s]+japanese',
        r'fluent[:\s]+japanese',
        r'business[:\s]+level[:\s]+japanese',
        r'日本語',
        r'ビジネスレベル',
        r'ネイティブレベル',
        r'流暢',
        r'japanese\s+proficiency',
        r'must\s+speak\s+japanese',
        r'requirement[:\s]+japanese'
    ]
    
    # Keywords that explicitly state Japanese is NOT required
    ENGLISH_ONLY_KEYWORDS = [
        r'no\s+japanese\s+required',
        r'japanese\s+not\s+required',
        r'english\s+only',
        r'english-only',
        r'working\s+language\s+is\s+english',
        r'primary\s+language\s+is\s+english'
    ]

    # --- IT Role Categorization ---
    IT_ROLE_KEYWORDS = [
        r'software', r'engineer', r'developer', r'frontend', r'backend', r'fullstack',
        r'data\s+scientist', r'data\s+engineer', r'machine\s+learning', r'ai\s+',
        r'devops', r'sre', r'infrastructure', r'cloud', r'security', r'architect',
        r'product\s+manager', r'designer', r'ux\s+', r'ui\s+', r'qa\s+', r'testing',
        r'mobile', r'android', r'ios', r'embedded', r'system\s+admin'
    ]
    
    NON_IT_ROLE_KEYWORDS = [
        r'sales', r'marketing', r'customer\s+support', r'account\s+manager',
        r'human\s+resources', r'recruiter', r'finance', r'legal', r'accountant',
        r'logistics', r'admin', r'clerk', r'operator', r'intern\s+in\s+sales'
    ]

    @classmethod
    def is_it_role(cls, text: str) -> Tuple[bool, str]:
        """Check if the text indicates an IT/Tech role."""
        if not text:
            return False, "No text provided"
        
        text_lower = text.lower()
        
        # 1. Check for explicit non-IT keywords first
        for pattern in cls.NON_IT_ROLE_KEYWORDS:
            if re.search(pattern, text_lower):
                return False, f"Detected non-IT role keyword: {pattern}"
        
        # 2. Check for IT keywords
        for pattern in cls.IT_ROLE_KEYWORDS:
            if re.search(pattern, text_lower):
                return True, f"Detected IT role keyword: {pattern}"
                
        return False, "No IT keywords found in title/description"

    @classmethod
    def is_english_only(cls, text: str) -> Tuple[bool, str]:
        """
        Check if the text indicates an English-only role.
        Returns: (is_english, reason)
        """
        if not text:
            return True, "No text provided"
            
        text_lower = text.lower()
        
        # 1. Check for explicit "No Japanese Required"
        for pattern in cls.ENGLISH_ONLY_KEYWORDS:
            if re.search(pattern, text_lower):
                return True, f"Found explicit English-only keyword: {pattern}"
                
        # 2. Check for Japanese requirements
        for pattern in cls.JAPANESE_REQUIRED_KEYWORDS:
            if re.search(pattern, text_lower):
                return False, f"Detected Japanese requirement keyword: {pattern}"
                
        # 3. Default to True if no Japanese requirements found
        return True, "No specific Japanese requirements detected"

if __name__ == "__main__":
    # Quick test
    test_texts = [
        "Software Engineer. Working language is English. No Japanese required.",
        "Backend Developer. Must have JLPT N1.",
        "Sales Manager. Fluent in English.",
        "Receptionist. No specific language requirement mentioned."
    ]
    
    for t in test_texts:
        is_it, it_reason = LanguageFilterService.is_it_role(t)
        is_eng, eng_reason = LanguageFilterService.is_english_only(t)
        print(f"Text: {t[:30]}... -> IT: {is_it}, English Only: {is_eng}")
