import requests
import time

start = time.time()
try:
    response = requests.get('http://localhost:8000/api/dashboard/overview', timeout=30)
    elapsed = time.time() - start
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Time: {elapsed:.2f}s")
    
    data = response.json()
    print(f"\nStats: {data['stats']}")
    print(f"Missions Count: {len(data['missions'])}")
    print(f"Alerts Count: {len(data['alerts'])}")
    
    if data['missions']:
        print(f"\nFirst Mission: {data['missions'][0]}")
        
except requests.Timeout:
    print("Request timed out after 30 seconds!")
except Exception as e:
    print(f"Error: {e}")
