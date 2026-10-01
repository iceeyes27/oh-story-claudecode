#!/usr/bin/env python3
"""Agent-neutral entry point. Python 3.9+; no third-party dependencies."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.novel-kit/scripts'))


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    if sys.version_info < (3, 9):
        print('novel-kit requires Python 3.9+.', file=sys.stderr)
        return 2
    if len(sys.argv) > 1 and sys.argv[1] in {'setup', 'doctor'}:
        import adapters
        return adapters.main(ROOT, sys.argv[1:])
    # Load under a distinct name so importing this entry point cannot shadow the core.
    import importlib.util
    spec = importlib.util.spec_from_file_location('novel_core', ROOT / '.novel-kit/scripts/novel.py')
    core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
    return core.main(['--root', str(ROOT), *sys.argv[1:]])


if __name__ == '__main__':
    sys.exit(main())
