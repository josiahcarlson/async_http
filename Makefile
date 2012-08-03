SHELL=/bin/bash

clean:
	-rm -f *.pyc async_http/*.pyc README.html MANIFEST
	-rm -rf build dist

install:
	python setup.py install

upload:
	python setup.py sdist upload
