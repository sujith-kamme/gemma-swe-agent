# Package the v3 agent (Kaggle dataset sujithkamme/gemma4-agent-v3) as /kaggle/working/submission.zip.
import glob
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

WHEELHOUSE = Path(glob.glob('/kaggle/input/**/gemma-4-developer-agent-wheelhouse', recursive=True)[0])
harness = [w for w in WHEELHOUSE.glob('*.whl') if w.name.split('-')[0] in ('swegemma', 'adk_submission', 'adk_eval_core')]
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', *map(str, harness)], check=True)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-index', f'--find-links={WHEELHOUSE}', 'google-adk'], check=False)

from adk_submission import validate_directory  # noqa: E402

src = Path(glob.glob('/kaggle/input/**/gemma4-agent-v3/agent.yaml', recursive=True)[0]).parent
agent = Path('/kaggle/working/agent')
shutil.rmtree(agent, ignore_errors=True)
shutil.copytree(src, agent, ignore=shutil.ignore_patterns('dataset-metadata.json', '__pycache__', '.DS_Store'))
validate_directory(agent)
zip_path = Path(shutil.make_archive('/kaggle/working/submission', 'zip', root_dir=agent))
shutil.rmtree(agent)
with zipfile.ZipFile(zip_path) as zf:
    names = zf.namelist()
assert 'agent.yaml' in names, names
print(f'{zip_path} ok: {len(names)} entries, {os.path.getsize(zip_path)} bytes')
print('\n'.join(sorted(names)))
