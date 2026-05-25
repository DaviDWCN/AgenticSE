from pathlib import Path

from setuptools import find_packages, setup


README = Path(__file__).with_name("README.md").read_text(encoding="utf-8")

setup(
    name="agenticse",
    version="0.1.0",
    description="Agent Memory Subsystem (AMS) for industrial-grade Coding Agents.",
    long_description=README,
    long_description_content_type="text/markdown",
    author="AgenticSE contributors",
    packages=find_packages(exclude=("tests", "examples")),
    package_data={"agenticse": ["py.typed"]},
    python_requires=">=3.8",
    install_requires=[],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Typing :: Typed",
    ],
    entry_points={
        "console_scripts": [
            "agenticse=agenticse.cli:main",
        ],
    },
    extras_require={
        "dev": ["pytest>=7.0"],
    },
)
