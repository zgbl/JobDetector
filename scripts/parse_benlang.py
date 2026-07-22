#!/usr/bin/env python3
"""
Parse Ben Lang's company lists from LinkedIn posts.
Extracts company names, descriptions, and locations.
"""
import re
import csv
from typing import List, Dict, Optional
from pathlib import Path


class BenLangParser:
    """Parser for Ben Lang's company list format"""
    
    # Regex pattern for: "1) Company Name - description (location)"
    # Adjusted to handle potential variability in spacing or characters
    PATTERN = r'^\d+\)\s+(.+?)\s+[-–—]\s+(.+?)\s+\((.+?)\)\s*$'
    
    # Company suffixes to clean
    SUFFIXES = [
        'Inc.', 'Inc', 'LLC', 'Ltd.', 'Ltd', 'Company', 'Co.', 
        'Corporation', 'Corp.', 'Corp', 'Technologies', 'Tech'
    ]
    
    def parse_file(self, file_path: str) -> List[Dict[str, str]]:
        """
        Parse BenLang.txt format and extract company data.
        
        Args:
            file_path: Path to the text file
            
        Returns:
            List of dicts with keys: name, description, location, raw_name
        """
        if Path(file_path).suffix.lower() == '.csv':
            return self.parse_csv_file(file_path)

        companies = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
                
            match = re.search(self.PATTERN, line)
            if match:
                raw_name = match.group(1).strip()
                description = match.group(2).strip()
                location = match.group(3).strip()
                
                companies.append({
                    'raw_name': raw_name,
                    'name': self.normalize_name(raw_name),
                    'description': description,
                    'location': location
                })
        
        return companies

    def parse_csv_file(self, file_path: str) -> List[Dict[str, str]]:
        """Parse a Google Sheets CSV export."""
        companies = []
        seen = set()
        with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
            rows = list(csv.reader(f))

        # Google Sheets exports may include one or more instruction rows before
        # the actual header row.
        header_index = next(
            (i for i, row in enumerate(rows) if 'Company' in row and 'Career Page' in row),
            None,
        )
        if header_index is None:
            return companies

        headers = rows[header_index]
        for values in rows[header_index + 1:]:
            row = dict(zip(headers, values))
            raw_name = (row.get('Company') or '').strip()
            if not raw_name:
                continue
            name = self.normalize_name(raw_name)
            career_url = (row.get('Career Page') or '').strip()
            key = career_url.casefold().rstrip('/') or name.casefold()
            if key in seen:
                continue
            seen.add(key)
            companies.append({
                'raw_name': raw_name,
                'name': name,
                'description': '',
                'location': (row.get('Location') or '').strip(),
                'career_url': career_url,
                'thread_url': (row.get('Thread Reply Link') or '').strip(),
                'source_file': Path(file_path).name,
            })
        return companies
    
    def normalize_name(self, raw_name: str) -> str:
        """
        Normalize company name by removing common suffixes.
        
        Examples:
            "Oxide Computer Company" -> "Oxide"
            "Noveon Magnetics Inc." -> "Noveon Magnetics"
            "Skild AI" -> "Skild AI"
        """
        name = raw_name.strip()
        
        # Remove suffixes
        for suffix in self.SUFFIXES:
            # Try exact match at end
            if name.endswith(f' {suffix}'):
                name = name[:-len(suffix)-1].strip()
                break
        
        return name
    
    def parse_linkedin_url(self, url: str) -> Optional[Dict]:
        """
        Extract post metadata from LinkedIn URL.
        
        Args:
            url: LinkedIn post URL
            
        Returns:
            Dict with post_id, date if parseable
        """
        # Extract activity ID from URL
        match = re.search(r'activity:(\d+)', url)
        if match:
            return {
                'post_id': match.group(1),
                'url': url
            }
        return None


def main():
    """Test parser on BenLang.txt"""
    parser = BenLangParser()
    
    # Parse the file
    file_path = Path(__file__).parent.parent / 'data' / 'ImportList' / 'BenLang.txt'
    companies = parser.parse_file(str(file_path))
    
    # Print results
    print(f"📋 Parsed {len(companies)} companies from {file_path.name}\n")
    
    for i, company in enumerate(companies, 1):
        print(f"{i}. {company['name']}")
        print(f"   Raw: {company['raw_name']}")
        print(f"   Description: {company['description']}")
        print(f"   Location: {company['location']}")
        print()
    
    # Summary
    print(f"\n✅ Successfully parsed {len(companies)} companies")
    print(f"📍 Locations: {len(set(c['location'] for c in companies))} unique")


if __name__ == '__main__':
    main()
