"""指南模式的行为检查：确定性、问事隔离、照片变体、模块非空与 HTML 分层；不验证命运。"""
import copy
import datetime as dt
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import guide_layout
import guide_reading as gr

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'references' / '指南观察示例.json'
DAY = dt.date(2026, 11, 3)


def sample():
    return json.loads(SAMPLE.read_text(encoding='utf-8'))


def feat(obs, fid):
    return next(f for f in obs['特征'] if f['id'] == fid)


def hit_ids(content):
    return {r['编号'] for r in content['依据']['命中']}


def score(content, name):
    return next(x['分'] for x in content['指数'] if x['项'] == name)


def section(content, fid):
    return next((s for s in content['特征解读'] if s['id'] == fid), None)


def run(obs_path=None):
    checks = []
    def check(name, ok, note=''):
        checks.append({'检查': name, '通过': bool(ok), **({'说明': note} if note else {})})
    lib = gr.load_library()
    base = json.loads(Path(obs_path).read_text(encoding='utf-8')) if obs_path else sample()
    first = gr.build(copy.deepcopy(base), today=DAY, lib=lib)
    again = gr.build(copy.deepcopy(base), today=DAY, lib=lib)
    check('同一输入两次生成内容摘要一致', gr.digest(first) == gr.digest(again))

    # 问事只改主题与要点顺序，不改观察、命中与断语
    asked = gr.build(copy.deepcopy(base), question='今年会不会破财', today=DAY, lib=lib)
    same = ('特征解读', '指数', '流月', '流年', '人生阶段', '依据')
    check('换问事不改变特征解读、指数、流月、阶段与依据', all(asked[k] == first[k] for k in same)
          and asked['主题'] == '财运' and first['主题'] == '全览')
    check('问事财运时快速总结先说财运', asked['快速总结']['要点'][0]['题'] == '财运')
    health = gr.build(copy.deepcopy(base), question='身体要注意什么', today=DAY, lib=lib)
    check('问事健康时快速总结先说身体', health['快速总结']['要点'][0]['题'] == '身体'
          and health['特征解读'] == first['特征解读'])

    # 日期只改流年流月，不改手上读出的内容
    later = gr.build(copy.deepcopy(base), today=dt.date(2027, 3, 10), lib=lib)
    check('换日期只改流月不改特征解读', later['特征解读'] == first['特征解读']
          and [m['月'] for m in later['流月']][0] == '2027-03' and later['流月'] != first['流月'])

    # 变体：完整（事业线贯指）
    full = copy.deepcopy(base)
    f = feat(full, '事业线'); f['状态'] = '清楚'; f['属性']['上段'] = '贯指'
    c_full = gr.build(full, today=DAY, lib=lib)
    check('完整变体：事业线清楚贯指命中业04、不再命中业03', '业04' in hit_ids(c_full) and '业03' not in hit_ids(c_full)
          and '业04' not in hit_ids(first))
    check('完整变体：事业指数随之变化', score(c_full, '事业') != score(first, '事业'),
          f'{score(first, "事业")} → {score(c_full, "事业")}')

    # 变体：局部（感情线从清楚降为部分，权重 1.0 → 0.7）
    part = copy.deepcopy(base); feat(part, '感情线')['状态'] = '部分'
    c_part = gr.build(part, today=DAY, lib=lib)
    w = {r['编号']: r['权'] for r in c_part['依据']['命中']}
    check('局部变体：感情线规则权重降为 0.7 且感情分下降', w.get('感01') == 0.7 and score(c_part, '感情') < score(first, '感情'),
          f'{score(first, "感情")} → {score(c_part, "感情")}')

    # 变体：遮挡（感情线不清）→ 不下断，改用弱判断句
    hidden = copy.deepcopy(base); feat(hidden, '感情线')['状态'] = '不清'
    c_hidden = gr.build(hidden, today=DAY, lib=lib)
    sec = section(c_hidden, '感情线')
    check('遮挡变体：感情线不命中任何感字规则', not any(i.startswith('感') for i in hit_ids(c_hidden)))
    check('遮挡变体：感情线段落改为补拍提示', sec is not None and sec['解读'] == [lib['未见句']['不清']])

    # 变体：未见（三主宫位缺记录）→ 人生阶段走默认句
    unseen = copy.deepcopy(base)
    unseen['特征'] = [x for x in unseen['特征'] if x['id'] not in ('巽宫', '离宫', '坤宫')]
    c_unseen = gr.build(unseen, today=DAY, lib=lib)
    youth = c_unseen['人生阶段']['段'][0]
    check('未见变体：宫位缺记录时少年段不再引相三主、也不带三宫句', '相三主' not in youth['来源']
          and len(youth['断']) == 1 and c_unseen['人生阶段'] != first['人生阶段'])

    # 人生阶段：按掌纹年龄尺分段（近代流年：腕纹 1 岁、交智慧线 35、交感情线 50）
    st = first['人生阶段']
    sc = st['年龄尺']
    check('年龄尺量得出起势与线淡岁数，分段边界与之一致', sc is not None and 1 < sc['起'] < 35 < sc['止'] < 50
          and [x['段'] for x in st['段']] == [f'0—{sc["起"] - 1}', f'{sc["起"]}—34', f'35—{sc["止"]}', f'{sc["止"] + 1}—50', '51—'])
    stage_lines = [t for sg in st['段'] for t in sg['断']]
    check('人生阶段各段之间没有重复句，标题也不重复', len(stage_lines) == len(set(stage_lines))
          and len({sg['题'] for sg in st['段']}) == len(st['段']))
    check('人生阶段正文不重复标题、不出现初主中主末主宫名术语', all(not x.startswith(sg['题']) for sg in st['段'] for x in sg['断'])
          and not re.search(r'初主|中主（|末主（|巽宫|离宫|坤宫', '\n'.join(stage_lines + [sg['题'] for sg in st['段']])))
    check('每段都有一句「宜」且带具体岁数或动作', all(sg['宜'] for sg in st['段']))
    low = copy.deepcopy(base)
    feat(low, '事业线')['路径'][0][1] = 0.85
    c_low = gr.build(low, today=DAY, lib=lib)['人生阶段']
    check('事业线起点更靠腕：起势岁数变小、分段随之改', c_low['年龄尺']['起'] < sc['起'] and c_low['段'][0]['段'] != st['段'][0]['段'])
    through = copy.deepcopy(base)
    f = feat(through, '事业线'); f['状态'] = '清楚'; f['属性']['上段'] = '贯指'; f['路径'].append([0.500, 0.40])
    c_through = gr.build(through, today=DAY, lib=lib)['人生阶段']
    check('事业线越过感情线：35—50 岁改为一路贯通段、没有线淡段', any(x['类'] == '贯通' for x in c_through['段'])
          and not any(x['类'] == '自补' for x in c_through['段']))
    nocareer = copy.deepcopy(base); feat(nocareer, '事业线')['状态'] = '未见'
    c_nc = gr.build(nocareer, today=DAY, lib=lib)['人生阶段']
    check('事业线未见：量不出年龄尺，退回三主三段', c_nc['年龄尺'] is None and [x['类'] for x in c_nc['段']] == ['初主', '中主', '收成'])
    def late(li, kun):
        v = copy.deepcopy(base)
        feat(v, '离宫')['属性']['饱满'] = li; feat(v, '坤宫')['属性']['饱满'] = kun
        return gr.build(v, today=DAY, lib=lib)['人生阶段']['段'][-1]['题']
    T = lib['阶段模板']['收成']['题']
    check('五十岁后按离宫→坤宫高低给转运、稳稳收成、收着走三种断', late('平', '较满') == T['升']
          and late('平满', '平满') == T['平'] and late('较满', '缺') == T['降'])
    aged = copy.deepcopy(base); aged['用户自述'] = {'年龄': 38}
    c_aged = gr.build(aged, today=DAY, lib=lib)
    check('用户自述年龄只标「你在这里」，不改各段断语', [x['段'] for x in c_aged['人生阶段']['段'] if x['当前']] == [f'35—{sc["止"]}']
          and [x['断'] for x in c_aged['人生阶段']['段']] == [x['断'] for x in st['段']] and c_aged['特征解读'] == first['特征解读'])
    check('未见特征（婚姻线）给出补拍句而不是空白', section(first, '婚姻线')['解读'] == [lib['未见句']['未见']])

    # 变体：冲突（按旧判读，醒目斜纹不是感情线）→ 感情段落改写
    old = copy.deepcopy(base)
    feat(old, '感情线')['属性'] = {'长度': '中', '终点': '中指下', '走向': '掌上部浅弧', '交会': '分支多'}
    c_old = gr.build(old, today=DAY, lib=lib)
    check('冲突变体：按旧判读时感情线断语与感情分都改变', section(c_old, '感情线')['解读'] != section(first, '感情线')['解读']
          and score(c_old, '感情') != score(first, '感情'))
    check('冲突记录进入依据层', first['依据']['冲突'] == base.get('冲突', []) and len(first['依据']['冲突']) >= 1)

    # 首屏可辨度与时间锚点
    check('首屏写明看清几处与时间锚点', first['快速总结']['可辨']['总'] == len(base['特征'])
          and first['快速总结']['锚点'].startswith('以2026年11月3日为准') and '立冬（11月7日）起入亥月' in first['快速总结']['锚点'])
    blur = copy.deepcopy(base)
    for x in blur['特征']:
        x['状态'] = '不清'
    c_blur = gr.build(blur, today=DAY, lib=lib)
    check('看清不足三成时首句先请补拍', c_blur['快速总结']['一句话'].startswith('这张照片能看清的地方不到三成')
          and c_blur['快速总结']['可辨']['档'] == '补拍为先' and not c_blur['依据']['命中'] == first['依据']['命中'])

    # 反模板审计：禁语、空话、跨模块重复、流月首句重复、换手差异
    def texts(c):
        out = [c['快速总结']['一句话'], c['总结']] + [k['断'] for k in c['快速总结']['要点']]
        out += [t for sct in c['特征解读'] for t in sct['解读']] + [a['事'] for a in c['建议提醒']] + c['优势'] + c['潜力']
        out += [m['断'] for m in c['流月']] + [t for m in c['流月'] for t in m['补']]
        out += [t for sg in c['人生阶段']['段'] for t in sg['断']] + [t for a in c['关键关注'] for t in a['说']]
        return [t if isinstance(t, str) else json.dumps(t, ensure_ascii=False) for t in out]
    body = '\n'.join(texts(first))
    banned = re.findall(r'必然|命中注定|注定|血光|克夫|克妻|二婚|破产|寿限|短命|服药|绝症|癌', body)
    check('正文无禁语（注定、血光、克夫克妻、寿限、病名确诊等）', not banned, '、'.join(sorted(set(banned))))
    empty = re.findall(r'保持平衡|相信直觉|一切都会好|顺其自然|注意沟通', body)
    check('正文无空话词', not empty, '、'.join(sorted(set(empty))))
    sentences = {}
    for module, items in [('快速总结', [first['快速总结']['一句话']]), ('总结', [first['总结']]), ('建议', [a['事'] for a in first['建议提醒']]),
                          ('解读', [t for sct in first['特征解读'] for t in sct['解读']]), ('流月', [t for m in first['流月'] for t in m['补']])]:
        for t in items:
            for piece in re.split(r'[。；！]', t):
                if len(piece) >= 8:
                    sentences.setdefault(piece, set()).add(module)
    repeat = [k for k, v in sentences.items() if len(v) >= 3]
    check('同一句不在三个及以上模块重复', not repeat, '；'.join(repeat[:3]))
    from collections import Counter
    top = Counter(m['断'] for m in first['流月']).most_common(1)[0][1]
    check('流月主断同一句不超过两个月', top <= 2, f'最多重复 {top} 次')
    other = copy.deepcopy(base)
    for fid, attrs in [('掌形', {'长宽': '方', '厚薄': '薄', '纹理': '疏', '指掌比': '指长于掌'}), ('掌色', {'整体': '偏白', '分布': '均匀'}),
                       ('感情线', {'长度': '中', '交会': '分支多'}), ('事业线', {'起点': '腕上', '连续': '连贯', '上段': '贯指'}),
                       ('拇指', {'粗细': '细', '外张': '小'})]:
        feat(other, fid)['属性'] = attrs
    feat(other, '事业线')['状态'] = '清楚'
    c_other = gr.build(other, today=DAY, lib=lib)
    a_set, b_set = set(texts(first)), set(texts(c_other))
    overlap = len(a_set & b_set) / max(1, len(a_set | b_set))
    check('换一只手：签、一句话与正文都变', c_other['快速总结']['签'] != first['快速总结']['签']
          and c_other['快速总结']['一句话'] != first['快速总结']['一句话'] and overlap < 0.6, f'正文句重合率 {overlap:.2f}（阈值 0.6）')

    # schema 校验
    for name, mutate in [('schema_version 错误', lambda o: o.update(schema_version='旧版')),
                         ('特征 id 重复', lambda o: o['特征'].append(copy.deepcopy(o['特征'][0]))),
                         ('状态不在四态内', lambda o: o['特征'][0].update(状态='模糊'))]:
        bad = copy.deepcopy(base); mutate(bad)
        try:
            gr.build(bad, today=DAY, lib=lib); ok = False
        except gr.GuideError:
            ok = True
        check(f'非法输入被拒：{name}', ok)

    # 模块非空
    q = first['快速总结']
    check('快速总结：签、一句话、三条要点齐全', q['签'] and q['一句话'] and len(q['要点']) == 3 and all(x['断'] for x in q['要点']))
    check('指数分析：五项加综合，每项有理由', [x['项'] for x in first['指数']] == list(gr.INDEXES) + ['综合']
          and all(x['理由'] for x in first['指数']))
    check('指数档位：80 以上吉、60—79 平、60 以下慎', all(x['档'] == ('吉' if x['分'] >= 80 else '平' if x['分'] >= 60 else '慎') for x in first['指数'])
          and [gr.tier(s) for s in (45, 59, 60, 79, 80, 95)] == ['慎', '慎', '平', '平', '吉', '吉'])
    check('人生阶段：至少三段，每段有标题、断语和宜', len(first['人生阶段']['段']) >= 3 and all(s['题'] and s['断'] and s['宜'] for s in first['人生阶段']['段']))
    check('流年两张、流月六个月且每月有断与宜忌', len(first['流年']) == 2 and len(first['流月']) == 6
          and all(m['断'] and m['宜'] and m['忌'] for m in first['流月']))
    # 月令与流年表：覆盖范围内每天都能排满六个月和两张流年，超出范围报清楚的错
    rows, cover = lib['月令'], lib['覆盖']
    seq = [dt.date(int(m['月'][:4]), int(m['月'][5:]), 1) for m in rows]
    order = '子丑寅卯辰巳午未申酉戌亥'
    check('月令表逐月连续、月支按节序轮转、五行与月支一致',
          all((b.year * 12 + b.month) - (a.year * 12 + a.month) == 1 for a, b in zip(seq, seq[1:]))
          and all(m['支'] == order[(int(m['月'][5:]) % 12)] for m in rows)
          and all(m['五行'] == ('木' if m['支'] in '寅卯' else '火' if m['支'] in '巳午' else '金' if m['支'] in '申酉' else '水' if m['支'] in '亥子' else '土') for m in rows))
    stems, branches = '甲乙丙丁戊己庚辛壬癸', '子丑寅卯辰巳午未申酉戌亥'
    check('流年干支逐年连续，立春落在 2 月 3—5 日',
          all(v['干支'] == stems[(int(y) - 4) % 10] + branches[(int(y) - 4) % 12] and v['立春'][5:] in ('02-03', '02-04', '02-05') for y, v in lib['流年'].items()))
    edge = [gr.build(copy.deepcopy(base), today=dt.date.fromisoformat(d), lib=lib) for d in (cover['起'], cover['止'])]
    check('覆盖起止两端都排满六个月流月与两张流年', all(len(c['流月']) == 6 and len(c['流年']) == 2 for c in edge))
    try:
        gr.build(copy.deepcopy(base), today=dt.date.fromisoformat(cover['止']) + dt.timedelta(days=1), lib=lib); msg = ''
    except ValueError as e:
        msg = str(e)
    check('超出覆盖范围时报出范围而不是生成半份报告', cover['起'] in msg and cover['止'] in msg)
    check('关键关注至少三条且有月份', len(first['关键关注']) >= 3 and all(a.get('月') is not None for a in first['关键关注'][:3]))
    check('建议提醒三到七条', 3 <= len(first['建议提醒']) <= 7)
    check('优势、潜力、总结非空', first['优势'] and first['潜力'] and first['总结'])
    check('主要掌纹每条都有特征句或补拍句', all(s['解读'] for s in first['特征解读']))

    # HTML 分层与回放
    with tempfile.TemporaryDirectory() as directory:
        from PIL import Image
        photo = Path(directory) / '占位.png'
        Image.new('RGB', (base['照片']['宽'], base['照片']['高']), (200, 150, 130)).save(photo)
        out = guide_layout.write(first, photo, Path(directory) / '报告', base)
        page = (out / '掌中有话.html').read_text(encoding='utf-8')
        replay = json.loads((out / '回放.json').read_text(encoding='utf-8'))
        main, _, basis = page.partition('<details class="basis">')
        check('输出三个文件', sorted(p.name for p in out.iterdir()) == ['内容.json', '回放.json', '掌中有话.html'])
        check('正文不出现规则编号、schema 与方法说明', not re.search(r'[感智命业健形心色金月坎拇小指斗腕]0\d', main)
              and 'schema' not in main and '合参法' not in main and basis)
        check('正文含十个附件对应模块', all(t in main for t in ('快速总结', '指数分析', '关键关注点', '优势与潜力', '掌纹总览',
                                                               '流年', '人生阶段参考', '特征＋解读', '建议与提醒', '手型')))
        check('页面无 PDF 与消灾收费字样，正文不出现小红书（来源名只在依据层）', not any(w in page for w in ('PDF', '消灾', '化解费', '血光'))
              and '小红书' not in main)
        check('页面带娱乐与就医声明', '图一乐' in page and '就医' in page)
        check('页面画出掌上年龄尺且刻度齐全', 'class="ruler"' in main and all(t in main for t in ('1岁', f'{sc["起"]}岁 起势', '35岁 换道', '50岁 转运')))
        check('页面指数六项都带档位', main.count('class="ixt t-') == len(first['指数']))
        check('页面不引外部资源', not re.search(r'(src|href)="https?://', page))
        check('回放记录内容摘要与文件一致', replay['内容sha256'] == __import__('hashlib').sha256((out / '内容.json').read_bytes()).hexdigest())
        try:
            guide_layout.write(first, photo, out, base); ok = False
        except SystemExit:
            ok = True
        check('已存在的输出目录拒绝覆盖', ok)
        cli = subprocess.run([sys.executable, str(Path(__file__).with_name('palm.py')), '指南', '--输入', str(Path(obs_path).resolve() if obs_path else SAMPLE),
                              '--原照', str(photo), '--输出', str(Path(directory) / 'cli'), '--日期', '2026-11-03', '--问事', '破财'],
                             capture_output=True, text=True)
        cli_content = json.loads((Path(directory) / 'cli' / '内容.json').read_text(encoding='utf-8')) if cli.returncode == 0 else {}
        check('命令行入口可生成且与函数调用的特征解读一致', cli.returncode == 0 and cli_content.get('特征解读') == first['特征解读']
              and cli_content.get('主题') == '财运', cli.stderr[-300:] if cli.returncode else '')
    return {'通过数': sum(r['通过'] for r in checks), '总数': len(checks), '检查项': checks}


if __name__ == '__main__':
    result = run(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(result['通过数'] != result['总数'])
