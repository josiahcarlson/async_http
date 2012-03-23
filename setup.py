#!/usr/bin/env python

from distutils.core import setup

with open('README') as f:
    long_description = f.read()

setup(
    name='async_http',
    version='.10',
    description='An http/https client library that works with asyncore/asynchat',
    author='Josiah Carlson',
    author_email='josiah.carlson@gmail.com',
    url='https://github.com/josiahcarlson/async_http',
    packages=['async_http'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)',
        'Programming Language :: Python',
    ],
    license='GNU LGPL v2.1',
    long_description=long_description,
)
