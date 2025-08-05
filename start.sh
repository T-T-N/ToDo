#!/bin/bash

# Install pyenv if not already installed
if ! command -v pyenv &> /dev/null; then
    curl https://pyenv.run | bash
    export PATH="$HOME/.pyenv/bin:$PATH"
    eval "$(pyenv init -)"
fi

# Install Python 3.11.7 if not already installed
pyenv install -s 3.11.7
pyenv global 3.11.7

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start gunicorn
exec gunicorn --config gunicorn.conf.py app:app
