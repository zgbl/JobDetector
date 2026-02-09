#!/usr/bin/env python3
"""
Clean and deduplicate Ben Lang's company list.
Reads data/ImportList/BenLang.txt, removes duplicates, and rewrites the file.
"""
import re
from pathlib import Path

def clean_benlang_list():
    file_path = Path(__file__).parent.parent / 'data' / 'ImportList' / 'BenLang.txt'
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    cleaned_lines = []
    seen_companies = set()
    
    # Regex to extract company name for deduplication
    # Matches: "1) Company Name - description (Location)"
    pattern = r'^\d+\)\s+(.+?)\s+-'
    
    for line in lines:
        match = re.search(pattern, line)
        if match:
            company_name = match.group(1).strip().lower()
            
            # Special handling for "The General Intelligence Company of New York" vs "General Intelligence Company"
            # Limit to basic cleaning for now
            
            if company_name in seen_companies:
                print(f"Skipping duplicate: {match.group(1)}")
                continue
            
            seen_companies.add(company_name)
            cleaned_lines.append(line)
        else:
            # Keep headers, empty lines, links etc.
            cleaned_lines.append(line)
            
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(cleaned_lines)
        
    print(f"Cleaned file. Total unique companies found: {len(seen_companies)}")

if __name__ == '__main__':
    clean_benlang_list()
