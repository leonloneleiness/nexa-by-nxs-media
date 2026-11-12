"""Build the small native kernel using an existing MinGW toolchain."""
from pathlib import Path
import shutil
import subprocess
import os

ROOT = Path(__file__).resolve().parents[1]

def main():
    compiler = shutil.which('g++') or r'C:\Program Files\CodeBlocks\MinGW\bin\g++.exe'
    if not Path(compiler).is_file():
        raise SystemExit('Install a C++ compiler or build native/CMakeLists.txt with CMake.')
    out = ROOT / 'nexa/native/nexa_geometry.dll'
    env = dict(os.environ)
    env['PATH'] = str(Path(compiler).parent) + os.pathsep + env.get('PATH', '')
    subprocess.run([compiler, '-O3', '-std=c++17', '-shared', '-static-libgcc', '-static-libstdc++',
                    str(ROOT / 'native/geometry.cpp'), '-o', str(out)], check=True, env=env)
    print(out)

if __name__ == '__main__':
    main()
