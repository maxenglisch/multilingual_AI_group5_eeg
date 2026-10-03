from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from .video_utils import VIDEO_RE,file_sha256,media_is_valid,refresh_video_manifest


def merge_videos(source_dir,target_dir,backup_dir=None,dry_run=False):
    source=Path(source_dir); target=Path(target_dir); target.mkdir(parents=True,exist_ok=True)
    backup=Path(backup_dir) if backup_dir else None; records=[]
    for incoming in sorted(source.iterdir(),key=lambda p:p.name.lower()):
        if not VIDEO_RE.fullmatch(incoming.name): continue
        if not media_is_valid(incoming):
            records.append({"file":incoming.name,"action":"rejected_invalid"}); continue
        destination=target/incoming.name; action="copied_new"
        if destination.exists():
            if media_is_valid(destination) and file_sha256(destination)==file_sha256(incoming): action="unchanged_identical"
            elif incoming.stat().st_mtime > destination.stat().st_mtime: action="replaced_with_newer"
            else: action="conflict_kept_existing"
        if action in {"copied_new","replaced_with_newer"} and not dry_run:
            if destination.exists() and backup:
                backup.mkdir(parents=True,exist_ok=True); shutil.copy2(destination,backup/destination.name)
            shutil.copy2(incoming,destination)
        records.append({"file":incoming.name,"action":action,"source_size":incoming.stat().st_size,
                        "source_modified":incoming.stat().st_mtime})
    manifest=None
    if not dry_run: manifest=str(refresh_video_manifest(target)[0])
    return {"source":str(source.resolve()),"target":str(target.resolve()),"records":records,"manifest":manifest}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True);parser.add_argument("--target",required=True)
    parser.add_argument("--backup-dir");parser.add_argument("--log",required=True);parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args(argv); result=merge_videos(args.source,args.target,args.backup_dir,args.dry_run)
    log=Path(args.log);log.parent.mkdir(parents=True,exist_ok=True);log.write_text(json.dumps(result,indent=2),encoding="utf-8")
    counts={}
    for item in result["records"]: counts[item["action"]]=counts.get(item["action"],0)+1
    print(json.dumps(counts,indent=2));print(f"Merge log: {log.resolve()}");return 0


if __name__=="__main__": raise SystemExit(main())
