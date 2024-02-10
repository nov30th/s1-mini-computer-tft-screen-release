source .venv/Scripts/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
python3 -m python_minifier -o dist/core.py core.py
python3 -m nuitka --include-package=proxmoxer.backends --standalone --onefile-no-compression --onefile dist/core.py
# --include-package=cv2