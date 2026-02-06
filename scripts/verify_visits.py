import requests
import sys

base_url = "http://0.0.0.0:8123/api"

print("--- Testing Visit Counter ---")
try:
    # 1st Hit
    resp = requests.post(f"{base_url}/stats/visit")
    print(f"Request 1: {resp.status_code} - {resp.json()}")
    val1 = resp.json().get("visits")

    # 2nd Hit
    resp = requests.post(f"{base_url}/stats/visit")
    print(f"Request 2: {resp.status_code} - {resp.json()}")
    val2 = resp.json().get("visits")

    if val2 == val1 + 1:
        print("SUCCESS: Counter incrementing correctly.")
    else:
        print(f"FAILED: Counter mismatch ({val1} -> {val2})")

except Exception as e:
    print(f"Error: {e}")
