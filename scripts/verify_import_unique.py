import yaml
import sys
from pathlib import Path

def verify_unique():
    base_path = Path('data/companies_startups.yaml')
    expansion_path = Path('data/companies_expansion_us_it.yaml')

    if not base_path.exists():
        print(f"Base file not found: {base_path}")
        return

    if not expansion_path.exists():
        print(f"Expansion file not found: {expansion_path}")
        return

    with open(base_path, 'r') as f:
        base_data = yaml.safe_load(f)
        base_domains = {c['domain'] for c in base_data.get('companies', [])}
        base_names = {c['name'].lower() for c in base_data.get('companies', [])}

    with open(expansion_path, 'r') as f:
        exp_data = yaml.safe_load(f)
        exp_companies = exp_data.get('companies', [])

    print(f"Base companies: {len(base_domains)}")
    print(f"Expansion companies: {len(exp_companies)}")

    duplicates = []
    for c in exp_companies:
        if c['domain'] in base_domains:
            duplicates.append(f"{c['name']} ({c['domain']}) - Domain match")
        elif c['name'].lower() in base_names:
            duplicates.append(f"{c['name']} ({c['domain']}) - Name match")

    if duplicates:
        print("\n❌ Found duplicates:")
        for d in duplicates:
            print(f"  - {d}")
        sys.exit(1)
    else:
        print("\n✅ No duplicates found! The lists are unique.")
        # Validate syntax
        print("✅ Syntax check passed.")

if __name__ == "__main__":
    verify_unique()
