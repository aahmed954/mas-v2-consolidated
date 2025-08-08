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