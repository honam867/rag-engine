# Implement: Script to debug Supabase login flow

## 1. Summary
- Scope: scripts, Phase 1 troubleshooting.
- Added a helper script to test Supabase email/password login and verify that the backend accepts the Supabase-issued JWT via `/api/me`, to help debug client/server auth mismatches.

## 2. Related spec / design
- Requirements Phase 1: `docs/requirements/requirements-phase-1.md`
- Phase 1 design: `docs/design/phase-1-design.md`
- Auth design: `docs/design/architecture-overview.md` (Supabase Auth + JWT verify)

## 3. Files touched
- `scripts/test_supabase_login.py` – New CLI script that:
  - Calls Supabase Auth password grant with provided email/password.
  - If successful, calls backend `/api/me` with the returned `access_token`.
  - Optionally decodes the JWT using `SUPABASE_JWT_SECRET` to check signature and `sub` claim.

## 4. Usage
- Example for the reported account:

```bash
poetry run python scripts/test_supabase_login.py \
  --email example@gmail.com \
  --password 'Password'
```

- The script reads Supabase and API URLs from:
  - `NEXT_PUBLIC_SUPABASE_URL` / `SUPABASE_URL`
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY` / `SUPABASE_ANON_KEY`
  - `NEXT_PUBLIC_API_BASE_URL` / `API_BASE_URL`
  - And uses `SUPABASE_JWT_SECRET` to try decoding the JWT if available.

## 5. Notes / TODO
- This script is intended as a troubleshooting tool; it does not seed users or modify DB state beyond what Supabase Auth does.
- When diagnosing issues:
  - If Supabase Auth login fails (non-200), check credentials or Supabase auth settings (password auth disabled, SMTP, etc.).
  - If `/api/me` fails but login is OK, likely `SUPABASE_JWT_SECRET` in backend is wrong or outdated compared to the Supabase project.

