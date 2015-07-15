#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='SSS',
    version='2.0',
    description='Simple Sword Server',
    author='Richard Jones',
    author_email='rich.d.jones@gmail.com',
    url='http://www.swordapp.org/',
    packages=find_packages(exclude=['tests']),
    install_requires=[
        "lxml==3.4.4"
    ]
)
