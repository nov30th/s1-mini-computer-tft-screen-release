pip install python-minifier Nuitka
python -m python_minifier --rename-globals -o dist/core.py core.py
echo yes | python -m nuitka --standalone --onefile-no-compression --onefile dist/core.py