import json

path = 'notebooks/01-infra-deployment.ipynb'
with open(path, 'r', encoding='utf-8') as f:
    nb = json.load(f)

for cell in nb.get('cells', []):
    if cell.get('cell_type') == 'code':
        source = cell.get('source', [])
        source_str = "".join(source)
        if 'seed_raw_documents.py' in source_str:
            new_source = []
            for line in source:
                # Clean up the previous botched attempt if necessary
                if line.strip() == "--workers', '32']," or line.strip() == ",'--workers', '32'],":
                     continue
                
                if "'--dest-container', DEST_CONTAINER," in line:
                    # Found the target line
                    new_source.append("     '--dest-container', DEST_CONTAINER,\n")
                    new_source.append("     '--workers', '32',\n")
                elif "'--dest-container', DEST_CONTAINER]" in line:
                    new_source.append("     '--dest-container', DEST_CONTAINER,\n")
                    new_source.append("     '--workers', '32'],\n")
                elif line.strip() == ",\n":
                    # Skip the stray comma from previous mistake
                    continue
                elif "'--workers', '32'" in line:
                    # Skip previously added workers lines to avoid duplicates
                    continue
                else:
                    new_source.append(line)
            cell['source'] = new_source

with open(path, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
    f.write('\n')
