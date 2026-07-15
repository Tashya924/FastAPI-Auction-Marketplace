import httpx

client = httpx.Client(base_url='http://127.0.0.1:8000')

# create unique user
import time
username = f"user_{int(time.time())}"
print(f"Registering {username}")
resp = client.post("/users", json={"username": username, "email": f"{username}@test.com", "password": "password"})
print("Register:", resp.status_code, resp.text)

print("Logging in with JSON")
resp = client.post("/login", json={"username": username, "password": "password"})
print("Login JSON:", resp.status_code, resp.text)
