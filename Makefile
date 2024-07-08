all: update

editable:
	pipx install -e .

install:
	poetry install

update:
	poetry update

publish: update
	poetry publish --build --skip-existing