.PHONY: interactive
interactive:
	uv run stackable-container -- interactive

.PHONY: build
build:
	axe src/**/*.py -- uv run stackable-container -- build

.PHONY: watch
watch:
	axe src/**/*.py -- uv run stackable-container -- build --show

.PHONY: setup
setup:
	uv sync
	uv run pre-commit install
