"""让测试可导入未打包安装的 eval/ 评测工具包（把仓库根加入 sys.path）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
