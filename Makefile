editable:
	pip cache purge
	PIPX_DEFAULT_PYTHON=$$(which python) pipx install -e .

update:
	poetry update

publish:
	poetry publish --build --skip-existing

clean:
	rm -rf dist