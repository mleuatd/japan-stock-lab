#!/usr/bin/env python3
"""Private GitHub repository backup/restore for licensed J-Quants data.

Requires PRIVATE_ARCHIVE_REPO=owner/private-repo and PRIVATE_ARCHIVE_TOKEN
(a fine-grained PAT with Contents:read/write for that private repo).
Never writes market data to the public code repository.
"""
import base64
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

def configured():
    return bool(os.environ.get("PRIVATE_ARCHIVE_REPO") and os.environ.get("PRIVATE_ARCHIVE_TOKEN"))

def request(path, method="GET", payload=None):
    repo = os.environ["PRIVATE_ARCHIVE_REPO"]
    token = os.environ["PRIVATE_ARCHIVE_TOKEN"]
    base = "https://api.github.com/repos/" + repo + "/contents/"
    url = base + "/".join(urllib.parse.quote(s) for s in path.split("/"))
    headers = {"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
               "X-GitHub-Api-Version":"2022-11-28", "User-Agent":"japan-stock-lab-archive/1"}
    data = json.dumps(payload).encode() if payload is not None else None
    if data: headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=headers,method=method),timeout=90) as resp:
        return json.load(resp)

def stored_paths(path="archive/daily"):
    """List existing private files using GitHub git tree, not public GitHub contents."""
    repo=os.environ["PRIVATE_ARCHIVE_REPO"]
    token=os.environ["PRIVATE_ARCHIVE_TOKEN"]
    endpoint="https://api.github.com/repos/"+repo+"/git/trees/main?recursive=1"
    req=urllib.request.Request(endpoint,headers={"Authorization":"Bearer "+token,
               "Accept":"application/vnd.github+json","User-Agent":"japan-stock-lab-archive/1"})
    with urllib.request.urlopen(req,timeout=90) as resp: data=json.load(resp)
    if data.get("truncated"): raise RuntimeError("Private archive git tree truncated; refusing incomplete restore")
    return [x["path"] for x in data["tree"] if x.get("type")=="blob" and x["path"].startswith(path+"/") and x["path"].endswith(".csv.gz")]

def restore(root=Path(".")):
    if not configured(): return 0
    count=0
    for key in stored_paths():
        destination=root/key
        if destination.exists(): continue
        item=request(key)
        if item.get("encoding")!="base64": raise RuntimeError("Unexpected GitHub content encoding")
        import hashlib
        binary=base64.b64decode(item["content"])
        # Git SHA ensures remote file has not changed accidentally.
        sha="blob "+str(len(binary))
        digest=hashlib.sha1(sha.encode()+b"\x00"+binary).hexdigest()
        if digest!=item["sha"]: raise RuntimeError("Private archive checksum mismatch: "+key)
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_suffix(".download")
        temporary.write_bytes(binary)
        temporary.replace(destination)
        count+=1
    print("PRIVATE_RESTORED",count,flush=True)
    return count

def backup(root=Path(".")):
    if not configured(): return 0
    known=set(stored_paths())
    count=0
    for path in sorted((root/"archive/daily").rglob("*.csv.gz")):
        key=path.relative_to(root).as_posix()
        if key in known: continue
        content=base64.b64encode(path.read_bytes()).decode("ascii")
        request(key,"PUT",{"message":"Archive J-Quants day "+path.name,"content":content,"branch":"main"})
        known.add(key)
        count+=1
    print("PRIVATE_BACKED_UP",count,flush=True)
    return count

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["restore","backup"])
    args=parser.parse_args()
    if not configured():
        print("PRIVATE_ARCHIVE_NOT_CONFIGURED (cache and artifacts are temporary)",flush=True)
    else:
        (restore if args.action=="restore" else backup)()
