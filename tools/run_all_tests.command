#!/bin/bash
# macOS：双击运行全套测试（会自动打开终端窗口）
cd "$(dirname "$0")/.." || exit 1

if [ -x ".conda/bin/python" ]; then
  PY=".conda/bin/python"
elif [ -x ".venv-build/bin/python" ]; then
  PY=".venv-build/bin/python"
else
  PY="$(command -v python3)"
fi

echo "使用解释器: $PY"
"$PY" tools/run_all_tests.py "$@"
CODE=$?

echo
if [ -t 0 ]; then
  read -n 1 -s -r -p "按任意键关闭窗口..."
fi
exit $CODE
