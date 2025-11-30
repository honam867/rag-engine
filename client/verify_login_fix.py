import requests
import jwt
import json

# Configuration
SUPABASE_URL = "https://jxnhebdgmsrsfevkgvpd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp4bmhlYmRnbXNyc2ZldmtndnBkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjQ0ODk4MTAsImV4cCI6MjA4MDA2NTgxMH0.6nxFvgRsAOWdyHg8vUCqNNtmNkCYqPyvT6Cd15iUckE"
JWT_SECRET = "kmJqOGDojK0gF3qQKUKl1S7cpNQJqrARhQ5GiCyHKVBp+9irhMOwPdblRaT6yIGoJ1jU/YISCVJfH7eRvmA7iw=="

EMAIL = "honam867@gmail.com"
PASSWORD = "Nam_heo1509"

def test_full_flow():
    print("1. Attempting Login to Supabase...")
    auth_url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "email": EMAIL,
        "password": PASSWORD
    }
    
    try:
        response = requests.post(auth_url, headers=headers, json=data)
        response.raise_for_status()
        tokens = response.json()
        access_token = tokens.get("access_token")
        print("   ✅ Login Successful! Got Access Token.")
    except Exception as e:
        print(f"   ❌ Login Failed: {e}")
        try:
            print(f"   Response: {response.text}")
        except:
            pass
        return

    print("\n2. Simulating Backend Validation (with 'aud' check DISABLED)...")
    try:
        # This matches the code currently in server/app/core/security.py
        payload = jwt.decode(
            access_token, 
            JWT_SECRET, 
            algorithms=["HS256"], 
            options={"verify_aud": False, "leeway": 60}
        )
        print("   ✅ Backend Validation PASSED!")
        print(f"   User ID: {payload.get('sub')}")
        print(f"   Email: {payload.get('email')}")
        print("   Audience (aud):", payload.get('aud'))
        print("\n   CONCLUSION: The fix works. The token is valid and the backend logic accepts it.")
    except jwt.ExpiredSignatureError:
        print("   ❌ Validation Failed: Token Expired")
    except jwt.InvalidSignatureError:
        print("   ❌ Validation Failed: Invalid Signature (Check JWT_SECRET)")
    except Exception as e:
        print(f"   ❌ Validation Failed: {e}")

if __name__ == "__main__":
    test_full_flow()
