from setuptools import setup, find_packages

setup(
    name="agentse",
    version="0.1.0",
    description="Autonomous Multi-Agent Software Engineering Team with Self-Learning",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "pydantic>=2.0.0",
        "rich>=13.0.0",
        "typer>=0.9.0",
        "httpx>=0.27.0",
        "tenacity>=8.2.0",
        "structlog>=24.1.0",
    ],
    entry_points={
        "console_scripts": [
            "agentse=agentse.cli:app",
        ],
    },
)
