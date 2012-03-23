SHELL=/bin/bash

clean:
	-rm -f *.pyc async_http/*.pyc README.html MANIFEST
	-rm -rf build dist

install:
	python setup.py install

test:
	python -m tests.test_rpqueue

upload:
	python setup.py sdist upload
