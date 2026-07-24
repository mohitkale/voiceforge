# Makefile helpers for common Docker workflows.
# Prefer these for accessibility; equivalent compose commands remain supported.

COMPOSE := docker compose -f docker/docker-compose.yml

.PHONY: start-cpu start-gpu stop logs smoke-openvoice

start-cpu:
	$(COMPOSE) --profile cpu up --build

start-gpu:
	$(COMPOSE) --profile gpu up --build

stop:
	$(COMPOSE) --profile cpu --profile gpu down

logs:
	$(COMPOSE) --profile cpu logs -f --tail=200

smoke-openvoice:
	python scripts/e2e_smoke_test.py --engine openvoice-v2
