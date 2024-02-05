source .venv/Scripts/activate
python3 -m python_minifier -o dist/core.py core.py
python3 -m nuitka --standalone --onefile-no-compression --onefile dist/core.py