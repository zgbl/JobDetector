import requests
import json

def test_google_api():
    url = "https://careers.google.com/api/v1/jobs/search/?q=Software%20Engineer&page=1"
    # Try different version if v1 fails
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Found {len(data.get('jobs', []))} jobs")
            if data.get('jobs'):
                print(f"First job: {data['jobs'][0]['title']}")
        else:
            print(f"Response: {response.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_google_api()
