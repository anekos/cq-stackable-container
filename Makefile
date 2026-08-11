.PHONY: watch
watch:
	axe src/**/*.py -- uv run stackable-container -- build --show

.PHONY: build
build:
	axe src/**/*.py -- uv run stackable-container -- build
