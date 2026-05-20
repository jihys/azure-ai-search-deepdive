import json, os

path = 'notebooks/01-infra-deployment.ipynb'
with open(path, 'r', encoding='utf-8') as f:
    nb = json.load(f)

new_source_text = """import subprocess, sys, os, datetime as dt
from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas

# 새로 배포된 storage account 이름 — 위 cfg / outputs 에서 가져옴
DEST_ACCOUNT = outputs.get('storageAccountName', {}).get('value') or os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
DEST_CONTAINER = 'raw-documents'

# pubzip 의 seed tar.gz 는 anonymous access 차단 → User-Delegation SAS 즉석 생성
# (호출 사용자는 pubzip0513143342 에 'Storage Blob Data Reader' 이상 필요)
PUBZIP_ACCOUNT   = 'pubzip0513143342'
PUBZIP_CONTAINER = 'seed'
PUBZIP_BLOB      = 'raw-documents-seed.tar.gz'

cred = AzureCliCredential()
pubzip_svc = BlobServiceClient(account_url=f'https://{PUBZIP_ACCOUNT}.blob.core.windows.net', credential=cred)
now = dt.datetime.now(dt.timezone.utc)
udk = pubzip_svc.get_user_delegation_key(key_start_time=now - dt.timedelta(minutes=5),
                                          key_expiry_time=now + dt.timedelta(hours=2))
sas = generate_blob_sas(
    account_name=PUBZIP_ACCOUNT,
    container_name=PUBZIP_CONTAINER,
    blob_name=PUBZIP_BLOB,
    user_delegation_key=udk,
    permission=BlobSasPermissions(read=True),
    expiry=now + dt.timedelta(hours=2),
)
SEED_URL = f'https://{PUBZIP_ACCOUNT}.blob.core.windows.net/{PUBZIP_CONTAINER}/{PUBZIP_BLOB}?{sas}'
print('[sas] generated 2h read-only User-Delegation SAS for pubzip seed blob')

print(f"Seeding {DEST_ACCOUNT}/{DEST_CONTAINER} from public bundle ...")
rc = subprocess.run(
    [sys.executable, '../scripts/seed_raw_documents.py',
     '--dest-account', DEST_ACCOUNT,
     '--dest-container', DEST_CONTAINER],
    check=False,
    env={**os.environ, 'SEED_URL': SEED_URL},
)
print(f"\nexit code: {rc.returncode}")"""

lines = new_source_text.split('\n')
source = [line + '\n' for line in lines[:-1]] + [lines[-1]]

found = False
for cell in nb['cells']:
    raw_source = "".join(cell.get('source', []))
    if 'seed_raw_documents.py' in raw_source:
        cell['cell_type'] = 'code'
        cell['source'] = source
        cell['outputs'] = []
        cell['execution_count'] = None
        found = True
        break

if not found:
    print('Cell not found!')
    exit(1)

with open(path, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
    f.write('\n')
