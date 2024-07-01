all:
	poetry update
	poetry publish --build --skip-existing