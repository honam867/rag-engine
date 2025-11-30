#!/usr/bin/env python3
"""
Phase 1 E2E smoke script (no UI required).

Usage:
    poetry run python scripts/e2e_phase1.py \
        --base-url http://127.0.0.1:8000 \
        --user-id test-user \
        --email test@example.com

Auth:
    - Reads SUPABASE_JWT_SECRET from environment and signs a HS256 token with sub/email.
    - Or pass --jwt to use an existing token.

What it covers:
    - /health
    - /api/me
    - Create + list workspace
    - Create + list conversation
    - Create + list messages (with mock AI reply)
    - Optional: upload document (skipped if R2 env is missing or --skip-upload)
"""

import argparse
import os
import time
from typing import Any

import httpx
import jwt
from dotenv import load_dotenv


def build_token(secret: str, user_id: str, email: str | None) -> str:
    payload: dict[str, Any] = {"sub": user_id}
    if email:
        payload["email"] = email
    return jwt.encode(payload, secret, algorithm="HS256")  # type: ignore[no-any-return]


def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise SystemExit(f"Missing required env var: {name}")
    return val


def main() -> None:
    # Load .env so SUPABASE_JWT_SECRET (and optionally R2_*) are available without manual export.
    load_dotenv()

    parser = argparse.ArgumentParser(description="Phase 1 E2E smoke without UI.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument("--user-id", default="00000000-0000-0000-0000-000000000000", help="User id for JWT sub claim (must be valid UUID)")
    parser.add_argument("--email", default="user@example.com", help="Email claim for JWT")
    parser.add_argument("--jwt", help="Existing JWT; if omitted, script will sign using SUPABASE_JWT_SECRET")
    parser.add_argument("--skip-upload", action="store_true", help="Skip document upload even if R2 is configured")
    args = parser.parse_args()

    token = args.jwt or build_token(require_env("SUPABASE_JWT_SECRET"), args.user_id, args.email)
    headers = {"Authorization": f"Bearer {token}"}
    client = httpx.Client(base_url=args.base_url, headers=headers, timeout=10.0)

    print(f"Base URL: {args.base_url}")
    print("1) /health ...", end=" ", flush=True)
    resp = client.get("/health")
    resp.raise_for_status()
    print(resp.json())

    print("2) /api/me ...", end=" ", flush=True)
    resp = client.get("/api/me")
    resp.raise_for_status()
    me = resp.json()
    print(me)

    ws_name = f"e2e-ws-{int(time.time())}"
    print(f"3) create workspace {ws_name} ...", end=" ", flush=True)
    resp = client.post("/api/workspaces", json={"name": ws_name, "description": "e2e workspace"})
    resp.raise_for_status()
    workspace = resp.json()
    ws_id = workspace["id"]
    print(ws_id)

    print("4) list workspaces ...", end=" ", flush=True)
    resp = client.get("/api/workspaces")
    resp.raise_for_status()
    print(f"{len(resp.json())} found")

    do_upload = not args.skip_upload and all(
        os.getenv(k) for k in ["R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]
    )

    if do_upload:
        print("5) upload document ...", end=" ", flush=True)
        files = [("files", ("sample.txt", b"hello from e2e", "text/plain"))]
        resp = client.post(f"/api/workspaces/{ws_id}/documents/upload", files=files)
        resp.raise_for_status()
        upload = resp.json()
        doc_id = upload["items"][0]["document"]["id"]
        print(doc_id)

        print("6) list documents ...", end=" ", flush=True)
        resp = client.get(f"/api/workspaces/{ws_id}/documents")
        resp.raise_for_status()
        print(f"{len(resp.json().get('items', []))} found")
    else:
        print("5) upload document ... skipped (R2 env not set or --skip-upload)")
        doc_id = None

    print("7) create conversation ...", end=" ", flush=True)
    resp = client.post(f"/api/workspaces/{ws_id}/conversations", json={"title": "E2E conversation"})
    resp.raise_for_status()
    conversation = resp.json()
    conv_id = conversation["id"]
    print(conv_id)

    print("8) list conversations ...", end=" ", flush=True)
    resp = client.get(f"/api/workspaces/{ws_id}/conversations")
    resp.raise_for_status()
    print(f"{len(resp.json().get('items', []))} found")

    print("9) create message ...", end=" ", flush=True)
    resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "Ping from e2e"})
    resp.raise_for_status()
    msg = resp.json()
    print(msg["id"])

    print("10) list messages ...", end=" ", flush=True)
    resp = client.get(f"/api/conversations/{conv_id}/messages")
    resp.raise_for_status()
    print(f"{len(resp.json().get('items', []))} found")

    print("\nE2E smoke completed successfully.")
    if not do_upload:
        print("Note: document upload was skipped (no R2 config); enable R2 env or remove --skip-upload to test uploads.")


if __name__ == "__main__":
    main()
