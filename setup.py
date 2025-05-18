from setuptools import setup, find_packages

setup(
    name="scipfs",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.0",
        "requests>=2.20",
        "importlib-metadata>=1.0; python_version < '3.8'", # For entry points
    ],
    entry_points={
        "console_scripts": [
            "scipfs = scipfs.cli:cli",  # CLI entry point
        ],
    },
    author="The SciPhi Initiative, LLC",
    description="A CLI tool to manage file clusters on IPFS for communities",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/CameronBeebe/scipfs",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
)
