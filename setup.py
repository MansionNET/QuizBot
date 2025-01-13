from setuptools import setup, find_packages

setup(
    name="quizbot_mansionnet",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "aiohttp>=3.8.0",
        "irc>=20.0.0",
        "asyncio>=3.4.3",
        "asyncio-irc>=0.2.2",
        "sqlalchemy>=1.4.0",
        "aiosqlite>=0.17.0",
        "httpx>=0.24.0",
        "python-dotenv>=0.19.0",
    ],
    python_requires=">=3.9",
)