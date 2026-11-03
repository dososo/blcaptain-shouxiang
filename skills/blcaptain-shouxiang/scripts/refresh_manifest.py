"""重算 references/文件摘要.json：技能入口、脚本、知识与模板；不含宿主界面元数据（agents/）、缓存和清单自身。

先写临时文件再原子替换；--检查 只比较不写入，有差异时退出码 1。
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'references' / '文件摘要.json'
SCOPE = ('LICENSE', 'SKILL.md', 'assets', 'references', 'scripts')


def collect():
    out = {}
    for top in SCOPE:
        base = ROOT / top
        paths = [base] if base.is_file() else sorted(p for p in base.rglob('*') if p.is_file())
        for p in paths:
            if '__pycache__' in p.parts or p.name == '.DS_Store' or p.resolve() == MANIFEST.resolve() or p.is_symlink():
                continue
            out[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return dict(sorted(out.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--检查', action='store_true', help='只比较，不写入')
    args = parser.parse_args()
    new = collect()
    old = json.loads(MANIFEST.read_text(encoding='utf-8')) if MANIFEST.exists() else {}
    diff = {'新增': sorted(set(new) - set(old)), '删除': sorted(set(old) - set(new)),
            '变更': sorted(k for k in set(new) & set(old) if new[k] != old[k])}
    if not args.检查 and any(diff.values()):
        tmp = MANIFEST.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(tmp, MANIFEST)
    print(json.dumps({'文件数': len(new), '已写入': not args.检查 and any(diff.values()), **diff}, ensure_ascii=False, indent=2))
    return 1 if args.检查 and any(diff.values()) else 0


if __name__ == '__main__':
    raise SystemExit(main())
