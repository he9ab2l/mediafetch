"""无第三方依赖的测试运行器：python3 tests/run.py"""
import importlib
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failed = 0
for path in sorted(Path(__file__).parent.glob('test_*.py')):
    mod = importlib.import_module(f'tests.{path.stem}')
    for name in sorted(dir(mod)):
        if not name.startswith('test_'):
            continue
        try:
            getattr(mod, name)()
            print(f'PASS {path.stem}::{name}')
        except Exception:
            failed += 1
            print(f'FAIL {path.stem}::{name}')
            traceback.print_exc()
print(f'\n{failed} failed')
sys.exit(1 if failed else 0)
