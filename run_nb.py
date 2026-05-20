import json
import nbformat
from nbconvert.preprocessors import ExecutePreprocessor
import traceback
import sys

try:
    nb_path = 'notebooks/04-search-and-query.ipynb'
    with open(nb_path) as f:
        nb = nbformat.read(f, as_version=4)

    for cell in nb.cells:
        if 'id' in cell:
            cell['id'] = cell['id'].replace('#', '').replace(' ', '_')

    ep = ExecutePreprocessor(timeout=600, kernel_name='python3')
    ep.preprocess(nb, {'metadata': {'path': 'notebooks/'}})

    with open('/tmp/nb04_executed.ipynb', 'w', encoding='utf-8') as f:
        nbformat.write(nb, f)

    found = False
    for cell in nb['cells']:
        src = ''.join(cell.get('source', []))
        if 'legal-foundry-agent-chase' in src and 'CHASE_INSTRUCTIONS' in src:
            found = True
            for o in cell.get('outputs', []):
                t = o.get('text')
                if isinstance(t, list): print(''.join(t))
                elif t: print(t, end='')
            break
    if not found:
        print("Target cell not found in notebook.")
except Exception as e:
    traceback.print_exc()
