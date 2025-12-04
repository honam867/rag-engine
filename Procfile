web: poetry run uvicorn server.app.main:app --reload --host 127.0.0.1 --port 8000
worker_parse: PYTHONPATH=. poetry run python server/app/workers/parse_worker.py
worker_ingest: PYTHONPATH=. poetry run python server/app/workers/ingest_worker.py