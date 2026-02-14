import requests
import json
import sys

BASE_URL = "http://localhost:8123"

def test_filter(location=None, category=None):
    params = {}
    if location:
        params['location'] = location
    if category:
        params['category'] = category
        
    print(f"Testing filter with params: {params}")
    try:
        response = requests.get(f"{BASE_URL}/api/jobs", params=params)
        if response.status_code != 200:
            print(f"Error: Status code {response.status_code}")
            print(response.text)
            return

        jobs = response.json()
        print(f"Returned {len(jobs)} jobs")
        
        for job in jobs[:5]:
            print(f"- {job['title']} | {job['company']} | Location: {job.get('location')} | Categories: {job.get('skills', [])[:3]}")
            
        # verification
        if location:
            mismatches = [j for j in jobs if location.lower() not in (j.get('location') or '').lower()]
            if mismatches:
                 print(f"FAIL: Found {len(mismatches)} jobs that do not match location '{location}'")
                 print(f"Example mismatch: {mismatches[0].get('location')}")
            else:
                 print("SUCCESS: All jobs match location.")

    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    print("--- Testing Location: London ---")
    test_filter(location="London")
    print("\n--- Testing Location: Reykjavik ---")
    test_filter(location="Reykjavik")
