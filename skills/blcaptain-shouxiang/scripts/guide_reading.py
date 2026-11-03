"""指南模式：观察记录 → 断语库条件命中 → 合参 → 单一内容对象。Python 3.10+，仅标准库。

同一观察、同一断语库版本、同一日期 → 内容对象逐字节一致；问事只改排序与重点，不改观察和断语。
"""
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'references' / '指南断语库.json'
OBS_SCHEMA = '指南观察/1.0'
OUT_SCHEMA = '指南内容/1.0'
STATES = ('清楚', '部分', '不清', '未见')
WEIGHT = {'清楚': 1.0, '部分': 0.7, '不清': 0.3, '未见': 0.0}
INDEXES = ('事业', '财运', '感情', '桃花', '健康')
INDEX_TIERS = ((80, '吉'), (60, '平'), (0, '慎'))
FOCUS = {'财运': ('财', '钱', '破财', '横财', '守财', '收入'), '感情': ('感情', '桃花', '婚', '恋', '对象', '伴侣'),
         '事业': ('事业', '工作', '升职', '跳槽', '创业'), '健康': ('健康', '身体', '病', '睡眠', '体检')}
YEAR_MOD = {'财': {'财运': 4}, '印': {'事业': 3, '健康': 2}, '官杀': {'事业': 2, '健康': -3},
            '比劫': {'财运': -3}, '食伤': {'桃花': 3, '财运': -1}}
FOCUS_MONTH = {'上火': '官杀', '睡眠': '官杀', '肠胃': '官杀', '透支': '官杀', '漏财': '比劫', '感情内耗': '桃花'}


class GuideError(ValueError):
    pass


def load_library(path=LIB):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def validate(obs):
    if obs.get('schema_version') != OBS_SCHEMA:
        raise GuideError(f'观察记录 schema_version 应为 {OBS_SCHEMA}')
    seen = set()
    for f in obs.get('特征', []):
        if f.get('id') in seen:
            raise GuideError(f'特征 id 重复：{f.get("id")}')
        seen.add(f.get('id'))
        if f.get('状态') not in STATES:
            raise GuideError(f'{f.get("id")} 状态须为 {"/".join(STATES)}')
    return {f['id']: f for f in obs.get('特征', [])}


def route(question):
    """问事 → 主题；无法识别时返回 None（默认全览）。"""
    if not question:
        return None
    for topic, words in FOCUS.items():
        if any(w in question for w in words):
            return topic
    return None


def relation(hand, month, lib):
    gen, ctl = lib['五行']['生'], lib['五行']['克']
    if month == hand:
        return '比劫'
    if gen[month] == hand:
        return '印'
    if gen[hand] == month:
        return '食伤'
    if ctl[hand] == month:
        return '财'
    return '官杀'


def match(lib, feats):
    hits, misses = [], []
    for rule in lib['规则']:
        f = feats.get(rule['特征'])
        cond = rule['条件']
        if not f:
            misses.append({'编号': rule['编号'], '原因': '本图无此特征记录'})
            continue
        if f['状态'] not in cond.get('状态', STATES):
            misses.append({'编号': rule['编号'], '原因': f'状态为{f["状态"]}'})
            continue
        bad = [k for k, allowed in cond.items() if k != '状态' and f.get('属性', {}).get(k) not in allowed]
        if bad:
            misses.append({'编号': rule['编号'], '原因': '条件不符：' + '、'.join(f'{k}={f.get("属性", {}).get(k, "未记")}' for k in bad)})
            continue
        hits.append({**rule, '权': WEIGHT[f['状态']]})
    return hits, misses


def five_elements(lib, feats):
    score = {k: 0 for k in '金木水火土'}
    used = []
    for w in lib['五行手型']['权重']:
        f = feats.get(w['特征'])
        if f and f['状态'] in ('清楚', '部分') and f.get('属性', {}).get(w['属性']) == w['值']:
            for k, v in w['五行'].items():
                score[k] += v
            used.append(f'{w["特征"]}·{w["值"]}')
    total = sum(score.values()) or 1
    order = sorted(score, key=lambda k: (-score[k], '土火金水木'.index(k)))
    pct = {k: round(score[k] * 100 / total) for k in order}
    main, second = order[0], order[1]
    return {'主': main, '副': second, '占比': pct, '签': lib['五行手型']['签'].get(main + second, f'{main}{second}相参'),
            '性情': lib['五行手型']['性情'][main], '依据特征': used}


def season(day, lib):
    bounds = lib['四季纹']['季界']
    md = day.strftime('%m-%d')
    cur = '冬'
    for name in ('春', '夏', '秋', '冬'):
        if md >= bounds[name]:
            cur = name
    return cur


def color_note(lib, feats, day):
    f = feats.get('掌色')
    if not f or f['状态'] not in ('清楚', '部分'):
        return None
    tone = f.get('属性', {}).get('整体', '')
    hue = '赤' if ('赤' in tone or '红' in tone) else '黄' if '黄' in tone else '白' if '白' in tone else '黑' if '黑' in tone else '青' if '青' in tone else None
    s = season(day, lib)
    tab = lib['四季纹']
    if hue and tab['应时'][s] == hue:
        return {'季': s, '色': hue, '判': '应时', '断': f'现在是{s}季，掌色偏{hue}正合时令：顺势而为，这一季做事有劲。', '原句': tab['原句'][0]}
    if hue and tab['逆时'][s] == hue:
        nxt = {'春': '立夏', '夏': '立秋', '秋': '立冬', '冬': '立春'}[s]
        return {'季': s, '色': hue, '判': '逆时', '断': f'{s}季掌色偏{hue}，按〈四季纹〉属逆时之色：{nxt}之前脾气急、易起口舌，大事缓一缓再拍板。', '原句': tab['原句'][1]}
    return None


def indexes(hits, rel_year, peach_year):
    acc = {k: [] for k in INDEXES}
    for r in hits:
        for k, v in r.get('指数', {}).items():
            acc[k].append((v * r['权'], r['短断'], r['编号']))
    for k, v in YEAR_MOD.get(rel_year, {}).items():
        acc[k].append((v, f'流年逢{rel_year}', '流年'))
    if peach_year:
        acc['桃花'].append((3, '流年逢桃花', '流年'))
    out = []
    for k in INDEXES:
        raw = sum(x[0] for x in acc[k])
        val = 60 + (35 * math.tanh(raw / 30) if raw >= 0 else 15 * math.tanh(raw / 12))
        val = max(45, min(95, round(val)))
        top = sorted(acc[k], key=lambda x: -abs(x[0]))[:3]
        out.append({'项': k, '分': val, '理由': [{'加减': round(x[0], 1), '因': x[1], '规则': x[2]} for x in top]})
    out.append({'项': '综合', '分': round(sum(x['分'] for x in out) / len(out)), '理由': [{'加减': 0, '因': '五项平均', '规则': '综合'}]})
    for x in out:
        x['档'] = tier(x['分'])
    return out


def tier(score):
    return next(name for floor, name in INDEX_TIERS if score >= floor)


def year_card(lib, hand, name, year):
    rels = []
    for el in year['五行']:
        r = relation(hand, el, lib)
        if r not in rels:
            rels.append(r)
    text = '；'.join(lib['十神'][r]['断'].split('：', 1)[1].rstrip('。') for r in rels) + '。'
    if len(rels) > 1:
        text = '两股气一起来：' + text
    return {'年': name, '干支': year['干支'], '十神': '＋'.join(rels), '标签': '＋'.join(lib['十神'][r]['标签'].replace('月', '年') for r in rels), '断': text}


def months(lib, hand, hits, start, count=6):
    tags = {t: s for s, ts in lib['地支神煞'].items() for t in ts}
    leak = [r['口子'] for r in hits if r.get('口子')]
    money = [r['短断'] for r in hits if r.get('主题') == '财运' and sum(r.get('指数', {}).values()) > 0]
    fire = any(r.get('关注', {}).get('标签') == '上火' for r in hits)
    love = [r['短断'] for r in hits if r.get('主题') in ('感情', '桃花')]
    organ = lib['五行']['脏腑']
    rows = [m for m in lib['月令'] if m['月'] >= start]
    out = []
    for m in rows[:count]:
        rel = relation(hand, m['五行'], lib)
        god = lib['十神'][rel]
        extra = []
        if rel == '财' and money:
            extra.append(f'你的财路：{money[0]}，这个月最见效。')
        if rel == '比劫':
            extra.append(f'你的漏财口子：{leak[0] if leak else "人情往来"}。朋友开口借钱，先问自己「收不回来行不行」。')
        if rel == '官杀':
            body = f'身体看{organ[hand]}和{organ[m["五行"]]}'
            extra.append(body + ('，叠加你本来火气旺，是这半年最该早睡的月份。' if fire else '，按时吃饭睡觉。'))
        sha = tags.get(m['支'])
        if sha:
            extra.append(lib['神煞断'][sha] + (f'你是「{love[0]}」的人，' + ('别把客气当暧昧。' if sha == '桃花' else '机会来了先接住。') if sha == '桃花' and love else ''))
        out.append({'月': m['月'], '节气': m['节气'], '支': m['支'], '五行': m['五行'], '十神': rel, '标签': god['标签'],
                    '级': god['级'], '断': god['断'], '补': extra, '宜': god['宜'], '忌': god['忌'], '神煞': sha})
    return out


def next_lucky(lib, hand, after):
    for m in lib['月令']:
        if m['月'] > after and relation(hand, m['五行'], lib) in ('印', '财'):
            return {'月': m['月'], '十神': relation(hand, m['五行'], lib), '标签': lib['十神'][relation(hand, m['五行'], lib)]['标签']}
    return None


def _cross_y(path, x):
    """折线在竖线 x 处的 y；够不着时取离 x 最近的端点。"""
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        if min(x1, x2) <= x <= max(x1, x2) and x1 != x2:
            return y1 + (x - x1) / (x2 - x1) * (y2 - y1)
    return min(path, key=lambda p: abs(p[0] - x))[1]


def age_scale(lib, feats):
    """近代流年：沿事业线所在竖线，腕纹 1 岁、交智慧线 35 岁、交感情线 50 岁，其间线性换算。缺线时返回 None。"""
    need = {k: feats.get(k) for k in ('事业线', '智慧线', '感情线', '腕纹')}
    if any(not f or f['状态'] not in ('清楚', '部分') or not f.get('路径') for f in need.values()):
        return None
    career = need['事业线']['路径']
    x = sum(p[0] for p in career) / len(career)
    anchor = lib['年龄尺']['锚点']
    ys = {k: _cross_y(need[k]['路径'], x) for k in anchor}
    pts = sorted(((ys[k], anchor[k]) for k in anchor), reverse=True)  # 由腕向指：y 递减、岁数递增
    if not pts[0][0] > pts[1][0] > pts[2][0]:
        return None

    def age(y):
        if y >= pts[0][0]:
            return pts[0][1]
        for (ya, aa), (yb, ab) in zip(pts, pts[1:]):
            if ya >= y >= yb:
                return aa + (ya - y) / (ya - yb) * (ab - aa)
        (ya, aa), (yb, ab) = pts[-2], pts[-1]
        return ab + (yb - y) / (ya - yb) * (ab - aa)

    top, bottom = min(p[1] for p in career), max(p[1] for p in career)
    return {'x': round(x, 4), '锚点y': {k: round(v, 4) for k, v in ys.items()},
            '起': max(1, round(age(bottom))), '止': round(age(top)), '起y': bottom, '止y': top}


def stages(lib, feats, hits, told_age=None):
    """人生阶段：能量出事业线年龄尺就按掌纹分段，否则退回〈相三主〉三段。每句只出现一次，正文不重复标题。"""
    gong = {g['宫']: g for g in lib['三主']['宫']}
    full = {}
    for name in ('巽宫', '离宫', '坤宫'):
        f = feats.get(name)
        if f and f['状态'] in ('清楚', '部分'):
            full[name] = f.get('属性', {}).get('饱满', '')
    palace = lambda name: gong[name]['口吻'].get(full.get(name, ''), '')
    tpl = lib['年龄尺'], lib['阶段模板']
    scale = age_scale(lib, feats)
    career = feats.get('事业线', {}).get('属性', {})
    hooks = [(lib['年龄尺']['钩子岁'][h['段']], h['断'], r['来源']) for r in hits for h in r.get('阶段', [])]

    def seg(lo, hi, kind, title, lines, advice, src, basis):
        return {'段': f'{lo}—{hi}' if hi else f'{lo}—', '起': lo, '止': hi, '类': kind, '题': title,
                '断': [t for t in lines if t], '宜': advice, '来源': sorted(set(src)), '据': basis}

    out = []
    if scale:
        S, E = scale['起'], scale['止']
        T = tpl[1]
        fmt = lambda s: s.replace('{S}', str(S)).replace('{E}', str(E))
        if S > 1:
            out.append(seg(0, S - 1, '打底', T['打底']['题'].get(full.get('巽宫', ''), T['打底']['题']['']), [fmt(T['打底']['断']), palace('巽宫')],
                           fmt(T['打底']['宜']), ['近代流年', '相三主'] if '巽宫' in full else ['近代流年'], f'事业线最下端在掌心，按年龄尺约 {S} 岁才起头'))
        lo = max(S, 1)
        if lo < 35:
            key = '掌心' if career.get('起点') == '掌心' else ''
            out.append(seg(lo, 34, '起势', fmt(T['起势']['题'][key]), [fmt(T['起势']['断'][key]), palace('离宫')],
                           fmt(T['起势']['宜']), ['近代流年', '相三主'] if '离宫' in full else ['近代流年'], f'事业线起点约 {S} 岁'))
        if E >= 50:
            out.append(seg(35, 50, '贯通', T['贯通']['题'], [T['贯通']['断']], T['贯通']['宜'], ['近代流年'], '事业线越过感情线'))
        else:
            key = '断续' if career.get('连续') == '断续' else ''
            out.append(seg(35, max(E, 35), '换道', T['换道']['题'][key], [T['换道']['断'][key]], T['换道']['宜'], ['近代流年'],
                           '事业线与智慧线交会处按年龄尺定为 35 岁'))
            out.append(seg(max(E, 35) + 1, 50, '自补', fmt(T['自补']['题']), [fmt(T['自补']['断'])], fmt(T['自补']['宜']), ['近代流年'],
                           f'事业线最上端约 {E} 岁，没到感情线（50 岁）'))
    else:
        out.append(seg(0, 25, '初主', T_title(lib, '巽宫', full), [palace('巽宫') or lib['阶段默认']['0—25']], '', ['相三主'] if '巽宫' in full else ['阶段默认'], '〈相三主〉巽宫'))
        out.append(seg(26, 50, '中主', T_title(lib, '离宫', full), [palace('离宫') or lib['阶段默认']['36—45']], '', ['相三主'] if '离宫' in full else ['阶段默认'], '〈相三主〉离宫'))
    rank = ['缺', '平', '平满', '较满']
    li, kun = full.get('离宫'), full.get('坤宫')
    way = ('升' if rank.index(kun) > rank.index(li) else '降' if rank.index(kun) < rank.index(li) else '平') if li in rank and kun in rank else '平'
    T = lib['阶段模板']['收成']
    out.append(seg(51, None, '收成', T['题'][way], [T['断'][way], palace('坤宫')], T['宜'].get(kun or '', T['宜']['']),
                   ['相三主'] if kun else ['阶段默认'], f'〈相三主〉离宫{li or "未记"}→坤宫{kun or "未记"}'))
    for at, text, src in hooks:
        s = next(x for x in out if x['起'] <= at and (x['止'] is None or at <= x['止']))
        s['断'].append(text if text.endswith(('。', '！', '？')) else text + '。')
        s['来源'] = sorted(set(s['来源']) | set(src))
    for s in out:
        s['当前'] = told_age is not None and s['起'] <= told_age and (s['止'] is None or told_age <= s['止'])
    return out, scale


def T_title(lib, name, full):
    g = next(g for g in lib['三主']['宫'] if g['宫'] == name)
    text = g['断'].get(full.get(name, ''), '')
    return text.split('：')[0] if '：' in text else g['名']


def focus_points(hits, month_rows, topic):
    agg = {}
    for r in hits:
        c = r.get('关注')
        if not c:
            continue
        a = agg.setdefault(c['标签'], {'标签': c['标签'], '分': 0, '规则': [], '说': [], '提醒': []})
        a['分'] += c['权重'] * r['权']
        a['规则'].append(r['编号'])
        a['说'].append(r['解读'])
        a['提醒'].extend(r.get('提醒', []))
    theme = {'上火': '健康', '睡眠': '健康', '肠胃': '健康', '透支': '健康', '久坐腰腿': '健康', '操心': '健康',
             '漏财': '财运', '感情内耗': '感情', '换赛道': '事业'}
    for a in agg.values():
        key = FOCUS_MONTH.get(a['标签'])
        a['月'] = [m['月'] for m in month_rows if key and (m['十神'] == key or m.get('神煞') == key)]
        a['主题'] = theme.get(a['标签'], '综合')
        a['分'] += 0.3 * sum(1 for m in month_rows if m['月'] in a['月'] and m['级'] == '慎')
        if topic and a['主题'] == topic:
            a['分'] += 10
    ranked = sorted(agg.values(), key=lambda a: (-a['分'], a['标签']))
    for i, a in enumerate(ranked):
        a['级'] = ('头号', '第二', '第三')[i] if i < 3 else '次要'
        a['分'] = round(a['分'], 2)
    return ranked


def advice(hits, focus, month_rows):
    items = []
    for a in focus[:3]:
        when = '、'.join(_cn_month(m) for m in a['月'][:2])
        for t in a['提醒'][:1]:
            items.append({'时': when or '这半年', '事': t, '因': a['标签']})
    lucky = {}
    for m in month_rows:
        if m['级'] == '吉':
            lucky.setdefault(f'{m["标签"]}，宜{m["宜"]}', []).append(_cn_month(m['月']))
    for text, when in lucky.items():
        items.append({'时': '、'.join(when), '事': text, '因': '流月'})
    seen, out = set(), []
    for r in hits:
        for t in r.get('提醒', []):
            if t not in {i['事'] for i in items}:
                items.append({'时': '平时', '事': t, '因': r['编号']})
    for i in items:
        if i['事'] not in seen:
            seen.add(i['事'])
            out.append(i)
    return out[:7]


_BASE = {'年': None}


def _cn_month(ym):
    y, m = ym.split('-')
    return f'{int(m)}月' if y == _BASE['年'] else f'{y}年{int(m)}月'


def sections(lib, feats, hits):
    by = {}
    for r in hits:
        by.setdefault(r['特征'], []).append(r)
    order = ['感情线', '智慧线', '生命线', '事业线', '健康线', '太阳线', '婚姻线', '掌形', '掌心', '掌色', '金星丘', '月丘', '坎宫',
             '拇指', '小指', '四指', '中指指腹', '腕纹']
    out = []
    for fid in order:
        f = feats.get(fid)
        if not f:
            continue
        rs = by.get(fid, [])
        item = {'id': fid, '类别': f['类别'], '状态': f['状态'], '所见': f['描述'],
                '特征': [r['特征句'] for r in rs], '短断': [r['短断'] for r in rs], '解读': [r['解读'] for r in rs],
                '规则': [r['编号'] for r in rs], '来源': sorted({s for r in rs for s in r['来源']}),
                '路径': f.get('路径'), '点': f.get('点'), '区域': f.get('区域'), '局部': f.get('局部')}
        if not rs:
            item['解读'] = [lib['未见句'].get(f['状态'] if f['状态'] in ('未见', '不清') else '无断', '这一处暂不下断。')]
        out.append(item)
    return out


def legibility(feats):
    """首屏的照片可辨度：清楚、部分算看清；不足三成时首句先请补拍。"""
    n = {k: sum(1 for f in feats.values() if f['状态'] == k) for k in STATES}
    total = len(feats) or 1
    clear = n['清楚'] + n['部分']
    return {**n, '总': len(feats), '看清': clear, '率': round(clear / total, 2),
            '档': '补拍为先' if clear / total < 0.3 else '部分解读' if clear / total < 0.7 else '正常'}


def anchor(day, month_rows):
    """首屏的时间锚点：以哪天为准，节气月从哪天起换。"""
    text = f'以{day.year}年{day.month}月{day.day}日为准'
    if month_rows:
        first = month_rows[0]
        term, md = first['节气'].split()
        mm, dd = (int(x) for x in md.split('/'))
        if first['月'] == day.strftime('%Y-%m') and (day.month, day.day) < (mm, dd):
            text += f'；{term}（{mm}月{dd}日）起入{first["支"]}月'
        else:
            text += f'；当前{first["支"]}月'
    return text


def summary(wx, strengths, good, bad, tense, lucky):
    parts = [f'{wx["签"]}：{wx["性情"]}的底子']
    if strengths:
        parts[0] += '，' + '、'.join(s.split('：')[0] for s in strengths[:3]) + '是你的本钱'
    plan = []
    if good:
        plan.append('、'.join(_cn_month(m['月']) for m in good) + '把钱收进来')
    if bad:
        plan.append('、'.join(_cn_month(m['月']) for m in bad) + '把钱守住')
    if tense:
        plan.append('、'.join(_cn_month(m['月']) for m in tense) + '把身体顾好')
    text = parts[0] + '。'
    if plan:
        text += '接下来半年：' + '，'.join(plan) + '。'
    if lucky:
        text += f'熬过这一段，{_cn_month(lucky["月"])}{lucky["标签"]}到。'
    return text


def build(obs, question=None, today=None, lib=None):
    lib = lib or load_library()
    feats = validate(obs)
    day = today or dt.date.today()
    cover = lib['覆盖']
    if not cover['起'] <= day.isoformat() <= cover['止']:
        raise ValueError(f'日期 {day.isoformat()} 超出断语库流年月令表的范围（{cover["起"]} 至 {cover["止"]}），请换一个范围内的日期或更新断语库')
    _BASE['年'] = str(day.year)
    topic = route(question)
    hits, misses = match(lib, feats)
    wx = five_elements(lib, feats)
    year = lib['流年'][str(day.year)]
    rel_year = relation(wx['主'], year.get('主五行', year['五行']), lib)
    start = day.strftime('%Y-%m')
    month_rows = months(lib, wx['主'], hits, start)
    focus = focus_points(hits, month_rows, topic)
    idx = indexes(hits, rel_year, year['干支'][1] in lib['地支神煞']['桃花'])
    nxt_year = lib['流年'].get(str(day.year + 1))
    years = [year_card(lib, wx['主'], str(day.year), year)]
    if nxt_year:
        years.append(year_card(lib, wx['主'], str(day.year + 1), nxt_year))
    strengths = [s for r in sorted(hits, key=lambda r: -sum(max(v, 0) for v in r.get('指数', {}).values())) for s in r.get('优势', [])]
    potential = [s for r in hits for s in r.get('潜力', [])]
    good = [m for m in month_rows if m['级'] == '吉']
    bad = [m for m in month_rows if m['标签'] == '破财月']
    tense = [m for m in month_rows if m['标签'] == '压力月']
    peach = [m for m in month_rows if m.get('神煞') == '桃花']
    lead = sorted(hits, key=lambda r: -abs(sum(r.get('指数', {}).values())) * r['权'])[:3]
    seen = legibility(feats)
    one = f'{wx["主"]}为主、{wx["副"]}为辅的手：{wx["性情"]}。' + '；'.join(r['短断'] for r in lead) + '。'
    if seen['率'] < 0.3:
        one = '这张照片能看清的地方不到三成，最好按提示补拍一张；下面只是粗看。' + one
    quick = {
        '签': wx['签'],
        '一句话': one,
        '可辨': seen,
        '锚点': anchor(day, month_rows),
        '要点': [
            {'题': '财运', '断': ('进财看' + '、'.join(_cn_month(m['月']) for m in good if m['十神'] == '财') if any(m['十神'] == '财' for m in good) else '这半年没有明显进财月，以守为主')
             + ('；破财防' + '、'.join(_cn_month(m['月']) for m in bad) if bad else '') + '。'},
            {'题': '身体', '断': (focus[0]['标签'] if focus and focus[0]['主题'] == '健康' else next((a['标签'] for a in focus if a['主题'] == '健康'), '作息'))
             + '是头号功课' + ('，' + '、'.join(_cn_month(m['月']) for m in tense) + '最要紧' if tense else '') + '。'},
            {'题': '感情', '断': (next((r['短断'] for r in hits if r['主题'] == '感情'), '感情线未看清'))
             + ('；桃花在' + '、'.join(_cn_month(m['月']) for m in peach) if peach else '') + '。'},
        ],
    }
    if topic:
        quick['要点'].sort(key=lambda q: 0 if q['题'] == {'财运': '财运', '健康': '身体', '感情': '感情'}.get(topic) else 1)
    lucky = next_lucky(lib, wx['主'], month_rows[-1]['月']) if month_rows else None
    told = obs.get('用户自述', {}).get('年龄')
    told_age = told if isinstance(told, int) and 0 < told < 120 else None
    stage_rows, scale = stages(lib, feats, hits, told_age)
    content = {
        'schema_version': OUT_SCHEMA,
        '断语库版本': lib['版本'],
        '生成日期': day.isoformat(),
        '问事': question or '',
        '主题': topic or '全览',
        '基本': {'手别': obs.get('基本', {}).get('手别', {}), '拍摄': obs.get('基本', {}).get('拍摄', ''),
                 '五行': wx, '掌色应时': color_note(lib, feats, day)},
        '快速总结': quick,
        '指数': idx,
        '特征解读': sections(lib, feats, hits),
        '人生阶段': {'三主原句': lib['三主']['原句'], '段': stage_rows, '年龄尺': scale, '自述年龄': told_age},
        '流年': years,
        '流月': month_rows,
        '下一个转运点': lucky,
        '关键关注': focus,
        '建议提醒': advice(hits, focus, month_rows),
        '优势': strengths,
        '潜力': potential,
        '总结': summary(wx, strengths, good, bad, tense, lucky),
        '依据': {
            '命中': [{'编号': r['编号'], '特征': r['特征'], '条件': r['条件'], '权': r['权'], '来源': r['来源']} for r in hits],
            '未命中': misses,
            '来源': lib['来源'],
            '层级': lib['层级'],
            '冲突': obs.get('冲突', []),
            '方法': {
                '指数': '每项从 60 起算；命中规则的加减 × 观察权重（清楚 1.0、部分 0.7）；再加流年十神修正；限定在 45—95。80 分及以上标「吉」，60—79 标「平」，60 以下标「慎」。',
                '五行手型': lib['五行手型']['说明'],
                '流月': '以手型主五行为「我」，按节气月令地支五行定生克十神（生我印、我克财、克我官杀、同我比劫、我生食伤），再叠加地支桃花、驿马、库；属本项目合参法。',
                '人生阶段': lib['年龄尺']['说明'] + '五十岁后按〈相三主〉离宫与坤宫饱满度高低定转运方向（缺＜平＜平满＜较满）。事业线、智慧线、感情线、腕纹任一缺失或看不清时，退回〈相三主〉巽、离、坤三段。',
            },
        },
    }
    return content


def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
