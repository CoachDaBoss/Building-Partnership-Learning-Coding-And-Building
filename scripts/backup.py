#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import shutil
root=Path(__file__).resolve().parents[1]
out=root/'backups'
out.mkdir(exist_ok=True)
stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
base=out/f'ihd_backup_{stamp}'
archive=shutil.make_archive(str(base),'zip',root_dir=root/'data')
print(f'Backup created: {archive}')
