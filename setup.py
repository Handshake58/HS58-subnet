import os
import re
import codecs
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))


def read_requirements(path):
    with open(path, "r") as f:
        return [
            line.strip()
            for line in f.readlines()
            if line.strip() and not line.startswith("#")
        ]


requirements = read_requirements("requirements.txt")

with open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

with codecs.open(
    os.path.join(here, "subnet58/__init__.py"), encoding="utf-8"
) as init_file:
    version_match = re.search(
        r"^__version__ = ['\"]([^'\"]*)['\"]", init_file.read(), re.M
    )
    version_string = version_match.group(1)

setup(
    name="subnet58",
    version=version_string,
    description="Handshake58 - Bittensor Subnet 58: DRAIN Protocol scoring for AI providers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Handshake58/HS58-validator",
    author="Handshake58",
    packages=find_packages(),
    include_package_data=True,
    license="MIT",
    python_requires=">=3.9",
    install_requires=requirements,
)
