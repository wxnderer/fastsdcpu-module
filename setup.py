from setuptools import setup, find_packages

requirements = []
with open('requirements.txt') as f:
    for line in f:
        requirements.append(line.strip().split('=')[0])

setup(
    name="fastsdcpu",
    version="0.1.0",
    packages=['fastsdcpu'],
    package_dir={'fastsdcpu': 'src'},
    install_requires=requirements,
)
