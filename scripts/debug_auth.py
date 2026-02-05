import requests
import sys

BASE_URL = "http://localhost:8123"

def test_register(email, password, name):
    print(f"--- Attempting Register: {email} ---")
    payload = {
        "email": email,
        "password": password,
        "full_name": name
    }
    try:
        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Request failed: {e}")
        return False

def test_login(email, password):
    print(f"--- Attempting Login: {email} ---")
    payload = {
        "email": email,
        "password": password
    }
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json=payload)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("Login Success")
            print(f"Token: {response.json().get('access_token')[:20]}...")
        else:
            print(f"Login Failed: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    # Test 1: Register a new user
    import time
    ts = int(time.time())
    new_email = f"test_user_{ts}@example.com"
    
    if test_register(new_email, "password123", "Test User"):
        test_login(new_email, "password123")
    else:
        print("Skipping login due to register failure")
