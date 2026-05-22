from setuptools import find_packages, setup

setup(
    name="agenticse",
    version="0.1.0",
    description="Agent Memory Subsystem (AMS) for industrial-grade Coding Agents.",
    author="AgenticSE contributors",
    packages=find_packages(exclude=("tests", "examples")),
    python_requires=">=3.8",
    install_requires=[],
    entry_points={
        "console_scripts": [
            "agenticse=agenticse.cli:main",
        ],
    },
    extras_require={
        "dev": ["pytest>=7.0"],
    },
)
