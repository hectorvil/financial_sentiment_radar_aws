.PHONY: run test lint format quality docker-build smoke-local preflight deploy-foundation deploy-app outputs destroy

run:
	PYTHONPATH=src uv run streamlit run app/streamlit_app.py

test:
	PYTHONPATH=src uv run pytest -q

lint:
	uv run ruff check .

format:
	uv run ruff format .

quality: test lint

docker-build:
	docker build -t financial-sentiment-radar:local .

smoke-local:
	./scripts/04_local_smoke_test.sh

preflight:
	./scripts/02_preflight_local.sh

deploy-foundation:
	./scripts/00_deploy_foundation.sh

deploy-app:
	./scripts/06_build_push_app.sh && ./scripts/07_deploy_ecs.sh

outputs:
	./scripts/09_print_outputs.sh

destroy:
	./scripts/99_destroy.sh
