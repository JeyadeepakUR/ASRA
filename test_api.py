import time
import httpx

API_URL = "http://localhost:8000"

def test_flow():
    print("1. Submitting Alert...")
    payload = {
        "service": "api-gateway",
        "alert_name": "HighLatency",
        "severity": "critical",
        "metrics": {"latency_ms": 3500.0, "cpu_pct": 98.0}
    }
    r = httpx.post(f"{API_URL}/webhook/alert", json=payload)
    print(r.json())
    
    print("\n2. Waiting for Graph to Process and Pause...")
    time.sleep(3)
    
    print("\n3. Checking Pending Incidents...")
    r = httpx.get(f"{API_URL}/api/incidents/pending")
    data = r.json()
    print(data)
    
    if data.get("pending_count", 0) > 0:
        thread_id = list(data["incidents"].keys())[0]
        print(f"\n4. Approving Incident {thread_id}...")
        r = httpx.post(f"{API_URL}/api/incidents/{thread_id}/approve")
        print(r.json())
        
        print("\n5. Checking Pending Incidents again...")
        time.sleep(2)
        r = httpx.get(f"{API_URL}/api/incidents/pending")
        print(r.json())

if __name__ == "__main__":
    test_flow()
