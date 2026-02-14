import requests
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

base_url = "http://0.0.0.0:8123/api"
email = "verify_user@example.com"
password = "password123"

def run_test():
    print(f"--- Starting Feature Verification ---")

    # 1. Register/Login
    print(f"\n1. Authenticating as {email}...")
    try:
        resp = requests.post(f"{base_url}/auth/register", json={
            "email": email, "password": password, "full_name": "Verify Bot"
        })
    except Exception:
        pass # Ignore if already exists

    resp = requests.post(f"{base_url}/auth/login", json={
        "email": email, "password": password
    })
    
    if resp.status_code != 200:
        print(f"FAILED: Login error {resp.text}")
        return
    
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("SUCCESS: Logged in.")

    # 2. Create Saved Search
    print("\n2. Creating Saved Search...")
    search_data = {
        "name": "Test Python Alert",
        "criteria": {"q": "Python", "location": "Remote"},
        "email_alert": True
    }
    resp = requests.post(f"{base_url}/user/searches", json=search_data, headers=headers)
    if resp.status_code != 200:
        print(f"FAILED: Create search error {resp.text}")
        return
    
    search_id = resp.json()["id"]
    print(f"SUCCESS: Created search ID {search_id}")

    # 3. List Searches
    print("\n3. Listing Searches...")
    resp = requests.get(f"{base_url}/user/searches", headers=headers)
    searches = resp.json()
    found = False
    for s in searches:
        if s["id"] == search_id and s["name"] == "Test Python Alert":
            found = True
            print(f"  - Found: {s['name']} (Alert: {s['email_alert']})")
    
    if not found:
        print("FAILED: Search not found in list")
        return
    print("SUCCESS: Listed searches.")

    # 4. Run Alert Script (Simulate)
    print("\n4. Triggering Alert Script...")
    import scripts.send_alerts as alert_script
    # We modify the alert script to run just once or call its function
    try:
        # Insert a fake "new" job if needed, or rely on existing data
        # Actually, let's just run it. It might not find new jobs if none scraped recently,
        # but effective execution without error is the goal here.
        alert_script.check_and_send_alerts()
        print("SUCCESS: Alert script ran.")
    except Exception as e:
        print(f"FAILED: Alert script error: {e}")

    # 5. Delete Search
    print("\n5. Deleting Search...")
    resp = requests.delete(f"{base_url}/user/searches/{search_id}", headers=headers)
    if resp.status_code != 200:
        print(f"FAILED: Delete error {resp.text}")
        return
        
    # Verify gone
    resp = requests.get(f"{base_url}/user/searches", headers=headers)
    for s in resp.json():
        if s["id"] == search_id:
            print("FAILED: Search still exists after delete")
            return
            
    print("SUCCESS: Search deleted.")
    print("\n--- Verification COMPLETE ---")

if __name__ == "__main__":
    run_test()
