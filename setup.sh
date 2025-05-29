#!/usr/bin/env bash
set -e

# 1. Create the virtual environment in .env if it doesn't exist
if [ ! -d ".env" ]; then
  python3 -m venv .env            # Uses the built-in venv module to create .env  [oai_citation:0‡Python Packaging](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/?utm_source=chatgpt.com)
fi

# 2. Activate the virtual environment
#    (this prepends .env/bin to your PATH so python & pip now refer to the venv)  [oai_citation:1‡Stack Overflow](https://stackoverflow.com/questions/76574045/how-to-enter-a-virtual-environment-through-a-shell-script?utm_source=chatgpt.com)
source .env/bin/activate

# 3. (Optional) Upgrade pip to the latest version
pip install --upgrade pip

# 4. Install all requirements
pip install -r cfb_data/requirements.txt
