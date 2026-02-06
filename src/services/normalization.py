import re

def normalize_company_name(name: str) -> str:
    """
    Normalizes a company name for consistent storage and comparison.
    
    Examples:
    - "  Review  " -> "Review"
    - "Google Inc." -> "Google"
    - "Amazon.com" -> "Amazon"
    
    Args:
        name: Raw company name
        
    Returns:
        Normalized name
    """
    if not name:
        return ""
        
    # 1. Strip whitespace
    normalized = name.strip()
    
    # 2. Remove common legal suffixes (basic list)
    # Note: rigorous entity resolution is complex, this is a starting point
    suffixes = [
        r'\s+Inc\.?$', 
        r'\s+LLC\.?$', 
        r'\s+Ltd\.?$', 
        r'\s+Corp\.?$', 
        r'\s+Corporation$', 
        r'\s+Co\.?$'
    ]
    
    for suffix in suffixes:
        normalized = re.sub(suffix, '', normalized, flags=re.IGNORECASE)
        
    # 3. Remove domain suffixes if present (e.g. Amazon.com -> Amazon)
    if '.' in normalized and ' ' not in normalized:
         # simple heuristic: if it looks like a domain, drop the TLD
         parts = normalized.split('.')
         if len(parts) == 2:
             normalized = parts[0]
    
    return normalized
