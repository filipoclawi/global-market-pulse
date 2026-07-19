#!/usr/bin/env python3
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1];DIST=ROOT/'dist'
if DIST.exists():shutil.rmtree(DIST)
DIST.mkdir()
for name in ('index.html','.nojekyll','README.md'):
 shutil.copy2(ROOT/name,DIST/name)
for name in ('assets','data'):
 shutil.copytree(ROOT/name,DIST/name)
print(f'Built {DIST}')
