SHELL := /bin/bash
.PHONY: up down status health qdrant tei

up: qdrant tei
	@echo "Services started."

down:
	-docker compose -f ~/qdrant/docker-compose.yml down
	-docker compose -f ~/local-emb/docker-compose.yml down

status:
	@echo "Qdrant:" && curl -s http://localhost:6333/ | jq .status || true
	@echo "TEI:" && curl -s http://localhost:8085/health | jq . || true

health:
	. ~/.venvs/masv2/bin/activate && SKIP_M2BERT=1 PYTHONPATH=. python scripts/embed_healthcheck.py

qdrant:
	@docker compose -f ~/qdrant/docker-compose.yml up -d

tei:
	@docker compose -f ~/local-emb/docker-compose.yml up -d

.PHONY: qdrant-up qdrant-down qdrant-cpu obsv-up obsv-down redis-up redis-down clean-rebuild ports-guard

qdrant-up:
	docker compose -f docker-compose.gpu.yml up -d

qdrant-down:
	docker compose -f docker-compose.gpu.yml down

qdrant-cpu:
	docker compose -f docker-compose.cpu.yml up -d

obsv-up:
	docker compose -f docker-compose.observability.yml up -d --remove-orphans

obsv-down:
	docker compose -f docker-compose.observability.yml down

redis-up:
	docker compose -f docker-compose.redis.yml up -d

redis-down:
	docker compose -f docker-compose.redis.yml down

clean-rebuild:
	scripts/clean_rebuild.sh

ports-guard:
	AUTO_FIX=1 ./scripts/ports_guard.sh
loadenv := ./scripts/load_env.sh

.PHONY: api
api:
	@source .venv/bin/activate || source ~/.venvs/masv2/bin/activate; $(loadenv); \
	uvicorn src.api_v2:app --host $$UVICORN_HOST --port $$UVICORN_PORT

.PHONY: workers
workers:
	@source .venv/bin/activate || source ~/.venvs/masv2/bin/activate; $(loadenv); \
	for i in 1 2 3 4; do (rq worker high_throughput &); done; wait

.PHONY: metro
metro:
	@source .venv/bin/activate || source ~/.venvs/masv2/bin/activate; $(loadenv); \
	nohup scripts/forensics/run_forensic_ingest.sh "$$DATA_ROOT/$$PRIORITY_FOLDER" > logs/forensic-metro.log 2>&1 & \
	&& tail -n 120 -f logs/forensic-metro.log

.PHONY: health
health:
	@source .venv/bin/activate || source ~/.venvs/masv2/bin/activate; $(loadenv); \
	SKIP_M2BERT=1 PYTHONPATH=. python scripts/embed_healthcheck.py || true; \
	curl -s "http://localhost:$$UVICORN_PORT/metrics" | head -n 3 || true; \
	curl -s "http://localhost:8088/system-check/run?key=$$CONTROL_API_KEY" | jq .
