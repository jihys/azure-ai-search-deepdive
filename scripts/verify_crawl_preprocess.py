import os, re, collections
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
load_dotenv()

STG = os.environ["AZURE_STORAGE_ACCOUNT_NAME"]
cred = DefaultAzureCredential(exclude_managed_identity_credential=True, exclude_workload_identity_credential=True)
svc = BlobServiceClient(f"https://{STG}.blob.core.windows.net", credential=cred)


def list_all(container):
    cc = svc.get_container_client(container)
    return [b.name for b in cc.list_blobs()]


raw = list_all("raw-documents")
print(f"raw-documents total blobs: {len(raw)}")
try:
    proc = list_all("processed-documents")
    print(f"processed-documents total blobs: {len(proc)}")
except Exception as e:
    proc = []
    print(f"processed-documents: ERROR {e}")

raw_pat = re.compile(r"^([^/]+)/(\d{4}-\d{2}-\d{2})/([^/]+)$")
raw_by_src_date = collections.defaultdict(lambda: collections.defaultdict(set))
raw_by_src_name = collections.defaultdict(lambda: collections.defaultdict(set))
for n in raw:
    m = raw_pat.match(n)
    if not m:
        continue
    src, date, name = m.group(1), m.group(2), m.group(3)
    if not name.endswith(".json"):
        continue
    base = name[:-5]
    raw_by_src_date[src][date].add(base)
    raw_by_src_name[src][base].add(date)

print("\n## RAW per source (json files only)")
print(f"  {'src':<8} {'total':>8}  dates")
for src in sorted(raw_by_src_date):
    total = sum(len(v) for v in raw_by_src_date[src].values())
    dates = sorted(raw_by_src_date[src].keys())
    print(f"  {src:<8} {total:>8}  {len(dates)} dates: {dates[0]}..{dates[-1]}")

print("\n## Cross-date duplicates (same name in 2+ dates within a source)")
dup_total = 0
for src in sorted(raw_by_src_name):
    dups = {n: sorted(ds) for n, ds in raw_by_src_name[src].items() if len(ds) > 1}
    print(f"  {src}: {len(dups)} duplicated filenames")
    dup_total += len(dups)
    for n, ds in sorted(dups.items())[:5]:
        print(f"    e.g. {n} in {ds}")
print(f"  ==> TOTAL duplicate filenames across all sources: {dup_total}")

print("\n## Cross-source same-name occurrence (informational)")
name_to_srcs = collections.defaultdict(set)
for src, m in raw_by_src_name.items():
    for n in m:
        name_to_srcs[n].add(src)
xs = {n: sorted(s) for n, s in name_to_srcs.items() if len(s) > 1}
print(f"  filenames in 2+ sources: {len(xs)}")

print("\n## PROCESSED per source (blob count)")
proc_by_src = collections.Counter()
for n in proc:
    parts = n.split("/", 1)
    if len(parts) >= 1:
        proc_by_src[parts[0]] += 1
for src in sorted(set(list(raw_by_src_date.keys()) + list(proc_by_src.keys()))):
    raw_cnt = sum(len(v) for v in raw_by_src_date.get(src, {}).values())
    proc_cnt = proc_by_src.get(src, 0)
    print(f"  {src:<8} raw_json={raw_cnt:>6}  processed_blobs={proc_cnt:>6}")

print("\n## PROCESSED doc counts (parsing .jsonl)")
doc_counter = collections.Counter()
for n in proc:
    if not n.endswith(".jsonl"):
        continue
    parts = n.split("/", 1)
    if len(parts) < 2:
        continue
    src = parts[0]
    try:
        bc = svc.get_blob_client("processed-documents", n)
        data = bc.download_blob().readall().decode("utf-8")
        cnt = sum(1 for line in data.splitlines() if line.strip())
        doc_counter[src] += cnt
    except Exception as e:
        print(f"  ERR reading {n}: {e}")
        continue
for src in sorted(set(list(raw_by_src_date.keys()) + list(doc_counter.keys()))):
    raw_cnt = sum(len(v) for v in raw_by_src_date.get(src, {}).values())
    proc_docs = doc_counter.get(src, 0)
    if raw_cnt == proc_docs:
        match = "OK"
    else:
        match = f"DIFF({proc_docs - raw_cnt:+d})"
    print(f"  {src:<8} raw_json={raw_cnt:>6}  processed_docs={proc_docs:>6}  {match}")
