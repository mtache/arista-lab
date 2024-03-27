all: build publish

build:
	poetry update
	poetry build
	poetry install

publish:
	poetry publish