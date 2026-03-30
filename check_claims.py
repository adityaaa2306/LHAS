import httpx
import json

url = 'http://localhost:8000/api/dashboard/missions/2ee30391-f6bf-4b48-be12-f9660c70a897/claims'
response = httpx.get(url)
data = response.json()

print(f"✅ API ENDPOINT ACTIVE")
print(f"Status: {response.status_code}")
print(f"Total claims: {len(data['claims'])}")
print(f"\nClaim Statistics:")
print(f"  Claim types: {sorted(set(c['claim_type'] for c in data['claims']))}")
print(f"  Directions: {sorted(set(c['direction'] for c in data['claims']))}")
print(f"  Avg confidence: {sum(c['confidence_score'] for c in data['claims'])/len(data['claims']):.3f}")

print(f"\nClaims by type:")
for ctype in sorted(set(c['claim_type'] for c in data['claims'])):
    count = len([c for c in data['claims'] if c['claim_type'] == ctype])
    print(f"  {ctype}: {count}")

print(f"\nClaims by direction:")
for direction in sorted(set(c['direction'] for c in data['claims'])):
    count = len([c for c in data['claims'] if c['direction'] == direction])
    print(f"  {direction}: {count}")

print(f"\nSample Claims:")
for i, claim in enumerate(data['claims'][:3], 1):
    print(f"  {i}. {claim['claim_text'][:60]}... [{claim['direction']}, {claim['confidence_score']}]")
