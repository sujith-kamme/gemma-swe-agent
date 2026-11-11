# Package the competition's sample_submission UNCHANGED (dummy adapters included) as /kaggle/working/submission.zip.
# Calibration: checks whether the 0.20 leaderboard cluster is the stock sample agent.
import glob
import os
import shutil
import zipfile
from pathlib import Path

src = Path(glob.glob('/kaggle/input/**/sample_submission/agent.yaml', recursive=True)[0]).parent
zip_path = Path(shutil.make_archive('/kaggle/working/submission', 'zip', root_dir=src))
with zipfile.ZipFile(zip_path) as zf:
    names = zf.namelist()
assert 'agent.yaml' in names, names
print(f'{zip_path} ok: {len(names)} entries, {os.path.getsize(zip_path)} bytes')
print('\n'.join(sorted(names)))
