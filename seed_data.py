import os
import sqlite3
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = "http://127.0.0.1:8000"

def run():
    username = f"testuser_{int(datetime.now().timestamp())}"
    # 1. Create a user
    user_data = {
        "username": username,
        "email": f"test_{int(datetime.now().timestamp())}@example.com",
        "password": "password123"
    }
    r = requests.post(f"{BASE_URL}/users", json=user_data)
    if r.status_code not in (200, 201):
        print(f"Failed to create user: {r.text}")
    
    # get user id from DB
    conn = sqlite3.connect("auction.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user_id = c.fetchone()[0]
    conn.close()

    # 2. Log in to get token
    login_data = {
        "username": user_data["username"],
        "password": user_data["password"]
    }
    r = requests.post(f"{BASE_URL}/login", json=login_data)
    r.raise_for_status()
    token = r.json()["access_token"]
    
    # 3. Create an auction
    headers = {"Authorization": f"Bearer {token}"}
    end_time = datetime.now(timezone.utc) + timedelta(days=1)
    auction_data = {
        "title": "Benchmark Auction",
        "description": "Load testing auction",
        "starting_price": 1.0,
        "owner_id": user_id,
        "end_time": end_time.isoformat()
    }
    
    r = requests.post(f"{BASE_URL}/auctions", json=auction_data, headers=headers)
    r.raise_for_status()
    auction_id = r.json()["id"]
    
    # 4. Save token and auction_id for k6
    with open("benchmark_env.json", "w") as f:
        import json
        json.dump({"token": token, "auction_id": auction_id, "user_id": user_id}, f)
    
    print(f"Setup complete. Auction ID: {auction_id}, User ID: {user_id}")

if __name__ == "__main__":
    run()
