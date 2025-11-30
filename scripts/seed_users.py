import asyncio
import uuid
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()

# Cấu hình kết nối DB từ .env
# Lưu ý: Script này dùng trực tiếp biến môi trường để tạo engine
DB_URL = os.getenv("SUPABASE_DB_URL")
if not DB_URL:
    raise ValueError("Missing SUPABASE_DB_URL in .env")

# Chuẩn hóa URL cho asyncpg
if DB_URL.startswith("postgresql://"):
    DB_URL = DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Áp dụng cấu hình tắt prepared statements trực tiếp vào engine của script này
engine = create_async_engine(
    DB_URL,
    echo=True,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda *args: "",
    },
)

async def seed_user():
    # Tạo một UUID ngẫu nhiên cho user mới
    new_user_id = str(uuid.uuid4())
    email = f"test_user_{new_user_id[:8]}@example.com"
    encrypted_password = "password123" # Mật khẩu giả, không dùng để login thật nhưng đủ để giữ chỗ
    
    now = datetime.now(timezone.utc)

    # SQL để insert vào bảng auth.users (Schema 'auth' của Supabase)
    # Lưu ý: Cần insert vào schema 'auth', không phải 'public'
    # Instance_id có thể là bất kỳ UUID nào, Supabase dùng '00000000-0000-0000-0000-000000000000' cho các user tự tạo
    sql = sa.text("""
        INSERT INTO auth.users (
            instance_id,
            id,
            aud,
            role,
            email,
            encrypted_password,
            email_confirmed_at,
            created_at,
            updated_at,
            confirmation_token,
            recovery_token
        ) VALUES (
            '00000000-0000-0000-0000-000000000000',
            :id,
            'authenticated',
            'authenticated',
            :email,
            :password,
            :now,
            :now,
            :now,
            '',
            ''
        )
    """)

    async with engine.begin() as conn:
        try:
            await conn.execute(sql, {
                "id": new_user_id,
                "email": email,
                "password": encrypted_password,
                "now": now
            })
            print(f"\n✅ SUCCESS: Created seed user in auth.users")
            print(f"User ID: {new_user_id}")
            print(f"Email:   {email}")
            print("\nCopy User ID trên để chạy script test e2e_phase1.py")
        except Exception as e:
            print(f"\n❌ ERROR: Could not insert user. Details: {e}")

if __name__ == "__main__":
    asyncio.run(seed_user())