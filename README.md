# College Football Data Python Toolkit

A modular Python package for fetching, transforming, and analyzing college football data using the [CollegeFootballData API](https://apinext.collegefootballdata.com/#/).

## Features
- Pythonic interface to the CollegeFootballData API
- Modular codebase for extending and adding new endpoints
- Built-in data validation using [pydantic](https://docs.pydantic.dev/) and [pandera](https://pandera.readthedocs.io/)
- Easily integrates with pandas for analysis

## Project Structure
```
cfb_data/
├── requirements.txt           # Python dependencies
├── notebooks/                 # (Currently empty) — place for example Jupyter notebooks
├── cfb_data/                  # Main package code
│   ├── base/                  # Core/base API access
│   │   ├── api/
│   │   │   └── base_api.py
│   │   └── __init__.py
│   ├── game/                  # Game-specific API modules
│   │   ├── api/
│   │   │   └── game_api.py
│   │   ├── models/
│   │   │   ├── pydantic/      # Pydantic model definitions
│   │   │   └── pandera/       # Pandera schema definitions
│   │   └── __init__.py
│   ├── tests/                 # unit tests for the package
│   └── __init__.py
├── setup.sh                   # Shell setup script for environment
└── README.md
```

## Requirements
- Python 3.9+
- pip

Install dependencies:
```sh
pip install -r cfb_data/requirements.txt
```

## Setup
1. **Clone the repository:**
```sh
git clone [REPO_URL]
cd [REPO_DIRECTORY]
```
2. **Create and activate a virtual environment (optional but recommended):**
```sh
python3 -m venv .env
source .env/bin/activate
```
3. **Install dependencies:**
```sh
pip install -r cfb_data/requirements.txt
```
4. **Run the setup script (optional):**
```sh
./setup.sh
```
5. **Configure your API key:**
Register for an API key at [CollegeFootballData.com](https://collegefootballdata.com/) and set it as an environment variable:
```sh
export CFB_API_KEY="your_api_key"
```
Or add it to a `.env` file.

## Basic Usage
TODO: fill out section

## Developing
- Code is organized by domain (`game`, `base`).
- Models are separated using Pydantic and Pandera for type and schema validation.
- Notebooks and tests directories are ready for expansion.

## Pre-commit hooks
To enable pre-commit checks:
```sh
pip install pre-commit
pre-commit install
```

## License
See [LICENSE](LICENSE).

## Contributing
Contributions are welcome! Fork the repo, make changes in a feature branch, and submit a pull request.

## TODO
- Add more endpoint wrappers
- Write example Jupyter notebooks
- Improve test coverage

---
This project is not affiliated with CollegeFootballData.com.
