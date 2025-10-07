import os
from setuptools import setup, find_packages

setup(
    name="ensync-sdk",
    version="0.2.0",
    packages=["ensync"],
    package_dir={"ensync": "ensync"},
    py_modules=[],
    include_package_data=True,
    package_data={
        "ensync": [
            "__init__.py", 
            "ecc_crypto.py", 
            "error.py", 
            "websocket.py",
            "grpc_client.py",
            "ensync_pb2.py",
            "ensync_pb2_grpc.py"
        ]
    },
    install_requires=[
        "websockets>=10.0",
        "pynacl>=1.5.0",
        "grpcio>=1.50.0",
        "grpcio-tools>=1.50.0",
    ],
    extras_require={
        "dev": [
            "python-dotenv>=0.19.0",
        ]
    },
    author="EnSync Team",
    author_email="info@ensync.io",
    description="Python SDK for EnSync Engine",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    url="https://github.com/EnSync-engine/Python-SDK",
    keywords="ensync, websocket, messaging, real-time",
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
