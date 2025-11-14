import os
from setuptools import setup, find_packages

setup(
    name="ensync-sdk",
    version="0.4.2",
    packages=find_packages(),
    install_requires=[
        "ensync-core>=0.1.0",
        "grpcio>=1.50.0",
        "grpcio-tools>=1.50.0",
    ],
    extras_require={
        "dev": [
            "python-dotenv>=0.19.0",
        ]
    },
    author="EnSync Team",
    author_email="dev@ensync.cloud",
    description="Python SDK for EnSync Engine - high-performance real-time messaging via gRPC",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    url="https://github.com/EnSync-engine/Python-SDK",
    keywords="ensync, grpc, messaging, real-time, pubsub",
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
