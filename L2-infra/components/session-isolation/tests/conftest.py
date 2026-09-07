# conftest for L2 component smoke tests
# 确保 pytest 不尝试收集上层 __init__.py 作为测试包
collect_ignore = ["../__init__.py"]
