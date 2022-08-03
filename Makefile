TESTING_WHEEL = ceos_lab-0.1.0-py3-none-any.whl

all: build install

build:
	poetry build

uninstall:
	pip3 uninstall ceos-lab -y

install: uninstall
	pip3 install dist/$(TESTING_WHEEL)
