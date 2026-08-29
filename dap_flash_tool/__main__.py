"""支持两种运行方式：
    1) python -m dap_flash_tool          （在项目根目录下）
    2) python dap_flash_tool\\__main__.py （直接运行本文件）

直接运行本文件时，Python 只把脚本所在目录（dap_flash_tool/）加入 sys.path，
包本身不在导入路径上；这里手动把项目根目录加进去，保证两种方式都能跑。
"""

import os
import sys

# 项目根目录 = 本文件所在目录的上一级
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_PKG_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dap_flash_tool.app import main  # noqa: E402

if __name__ == "__main__":
    main()
