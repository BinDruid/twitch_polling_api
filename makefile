DEFAULT_GOAL := dev

.PHONY: dev test

dev:
	docker compose -f docker-compose-dev.yml down
	docker compose -f docker-compose-dev.yml up

test:
	docker compose -f docker-compose-test.yml down
	docker compose -f docker-compose-test.yml run --rm twitter_api_test || true
	docker compose -f docker-compose-test.yml down

migrate:
	docker compose -f docker-compose-dev.yml exec twitter_api sh -c "alembic upgrade head"
	docker compose -f docker-compose-dev.yml exec analytics sh -c "alembic upgrade head"
