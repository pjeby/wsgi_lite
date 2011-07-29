#!/usr/bin/env python
"""Distutils setup file"""

import ez_setup
ez_setup.use_setuptools()
from setuptools import setup

# Metadata
PACKAGE_NAME = "wsgi_lite"
PACKAGE_VERSION = "0.5a1"

def get_description():
    # Get our long description from the documentation
    f = file('README')
    lines = []
    for line in f:
        if not line.strip():
            break     # skip to first blank line
    for line in f:
        if line.startswith('.. contents::'):
            break     # read to table of contents
        lines.append(line)
    f.close()
    return ''.join(lines)

setup(
    name=PACKAGE_NAME,
    version=PACKAGE_VERSION,
    description= "A better way to write WSGI apps and middleware",
    long_description = get_description(),
    url = "http://cheeseshop.python.org/pypi/wsgi_lite",
    author="P.J. Eby",
    author_email="web-sig@python.org",
    license="ASF",
    #test_suite = 'wsgi2.test_suite',
    py_modules = ['wsgi_lite'],
    #install_requires = ['DecoratorTools>=1.8'],
)

