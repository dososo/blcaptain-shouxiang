"""掌中有话命令入口：诊断、指南。Python 3.10 及以上；Pillow 可选（有则把原照压成 JPEG 内嵌，无则只收 PNG）。"""
import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def doctor():
    manifest = json.loads((ROOT / 'references' / '文件摘要.json').read_text(encoding='utf-8'))
    errors = []
    for name, digest in manifest.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(name)
    lib = json.loads((ROOT / 'references' / '指南断语库.json').read_text(encoding='utf-8'))
    try:
        import PIL
        pillow = PIL.__version__
    except ImportError:
        pillow = '未安装（只支持 PNG 原照）'
    return {'可用': not errors, '断语库版本': lib['版本'], '规则数': len(lib['规则']), 'Python': sys.version.split()[0], 'Pillow': pillow,
            '文件异常': errors, '摘要范围': '技能入口、脚本、断语库与契约；宿主界面元数据不计入。用于损坏检查，不替代签名。',
            '照片观察': '需要宿主能查看用户照片；脚本不内置视觉模型', '网络': '本脚本不联网，不上传照片'}


def main():
    parser = argparse.ArgumentParser(description='掌中有话：按宿主看图记录生成个人手相指南 HTML')
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('诊断', help='检查文件完整性与运行环境')
    s = sub.add_parser('指南', help='按宿主看图记录生成直白的个人手相指南 HTML')
    s.add_argument('--输入', required=True)
    s.add_argument('--输出', required=True)
    s.add_argument('--原照', required=True)
    s.add_argument('--问事')
    s.add_argument('--日期', help='YYYY-MM-DD，默认今天；回放时传原日期')
    args = parser.parse_args()
    try:
        if args.cmd == '诊断':
            result = doctor()
            status = 0 if result['可用'] else 2
        else:
            path = Path(args.输入).expanduser().resolve()
            out = Path(args.输出).expanduser().resolve()
            if path.stat().st_size > 65536:
                raise ValueError('观察记录超过64KB，请只保留本次观察。')
            if out.is_relative_to(ROOT) or ROOT.is_relative_to(out):
                raise ValueError('请把报告保存到技能目录之外的新目录。')
            if out.exists():
                raise ValueError('输出目录已存在，请使用新目录，避免覆盖。')
            payload = json.loads(path.read_text(encoding='utf-8'))
            from guide_reading import build
            from guide_layout import write
            day = dt.date.fromisoformat(args.日期) if args.日期 else dt.date.today()
            content = build(payload, question=args.问事, today=day)
            write(content, Path(args.原照).expanduser().resolve(), out, payload)
            result = {'完成': True, '输出目录': str(out), '文件': ['掌中有话.html', '内容.json', '回放.json'],
                      '说明': '已生成个人手相指南：快速总结、指数、特征＋解读、流年流月、人生阶段、关注点、建议、优势与总结；依据与方法收在页尾。'}
            status = 0
    except (ValueError, OSError, KeyError, TypeError) as e:
        result = {'完成': False, '错误': str(e)}
        status = 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return status


if __name__ == '__main__':
    sys.exit(main())
