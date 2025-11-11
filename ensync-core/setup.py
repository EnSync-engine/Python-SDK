import os
from setuptools import setup, find_packages

setup(
    name="ensync-core",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pynacl>=1.5.0",
    ],
    author="EnSync Team",
    author_email="info@ensync.io",
    description="Core utilities for EnSync SDK - encryption, decryption, and error handling",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    url="https://github.com/EnSync-engine/Python-SDK",
    keywords="ensync, encryption, utilities",
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
