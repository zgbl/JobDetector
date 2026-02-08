"""
Language Filter Service
Detects if a job role requires Japanese proficiency and categorizes IT roles.
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
    # Broaden these significantly and use word boundaries
    IT_ROLE_KEYWORDS = [
        r'\bsoftware\b', r'\bengineer\b', r'\bdeveloper\b', r'\bdev\b', r'\bfrontend\b', r'\bbackend\b', r'\bfullstack\b',
        r'\bdata\b', r'\bscientist\b', r'\banalyst\b', r'\bmachine\s+learning\b', r'\bml\b', r'\bai\b', r'\bartificial\b',
        r'\bnlp\b', r'\bdevops\b', r'\bsre\b', r'\bsite\s+reliability\b', r'\binfrastructure\b', r'\bcloud\b', 
        r'\bsecurity\b', r'\bcyber\b', r'\barchitect\b', r'\bproduct\b', r'\bpm\b', r'\bdesigner\b', r'\bux\b', r'\bui\b', 
        r'\bqa\b', r'\bquality\b', r'\btesting\b', r'\bautomation\b', r'\bmobile\b', r'\bandroid\b', r'\bios\b', 
        r'\bswift\b', r'\bkotlin\b', r'\bembedded\b', r'\bfirmware\b', r'\bhardware\b', r'\bsystem\b', r'\badmin\b', 
        r'\btech\b', r'\btechnical\b', r'\bresearcher\b', r'\bspecialist\b', r'\bplatform\b', r'\breliability\b', 
        r'\bobservability\b', r'\bcryptography\b', r'\bblockchain\b', r'\bweb3\b', r'\bdatabase\b', r'\bsql\b', 
        r'\big\s+data\b', r'\bdistributed\b', r'\bperformance\b', r'\btools\b', r'\bintern\b', r'\bstaff\b', 
        r'\bprincipal\b', r'\blead\b', r'\bhead\b', r'\bvp\b', r'\bcto\b'
    ]
    
    # These should only be used as deal-breakers if found in the TITLE
    NON_IT_ROLE_TITLES = [
        r'\bsales\b', r'\bmarketing\b', r'\bcustomer\s+success\b', r'\baccount\s+manager\b',
        r'\bhuman\s+resources\b', r'\bhr\b', r'\brecruiting\b', r'\brecruiter\b', r'\bfinance\b', 
        r'\blegal\b', r'\baccountant\b', r'\bauditor\b', r'\bpayroll\b', r'\bworkplace\b', 
        r'\bfacilities\b', r'\boffice\s+manager\b', r'\badministrator\b', r'\breceptionist\b', 
        r'\bclerk\b', r'\boperator\b', r'\blogistics\b', r'\bwarehouse\b', r'\bsupply\s+chain\b',
        r'\btreasury\b', r'\btax\b', r'\bpublic\s+relations\b', r'\bcomms\b', r'\bcommunications\b'
    ]

    @classmethod
    def is_it_role(cls, text: str, is_title: bool = True) -> Tuple[bool, str]:
        """
        Check if the text indicates an IT/Tech role.
        """
        if not text:
            return False, "No text provided"
        
        text_lower = text.lower()
        
        # 1. If it's the title, check for explicit non-IT deal breakers
        if is_title:
            for pattern in cls.NON_IT_ROLE_TITLES:
                if re.search(pattern, text_lower):
                    # But wait, "Sales Engineer" is tech! "Marketing Technology" is tech!
                    # "Recruiting System Admin" is tech!
                    # Let's check if it ALSO has tech keywords.
                    has_tech = False
                    for tech_pattern in cls.IT_ROLE_KEYWORDS:
                        if re.search(tech_pattern, text_lower):
                            has_tech = True
                            break
                    
                    if not has_tech:
                        return False, f"Detected non-IT role keyword in title: {pattern}"
        
        # 2. Check for IT keywords
        for pattern in cls.IT_ROLE_KEYWORDS:
            if re.search(pattern, text_lower):
                return True, f"Detected IT role keyword: {pattern}"
                
        return False, "No IT keywords found"

    @classmethod
    def is_english_only(cls, text: str) -> Tuple[bool, str]:
        """
        Check if the text indicates an English-only role.
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
                
        # 3. Default to True
        return True, "No specific Japanese requirements detected"

if __name__ == "__main__":
    # Tests
    test_cases = [
        ("Software Engineer", True),
        ("Staff Technical Program Manager", True),
        ("Data Scientist", True),
        ("Manager, Sales", False),
        ("Technical Accounting Manager", True), # Should be true now
        ("Recruiting Coordinator", False),
        ("Sales Engineer", True),
        ("UX Designer", True)
    ]
    
    for title, expected in test_cases:
        res, reason = LanguageFilterService.is_it_role(title)
        print(f"Title: {title:30} -> Result: {res} (Reason: {reason})")
