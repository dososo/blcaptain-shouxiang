"""指南模式 HTML：只读内容对象与原照，不再自行判断内容。单文件、离线可读。"""
import base64
import html
import io
import json
from pathlib import Path

ESC = html.escape
CN_NUM = ['壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖', '拾', '拾壹', '拾贰']
TIER_CLASS = {'吉': 'ji', '平': 'ping', '慎': 'shen'}
LINE_COLOR = {'感情线': '#b23a2b', '智慧线': '#2f5f5c', '生命线': '#9c6b2e', '事业线': '#2a2420', '健康线': '#7a5c8a', '腕纹': '#6b5f55'}
LEVEL = {'吉': 'ji', '平': 'ping', '慎': 'shen'}


def photo_data(path, max_side=1400):
    """返回 (data URI, 原图宽, 原图高)。有 Pillow 时压成 JPEG；没有则原样内嵌。"""
    raw = Path(path).read_bytes()
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert('RGB')
        w, h = im.size
        scale = min(1, max_side / max(w, h))
        if scale < 1:
            im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, 'JPEG', quality=84, optimize=True)
        return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode(), w, h
    except ImportError:
        kind = 'png' if raw[:8] == b'\x89PNG\r\n\x1a\n' else 'jpeg'
        import struct
        if kind == 'png':
            w, h = struct.unpack('>II', raw[16:24])
        else:
            raise SystemExit('无 Pillow 时只支持 PNG 原照')
        return f'data:image/{kind};base64,' + base64.b64encode(raw).decode(), w, h


def _pts(path, W, H):
    return ' '.join(f'{x * W:.0f},{y * H:.0f}' for x, y in path)


def _anchor(sec, W, H):
    if sec.get('路径'):
        p = sec['路径'][len(sec['路径']) // 2]
        return p[0] * W, p[1] * H
    if sec.get('点'):
        return sec['点'][0] * W, sec['点'][1] * H
    if sec.get('区域'):
        return sec['区域'][0] * W, sec['区域'][1] * H
    return None


def view_box(content, W, H, pad=60):
    """总览只显示手部：取所有局部框与定位点的外接框，加边距。"""
    xs, ys = [], []
    for sec in content['特征解读']:
        if sec.get('局部'):
            xs += [sec['局部'][0], sec['局部'][2]]
            ys += [sec['局部'][1], sec['局部'][3]]
        a = _anchor(sec, W, H)
        if a:
            xs.append(a[0])
            ys.append(a[1])
    if not xs:
        return [0, 0, W, H]
    return [max(0, min(xs) - pad), max(0, min(ys) - pad), min(W, max(xs) + pad), min(H, max(ys) + pad)]


def candidates(sec, W, H):
    if sec.get('路径'):
        pts = sec['路径']
        return [(x * W, y * H) for x, y in pts[1:-1] or pts]
    a = _anchor(sec, W, H)
    return [a] if a else []


def place_marks(content, W, H):
    """贪心布置编号：每个特征取离已放编号最远的候选点，避免掌心叠号。"""
    placed, out = [], {}
    for i, sec in enumerate(content['特征解读'], 1):
        cs = candidates(sec, W, H)
        if not cs:
            continue
        best = max(cs, key=lambda c: min([((c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2) for p in placed] or [1e12]))
        placed.append(best)
        out[i] = best
    return relax(out, view_box(content, W, H))


def relax(spots, box, gap=0.08, rounds=80):
    """编号间距不足 gap×框宽时互相推开，留在框内。"""
    x0, y0, x1, y1 = box
    t = gap * (x1 - x0)
    pts = {k: list(v) for k, v in spots.items()}
    keys = sorted(pts)
    for _ in range(rounds):
        moved = False
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                pa, pb = pts[a], pts[b]
                dx, dy = pb[0] - pa[0], pb[1] - pa[1]
                d = (dx * dx + dy * dy) ** 0.5
                if d < t:
                    if d < 1e-6:
                        dx, dy, d = 1.0, 0.0, 1.0
                    push = (t - d) / 2 + 0.5
                    pa[0] -= dx / d * push
                    pa[1] -= dy / d * push
                    pb[0] += dx / d * push
                    pb[1] += dy / d * push
                    moved = True
        for p in pts.values():
            p[0] = min(max(p[0], x0 + t / 2), x1 - t / 2)
            p[1] = min(max(p[1], y0 + t / 2), y1 - t / 2)
        if not moved:
            break
    return {k: tuple(v) for k, v in pts.items()}


def overlay(content, W, H, box):
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    out = []
    marks = []
    spots = place_marks(content, W, H)
    for i, sec in enumerate(content['特征解读'], 1):
        color = LINE_COLOR.get(sec['id'], '#b23a2b')
        if sec.get('路径') and sec['状态'] != '未见':
            dash = '' if sec['状态'] == '清楚' else ' stroke-dasharray="18 10"'
            out.append(f'<g class="ln" data-k="{ESC(sec["id"])}"><polyline points="{_pts(sec["路径"], W, H)}" class="halo"/>'
                       f'<polyline points="{_pts(sec["路径"], W, H)}" stroke="{color}"{dash} class="stroke"/></g>')
        elif sec.get('区域'):
            x, y, r = sec['区域']
            out.append(f'<circle class="zone" cx="{x * W:.0f}" cy="{y * H:.0f}" r="{r * W:.0f}"/>')
        a = spots.get(i)
        if a:
            marks.append(f'<a class="mk{" mk-off" if sec["状态"] == "未见" else ""}" href="#f-{i}" data-k="{ESC(sec["id"])}" '
                         f'style="left:{(a[0] - x0) / bw * 100:.2f}%;top:{(a[1] - y0) / bh * 100:.2f}%">{i}</a>')
    svg = f'<svg class="ov" viewBox="{x0:.0f} {y0:.0f} {bw:.0f} {bh:.0f}" preserveAspectRatio="none" aria-hidden="true">{"".join(out)}</svg>'
    return svg, ''.join(marks)


def thumb(sec, W, H):
    box = sec.get('局部')
    if not box:
        a = _anchor(sec, W, H)
        if not a:
            return ''
        r = 170
        box = [max(0, a[0] - r), max(0, a[1] - r), min(W, a[0] + r), min(H, a[1] + r)]
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    size = f'{W / bw * 100:.2f}% auto'
    px = 0 if W == bw else x0 / (W - bw) * 100
    py = 0 if H == bh else y0 / (H - bh) * 100
    line = ''
    if sec.get('路径') and sec['状态'] != '未见':
        color = LINE_COLOR.get(sec['id'], '#b23a2b')
        line = (f'<svg viewBox="{x0} {y0} {bw} {bh}" preserveAspectRatio="none" aria-hidden="true">'
                f'<polyline points="{_pts(sec["路径"], W, H)}" class="halo"/><polyline points="{_pts(sec["路径"], W, H)}" stroke="{color}" class="stroke"/></svg>')
    return (f'<button class="th ph" type="button" aria-label="放大看{ESC(sec["id"])}" data-zoom="{x0},{y0},{x1},{y1}" '
            f'style="aspect-ratio:{bw}/{bh};background-size:{size};background-position:{px:.2f}% {py:.2f}%">{line}</button>')


def ruler(content, W, H):
    """掌上年龄尺：在原照上沿事业线标出岁数刻度；量不出年龄尺时不画。"""
    sc = content['人生阶段'].get('年龄尺')
    if not sc:
        return ''
    paths = {s['id']: s['路径'] for s in content['特征解读'] if s.get('路径')}
    ys = sc['锚点y']
    x = sc['x']
    x0, x1 = max(0, (x - 0.21) * W), min(W, (x + 0.21) * W)
    y0, y1 = max(0, (min(ys['感情线'], sc['止y']) - 0.05) * H), min(H, (ys['腕纹'] + 0.03) * H)
    bw, bh = x1 - x0, y1 - y0
    marks = [(ys['腕纹'], '1岁'), (sc['起y'], f'{sc["起"]}岁 起势'), (ys['智慧线'], '35岁 换道')]
    if sc['止'] < 50:
        marks.append((sc['止y'], f'{sc["止"]}岁 线淡'))
    marks.append((ys['感情线'], '50岁 转运'))
    lines = ''.join(f'<polyline points="{_pts(paths[k], W, H)}" stroke="{LINE_COLOR[k]}" class="faint"/>'
                    for k in ('智慧线', '感情线', '腕纹') if k in paths)
    lines += f'<polyline points="{_pts(paths["事业线"], W, H)}" class="halo"/><polyline points="{_pts(paths["事业线"], W, H)}" stroke="#b23a2b" class="stroke"/>'
    ticks = ''.join(f'<line x1="{(x - 0.035) * W:.0f}" x2="{(x + 0.035) * W:.0f}" y1="{y * H:.0f}" y2="{y * H:.0f}" class="tick"/>' for y, _ in marks)
    labels = ''.join(f'<span class="rl" style="left:{((x + 0.045) * W - x0) / bw * 100:.2f}%;top:{(y * H - y0) / bh * 100:.2f}%">{ESC(t)}</span>'
                     for y, t in marks)
    px = 0 if W == bw else x0 / (W - bw) * 100
    py = 0 if H == bh else y0 / (H - bh) * 100
    return (f'<figure class="ruler"><div class="rw ph" style="aspect-ratio:{bw:.0f}/{bh:.0f};background-size:{W / bw * 100:.2f}% auto;'
            f'background-position:{px:.2f}% {py:.2f}%"><svg viewBox="{x0:.0f} {y0:.0f} {bw:.0f} {bh:.0f}" preserveAspectRatio="none" aria-hidden="true">'
            f'{lines}{ticks}</svg>{labels}</div><figcaption>掌上年龄尺：沿你的事业线量出的岁数</figcaption></figure>')


def cond_text(cond):
    return '；'.join(k + '∈' + '/'.join(v) for k, v in cond.items())


def card(title, body, cls='', num=None):
    n = f'<span class="no">{CN_NUM[num - 1]}</span>' if num else ''
    return f'<section class="card {cls}"><h2>{n}{ESC(title)}</h2>{body}</section>'


def render(content, photo_path):
    uri, W, H = photo_data(photo_path)
    c = content
    q = c['快速总结']
    wx = c['基本']['五行']
    hand = c['基本']['手别']
    box = view_box(c, W, H)
    svg, marks = overlay(c, W, H, box)
    bw, bh = box[2] - box[0], box[3] - box[1]
    atlas_style = (f'aspect-ratio:{bw:.0f}/{bh:.0f};background-size:{W / bw * 100:.2f}% auto;'
                   f'background-position:{0 if W == bw else box[0] / (W - bw) * 100:.2f}% {0 if H == bh else box[1] / (H - bh) * 100:.2f}%')

    seen = q['可辨']
    quick = (f'<p class="sign">{ESC(q["签"])}</p><p class="anchor">照片看清 {seen["看清"]}/{seen["总"]} 处'
             + (f' · {ESC(seen["档"])}' if seen['档'] != '正常' else '') + f' · {ESC(q["锚点"])}</p>'
             f'<p class="lead">{ESC(q["一句话"])}</p>'
             '<ul class="keys">' + ''.join(f'<li><b>{ESC(k["题"])}</b><span>{ESC(k["断"])}</span></li>' for k in q['要点']) + '</ul>')

    idx_rows = []
    for it in c['指数']:
        why = ''.join(f'<li><em class="{"up" if r["加减"] >= 0 else "dn"}">{"+" if r["加减"] >= 0 else ""}{r["加减"]:g}</em>{ESC(r["因"])}</li>'
                      for r in it['理由'] if r['规则'] != '综合')
        idx_rows.append(f'<details class="ix{" ix-all" if it["项"] == "综合" else ""}"><summary><span class="ixn">{ESC(it["项"])}</span>'
                        f'<span class="bar"><i style="width:{it["分"]}%"></i></span><span class="ixv">{it["分"]}</span>'
                        f'<span class="ixt t-{TIER_CLASS[it["档"]]}">{ESC(it["档"])}</span></summary>'
                        + (f'<ul class="why">{why}</ul>' if why else '<p class="why">五项平均</p>') + '</details>')
    idx = '<p class="hint">点任一项看加减理由</p>' + ''.join(idx_rows)

    atlas = (f'<div class="atlas"><div class="frame ph" id="atlas" role="img" aria-label="原照与掌纹定位" style="{atlas_style}">{svg}{marks}</div>'
             '<div class="tools"><label><input type="checkbox" id="lines" checked> 显示掌纹线</label><button type="button" id="full">放大原照</button></div>'
             '<ol class="legend">' + ''.join(
                 f'<li><a href="#f-{i}"><span class="dot" style="background:{LINE_COLOR.get(s["id"], "#b23a2b")}"></span>{ESC(s["id"])}'
                 f'{"<small>未见</small>" if s["状态"] == "未见" else ""}</a></li>' for i, s in enumerate(c['特征解读'], 1)) + '</ol></div>')

    pct = ''.join(f'<li><span>{k}</span><span class="bar thin"><i style="width:{v}%"></i></span><b>{v}%</b></li>' for k, v in wx['占比'].items())
    tone = c['基本'].get('掌色应时')
    basic = (f'<dl class="kv"><dt>手别</dt><dd>{ESC(hand.get("值", "未确认"))}<small>（{ESC(hand.get("状态", ""))}）</small></dd>'
             f'<dt>手型</dt><dd>{ESC(wx["主"])}形为主，{ESC(wx["副"])}形为辅</dd><dt>性情</dt><dd>{ESC(wx["性情"])}</dd></dl>'
             f'<p class="sub">五行手型</p><ul class="wx">{pct}</ul>'
             + (f'<p class="note"><b>掌色应时</b>{ESC(tone["断"])}</p>' if tone else ''))

    feats = []
    for i, s in enumerate(c['特征解读'], 1):
        tag = '' if s['状态'] == '清楚' else f'<span class="st st-{ "off" if s["状态"] in ("未见", "不清") else "part"}">{ESC(s["状态"])}</span>'
        heads = '<p class="dd">' + '　'.join(f'「{ESC(x)}」' for x in s['短断']) + '</p>' if s['短断'] else ''
        tz = '<dl class="fx">'
        tz += f'<dt>特征</dt><dd>{ESC(s["所见"])}</dd>'
        tz += f'<dt>解读</dt><dd>' + ''.join(f'<p>{ESC(x)}</p>' for x in s['解读']) + '</dd></dl>'
        feats.append(f'<article class="feat" id="f-{i}" data-k="{ESC(s["id"])}">{thumb(s, W, H)}<div class="ft">'
                     f'<h3><span class="fn">{i}</span>{ESC(s["id"])}{tag}</h3>{heads}{tz}</div></article>')
    main_ids = {i for i, s in enumerate(c['特征解读'], 1) if s['类别'] in ('主纹', '副纹')}
    feat = '<div class="feats">' + ''.join(f for i, f in enumerate(feats, 1) if i in main_ids) + '</div>'
    body_feat = '<div class="feats band-grid">' + ''.join(f for i, f in enumerate(feats, 1) if i not in main_ids) + '</div>'

    st = c['人生阶段']
    stage = ruler(c, W, H) + '<ol class="tl">' + ''.join(
        f'<li{" class=now" if s.get("当前") else ""}><span class="age">{ESC(s["段"])}岁</span><div><b>{ESC(s["题"])}</b>'
        + ('<span class="here">你在这里</span>' if s.get('当前') else '')
        + ''.join(f'<p>{ESC(x)}</p>' for x in s['断'])
        + (f'<p class="yi"><em>宜</em>{ESC(s["宜"])}</p>' if s.get('宜') else '') + '</div></li>'
        for s in st['段']) + '</ol>'

    years = ''.join(f'<div class="yr"><span class="yn">{ESC(y["年"])}<small>{ESC(y["干支"])}</small></span><b>{ESC(y["标签"])}</b><p>{ESC(y["断"])}</p></div>'
                    for y in c['流年'])
    mons = ''.join(
        f'<div class="mo lv-{LEVEL[m["级"]]}"><div class="moh"><span class="mon">{int(m["月"][5:])}<small>月</small></span>'
        f'<span class="mot">{ESC(m["标签"])}</span></div><p class="mos">{ESC(m["节气"])} 起 · {ESC(m["支"])}月{ESC(m["五行"])}'
        + (f' · {ESC(m["神煞"])}' if m.get('神煞') else '') + f'</p><p>{ESC(m["断"].split("：", 1)[1])}</p>'
        + ''.join(f'<p class="mox">{ESC(x)}</p>' for x in m['补'])
        + f'<p class="yj"><span>宜</span>{ESC(m["宜"])}<span>忌</span>{ESC(m["忌"])}</p></div>'
        for m in c['流月'])
    first = c['流月'][0]['月'][:4] if c['流月'] else ''
    lucky = c.get('下一个转运点')
    luck = f'<p class="luck">下一个转运点：<b>{ESC(lucky["月"][:4])}年{int(lucky["月"][5:])}月 · {ESC(lucky["标签"])}</b></p>' if lucky else ''
    flow = f'<div class="yrs">{years}</div><p class="sub">未来半年 · 从 {ESC(first)} 年 {int(c["流月"][0]["月"][5:]) if c["流月"] else ""} 月起</p><div class="mos-grid">{mons}</div>{luck}'

    fc = c['关键关注']
    focus = ''
    for a in fc[:3]:
        when = '、'.join(f'{int(m[5:])}月' for m in a['月'][:3])
        focus += (f'<div class="fp"><span class="rank">{ESC(a["级"])}</span><div><b>{ESC(a["标签"])}</b>'
                  + (f'<em>{ESC(when)} 最要紧</em>' if when else '') + f'<p>{ESC(a["说"][0])}</p></div></div>')
    rest = [a['标签'] for a in fc[3:]]
    if rest:
        focus += f'<p class="also">其次留意：{ESC("、".join(rest))}</p>'

    adv = '<ul class="todo">' + ''.join(f'<li><span class="when">{ESC(a["时"])}</span>{ESC(a["事"])}</li>' for a in c['建议提醒']) + '</ul>'
    good = ('<p class="sub">优势</p><ul class="ticks">' + ''.join(f'<li><b>{ESC(s.split("：")[0])}</b>{ESC("：" + s.split("：", 1)[1] if "：" in s else "")}</li>' for s in c['优势'])
            + '</ul><p class="sub">潜力</p><ul class="ticks pot">' + ''.join(f'<li>{ESC(s)}</li>' for s in c['潜力']) + '</ul>')

    basis = c['依据']
    rows = ''.join(f'<tr><td>{ESC(h["编号"])}</td><td>{ESC(h["特征"])}</td><td>{ESC(cond_text(h["条件"]))}</td>'
                   f'<td>{h["权"]:g}</td><td>{ESC("、".join(basis["来源"][s]["出处"] + "（" + basis["来源"][s]["层级"] + "）" for s in h["来源"]))}</td></tr>' for h in basis['命中'])
    miss = ''.join(f'<li>{ESC(m["编号"])}：{ESC(m["原因"])}</li>' for m in basis['未命中'])
    srcs = ''.join(f'<li><b>{ESC(v["出处"])}</b>〔{ESC(v["层级"])}〕{ESC(v["核验"])}</li>' for v in basis['来源'].values())
    conf = ''.join(f'<li><b>{ESC(x["对象"])}</b>：本次判为{ESC(x["本次判读"])}；旧记录判为{ESC(x["旧判读"])}。{ESC(x["依据"])}{ESC(x["处理"])}</li>' for x in basis['冲突'])
    meth = ''.join(f'<li><b>{ESC(k)}</b>：{ESC(v)}</li>' for k, v in basis['方法'].items())
    lv = ''.join(f'<li><b>{ESC(k)}</b>：{ESC(v)}</li>' for k, v in basis['层级'].items())
    sc = c['人生阶段'].get('年龄尺')
    scale_html = ('<h4>掌上年龄尺的量法</h4><ul>'
                  f'<li>沿事业线所在竖线（原照横向 {sc["x"]:.3f}）取交点：腕纹 y={sc["锚点y"]["腕纹"]:.3f} 记 1 岁，智慧线 y={sc["锚点y"]["智慧线"]:.3f} 记 35 岁，感情线 y={sc["锚点y"]["感情线"]:.3f} 记 50 岁，其间线性换算。</li>'
                  f'<li>事业线最下端 y={sc["起y"]:.3f} → 约 {sc["起"]} 岁起势；最上端 y={sc["止y"]:.3f} → 约 {sc["止"]} 岁线淡。</li>'
                  '<li>锚点出自近代流年一派（两处独立来源），不是古籍；另一派从生命线量岁数，本版未用。</li></ul>') if sc else ''
    basis_html = (f'<details class="basis"><summary>依据与方法（给想深究的人）</summary>'
                  f'<h4>怎么算出来的</h4><ul>{meth}</ul><h4>本次命中的断语</h4><div class="tw"><table><thead><tr><th>编号</th><th>部位</th><th>条件</th><th>权重</th><th>出处</th></tr></thead><tbody>{rows}</tbody></table></div>'
                  + scale_html +
                  f'<h4>没有命中的断语</h4><ul>{miss}</ul><h4>判读冲突</h4><ul>{conf or "<li>无</li>"}</ul>'
                  f'<h4>出处层级</h4><ul>{lv}</ul><h4>资料来源</h4><ul>{srcs}</ul>'
                  f'<p class="meta">内容对象 {ESC(c["schema_version"])} · 断语库 {ESC(c["断语库版本"])} · 生成日期 {ESC(c["生成日期"])} · 问事：{ESC(c["问事"] or "全览")}</p></details>')

    title = f'{c["生成日期"][:4]}年{int(c["生成日期"][5:7])}月{int(c["生成日期"][8:])}日'
    body = f'''<header class="mast"><p class="kick">掌中有话 · 手相指南</p><h1>你的手相解读</h1>
<p class="dek">{ESC(title)} · {ESC(hand.get("值", ""))}（{ESC(hand.get("状态", ""))}） · 中国传统手相 · 娱乐解读</p></header>
<main class="grid">
<div class="col c1">
{card("快速总结", quick, "o-quick hero", 1)}
{card("指数分析", idx, "o-idx", 2)}
{card("关键关注点", focus, "o-focus", 3)}
{card("优势与潜力", good, "o-good", 4)}
{card("基本信息", basic, "o-basic", 5)}
</div>
<div class="col c2">
{card("掌纹总览 · 原照定位", atlas, "o-atlas", 6)}
{card("流年 · 流月", flow, "o-flow", 7)}
{card("人生阶段参考", stage, "o-stage", 8)}
</div>
<div class="col c3">
{card("主要掌纹 · 特征＋解读", feat, "o-feat", 9)}
{card("建议与提醒", adv, "o-adv", 10)}
</div>
{card("手型 · 手指 · 掌丘 · 掌色", body_feat, "o-body band", 11)}
</main>
<section class="close"><p class="kick">总结</p><p class="sum">{ESC(c["总结"])}</p>
<p class="remark">备注：本报告按中国传统手相与民间说法做娱乐解读，图一乐；身体相关的提醒只是生活建议，真有不适请就医。</p>
{basis_html}</section>
<div class="lb" id="lb" hidden><button type="button" class="x" aria-label="关闭">×</button><div class="lbi ph" id="lbi"></div></div>'''
    return PAGE.replace('{{URI}}', uri).replace('{{W}}', str(W)).replace('{{H}}', str(H)).replace('{{BODY}}', body)


PAGE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>掌中有话 · 手相指南</title>
<style>
:root{--paper:#f4efe5;--card:#fbf8f2;--line:#e2d8c5;--ink:#2a2420;--ink2:#6b5f55;--zhu:#b23a2b;--zhe:#9c7a3c;--qing:#2f5f5c;--ji:#2f6b5e;--shen:#b23a2b;--ping:#9c7a3c;
--serif:"Songti SC","STSong","Noto Serif CJK SC","Source Han Serif SC","Noto Serif SC",serif;--sans:"PingFang SC","Hiragino Sans GB","Noto Sans CJK SC","Microsoft YaHei",sans-serif}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.75 var(--sans);overflow-x:hidden}
.ph{background-image:url({{URI}});background-repeat:no-repeat}
.mast{max-width:1360px;margin:0 auto;padding:40px 24px 8px}
.kick{margin:0;font-size:12px;letter-spacing:.32em;color:var(--zhu)}
h1{font:600 40px/1.2 var(--serif);margin:8px 0 6px;letter-spacing:.06em}
.dek{margin:0;color:var(--ink2);font-size:13px}
.grid{max-width:1360px;margin:0 auto;padding:16px 24px;display:grid;grid-template-columns:minmax(300px,0.9fr) minmax(360px,1.15fr) minmax(360px,1.1fr);gap:16px;align-items:start}
.col{display:flex;flex-direction:column;gap:16px;min-width:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:20px 20px 18px;min-width:0}
.card h2{font:600 18px/1.3 var(--serif);margin:0 0 14px;display:flex;align-items:center;gap:10px;letter-spacing:.04em}
.no{display:inline-grid;place-items:center;min-width:24px;padding:0 3px;height:24px;border:1px solid var(--zhu);color:var(--zhu);font:13px/1 var(--serif);border-radius:2px}
.hero{border-top:3px solid var(--zhu)}
.sign{font:600 26px/1.35 var(--serif);margin:0 0 10px;color:var(--zhu);letter-spacing:.06em}
.anchor{margin:-4px 0 10px;font-size:13px;color:var(--ink2)}.lead{margin:0 0 14px;font-size:15px}
.keys{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.keys li{display:grid;grid-template-columns:44px 1fr;gap:8px;padding:10px 12px;background:#f3ece0;border-radius:3px}
.keys b{font:600 14px var(--serif);color:var(--zhu)}
.sub{margin:16px 0 8px;font:600 13px var(--serif);color:var(--ink2);letter-spacing:.1em}
.kv{display:grid;grid-template-columns:52px 1fr;gap:6px 10px;margin:0}.kv dt{color:var(--ink2)}.kv dd{margin:0}.kv small{color:var(--ink2)}
.wx{list-style:none;margin:0;padding:0;display:grid;gap:6px}.wx li{display:grid;grid-template-columns:20px 1fr 40px;align-items:center;gap:8px;font-family:var(--serif)}.wx b{font-weight:400;text-align:right;color:var(--ink2)}
.bar{display:block;height:8px;background:#ebe2d2;border-radius:4px;overflow:hidden}.bar i{display:block;height:100%;background:var(--zhu);border-radius:4px}.bar.thin{height:6px}.bar.thin i{background:var(--zhe)}
.note{margin:14px 0 0;padding:10px 12px;border-left:3px solid var(--zhe);background:#f3ece0;font-size:14px}.note b{display:block;font:600 13px var(--serif);color:var(--zhe)}
.hint{margin:-6px 0 10px;font-size:12px;color:var(--ink2)}
.ix{border-bottom:1px dashed var(--line)}.ix summary{display:grid;grid-template-columns:44px 1fr 36px 22px;align-items:center;gap:12px;padding:9px 0;cursor:pointer;list-style:none}.ix summary::-webkit-details-marker{display:none}
.ixn{font:600 14px var(--serif)}.ixv{font:600 20px var(--serif);text-align:right;color:var(--zhu)}.ix-all .bar i{background:var(--ink)}.ix-all .ixv{color:var(--ink)}
.ixt{display:inline-grid;place-items:center;width:22px;height:22px;border:1px solid currentColor;border-radius:2px;font:600 13px/1 var(--serif)}.t-ji{color:var(--ji)}.t-ping{color:var(--ping)}.t-shen{color:var(--shen)}
.why{list-style:none;margin:0 0 10px 56px;padding:0;font-size:13px;color:var(--ink2)}.why em{font-style:normal;display:inline-block;min-width:42px;font-family:var(--serif)}.why .up{color:var(--ji)}.why .dn{color:var(--shen)}
.atlas .frame{position:relative;width:100%;border-radius:3px;overflow:hidden;cursor:zoom-in}
.ov{position:absolute;inset:0;width:100%;height:100%}
.halo{fill:none;stroke:#fff;stroke-opacity:.75;stroke-width:16;stroke-linecap:round;stroke-linejoin:round}.stroke{fill:none;stroke-width:7;stroke-linecap:round;stroke-linejoin:round}
.zone{fill:#fff;fill-opacity:.12;stroke:#fff;stroke-opacity:.8;stroke-width:4;stroke-dasharray:14 10}
.nolines .ov{display:none}
.mk{position:absolute;transform:translate(-50%,-50%);width:24px;height:24px;border-radius:50%;background:var(--zhu);color:#fff;font:600 12px/24px var(--serif);text-align:center;text-decoration:none;box-shadow:0 0 0 2px #fff}
.mk-off{background:#8c8279}.mk.on,.ln.on .stroke{filter:brightness(1.15)}.ln.on .halo{stroke:#ffe9a8;stroke-opacity:1}
.tools{display:flex;justify-content:space-between;align-items:center;margin:10px 0;font-size:13px;color:var(--ink2)}
.tools button,.lb .x{font:inherit;border:1px solid var(--line);background:var(--card);border-radius:3px;padding:4px 10px;cursor:pointer;color:var(--ink)}
.legend{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(3,1fr);gap:4px 10px;font-size:13px;counter-reset:n}
.legend li{counter-increment:n}.legend a{color:var(--ink);text-decoration:none;display:flex;align-items:center;gap:6px}.legend a::before{content:counter(n);font:12px var(--serif);color:var(--ink2);min-width:14px}
.dot{width:10px;height:3px;border-radius:2px;flex:none}.legend small{color:var(--ink2);margin-left:2px}
.feats{display:flex;flex-direction:column;gap:0}
.feat{display:grid;grid-template-columns:96px 1fr;gap:14px;padding:16px 0;border-top:1px solid var(--line);scroll-margin-top:16px}.feat:first-child{border-top:0;padding-top:0}
.feat.flash{animation:fl 1.6s ease}@keyframes fl{0%{background:#f6e3c8}100%{background:transparent}}
.th{display:block;width:96px;border:1px solid var(--line);border-radius:3px;padding:0;cursor:zoom-in;position:relative;overflow:hidden;align-self:start;max-height:150px}
.th svg{position:absolute;inset:0;width:100%;height:100%}.th .halo{stroke-width:14}.th .stroke{stroke-width:7}
.feat h3{margin:0 0 4px;font:600 16px/1.4 var(--serif);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.fn{display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;background:var(--zhu);color:#fff;font:600 11px var(--serif)}
.st{font:12px var(--sans);padding:0 6px;border-radius:2px;border:1px solid}.st-part{color:var(--zhe);border-color:var(--zhe)}.st-off{color:var(--ink2);border-color:var(--line)}
.dd{margin:0 0 6px;font:600 14px var(--serif);color:var(--zhu)}
.fx{display:grid;grid-template-columns:34px 1fr;gap:4px 8px;margin:0;font-size:14px}.fx dt{font:600 12px/2.1 var(--serif);color:var(--ink2)}.fx dd{margin:0}.fx dd p{margin:0 0 6px}
.ruler{margin:0 auto 18px;max-width:280px}.rw{position:relative;border:1px solid var(--line);border-radius:3px;overflow:hidden}.rw svg{position:absolute;inset:0;width:100%;height:100%}.rw .faint{fill:none;stroke-width:5;opacity:.55}.rw .tick{stroke:#fff;stroke-width:9}.rl{position:absolute;transform:translateY(-50%);font:600 13px/1.2 var(--serif);color:#fff;background:rgba(42,36,32,.78);padding:2px 6px;border-radius:2px;white-space:nowrap}.ruler figcaption{font-size:13px;color:var(--ink2);text-align:center;margin-top:6px}.tl .yi{color:var(--ink2)}.tl .yi em{font-style:normal;color:var(--zhu);font-weight:600;margin-right:6px}.here{margin-left:8px;font-size:13px;color:#fff;background:var(--zhu);padding:1px 6px;border-radius:2px}.tl li.now b{color:var(--zhu)}.tl{list-style:none;margin:0;padding:0;position:relative}.tl::before{content:"";position:absolute;left:58px;top:6px;bottom:6px;width:1px;background:var(--line)}
.tl li{display:grid;grid-template-columns:52px 1fr;gap:18px;padding:0 0 14px;position:relative}.tl li::before{content:"";position:absolute;left:54px;top:8px;width:9px;height:9px;border-radius:50%;background:var(--zhu)}
.age{font:600 13px var(--serif);color:var(--ink2);text-align:right;padding-top:2px}.tl b{font:600 15px var(--serif)}.tl p{margin:2px 0 0;font-size:14px;color:var(--ink)}
.yrs{display:grid;grid-template-columns:1fr 1fr;gap:10px}.yr{padding:12px;background:#f3ece0;border-radius:3px}.yn{display:block;font:600 22px/1.2 var(--serif)}.yn small{font-size:13px;color:var(--ink2);margin-left:6px}.yr b{display:block;font:600 14px var(--serif);color:var(--zhu);margin:4px 0}.yr p{margin:0;font-size:13px}
.mos-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.mo{border:1px solid var(--line);border-top:3px solid var(--ping);border-radius:3px;padding:10px 12px;font-size:13px;background:#fdfbf7}.mo p{margin:4px 0 0}
.lv-ji{border-top-color:var(--ji)}.lv-shen{border-top-color:var(--shen)}
.moh{display:flex;align-items:baseline;justify-content:space-between}.mon{font:600 26px/1 var(--serif)}.mon small{font-size:13px;margin-left:2px}
.mot{font:600 14px var(--serif);color:var(--ping)}.lv-ji .mot{color:var(--ji)}.lv-shen .mot{color:var(--shen)}
.mos{color:var(--ink2);font-size:13px}.mox{color:var(--ink)}
.yj{color:var(--ink2)}.yj span{display:inline-block;font:600 11px/18px var(--serif);width:18px;text-align:center;border-radius:2px;color:#fff;background:var(--ji);margin:0 4px 0 0}.yj span+span{background:var(--shen);margin-left:8px}
.luck{margin:12px 0 0;padding:10px 12px;background:#e9efe9;border-radius:3px;font-size:14px}.luck b{font-family:var(--serif);color:var(--ji)}
.fp{display:grid;grid-template-columns:48px 1fr;gap:12px;padding:10px 0;border-bottom:1px dashed var(--line)}.fp:last-of-type{border-bottom:0}
.rank{font:600 13px/1 var(--serif);color:#fff;background:var(--zhu);border-radius:2px;padding:6px 0;text-align:center;align-self:start}
.fp b{font:600 16px var(--serif)}.fp em{font-style:normal;font-size:12px;color:var(--zhu);margin-left:8px}.fp p{margin:4px 0 0;font-size:14px}
.also{margin:10px 0 0;font-size:13px;color:var(--ink2)}
.todo{list-style:none;margin:0;padding:0}.todo li{display:grid;grid-template-columns:110px 1fr;gap:10px;padding:8px 0;border-bottom:1px dashed var(--line);font-size:14px}.todo li:last-child{border:0}
.when{font:600 13px var(--serif);color:var(--zhu)}
.ticks{list-style:none;margin:0;padding:0}.ticks li{padding:5px 0 5px 18px;position:relative;font-size:14px}.ticks li::before{content:"";position:absolute;left:2px;top:13px;width:7px;height:7px;border:1.5px solid var(--zhu);transform:rotate(45deg)}
.ticks b{font-family:var(--serif)}.pot li::before{border-color:var(--ji)}
.close{max-width:1360px;margin:0 auto;padding:8px 24px 48px}
.sum{font:600 20px/1.8 var(--serif);margin:8px 0 12px;max-width:920px}
.remark{font-size:12px;color:var(--ink2);margin:0 0 16px}
.basis{border-top:1px solid var(--line);padding-top:12px;font-size:13px;color:var(--ink2)}.basis summary{cursor:pointer;font:600 14px var(--serif);color:var(--ink)}
.basis h4{font:600 13px var(--serif);color:var(--ink);margin:16px 0 6px}.basis ul{margin:0;padding-left:18px}.tw{overflow-x:auto}
.basis table{border-collapse:collapse;width:100%;min-width:640px}.basis td,.basis th{border-bottom:1px solid var(--line);padding:5px 6px;text-align:left;vertical-align:top}.meta{margin-top:12px}
.lb{position:fixed;inset:0;background:rgba(30,26,22,.92);z-index:9;display:grid;place-items:center;padding:16px}.lb[hidden]{display:none}
.lbi{width:min(92vw,900px);max-height:88vh;background-size:100% 100%;border-radius:3px}.lb .x{position:absolute;top:12px;right:12px;font-size:20px;line-height:1;padding:6px 12px}
.band{grid-column:1/-1}.band-grid{display:grid;grid-template-columns:repeat(3,1fr);column-gap:28px}.band-grid .feat:nth-child(-n+3){border-top:0;padding-top:0}
@media (max-width:1180px){.grid{grid-template-columns:1fr 1fr}.c3{grid-column:1/-1}.band-grid{grid-template-columns:1fr 1fr}.band-grid .feat:nth-child(3){border-top:1px solid var(--line);padding-top:16px}}
@media (max-width:760px){
body{font-size:16px}.mast{padding:28px 16px 4px}h1{font-size:32px}
.grid{display:flex;flex-direction:column;align-items:stretch;padding:12px 16px;gap:12px}.col{display:contents}
.card{padding:16px}.o-quick{order:1}.o-idx{order:2}.o-focus{order:3}.o-atlas{order:4}.o-feat{order:5}.o-body{order:6}.o-flow{order:7}.o-stage{order:8}.o-adv{order:9}.o-good{order:10}.o-basic{order:11}
.band-grid{grid-template-columns:1fr}.band-grid .feat:nth-child(n+2){border-top:1px solid var(--line);padding-top:16px}.mk{width:20px;height:20px;font-size:11px;line-height:20px}
.feat{grid-template-columns:76px 1fr;gap:12px}.th{width:76px}
.mos-grid{grid-template-columns:1fr}.legend{grid-template-columns:repeat(2,1fr)}.todo li{grid-template-columns:1fr;gap:0}
.close{padding:4px 16px 40px}.sum{font-size:18px}.sign{font-size:23px}
}
@media print{.tools,.lb{display:none}}
</style></head><body>
{{BODY}}
<script>
(function(){
var W={{W}},H={{H}},atlas=document.getElementById('atlas'),lb=document.getElementById('lb'),lbi=document.getElementById('lbi');
document.getElementById('lines').addEventListener('change',function(e){atlas.classList.toggle('nolines',!e.target.checked)});
function zoom(b){var x0=b[0],y0=b[1],x1=b[2],y1=b[3],bw=x1-x0,bh=y1-y0;
lbi.style.aspectRatio=bw+'/'+bh;lbi.style.backgroundSize=(W/bw*100)+'% auto';
lbi.style.backgroundPosition=(W===bw?0:x0/(W-bw)*100)+'% '+(H===bh?0:y0/(H-bh)*100)+'%';lb.hidden=false}
document.getElementById('full').addEventListener('click',function(){zoom([0,0,W,H])});
atlas.addEventListener('click',function(e){if(e.target.closest('.mk'))return;zoom([0,0,W,H])});
document.querySelectorAll('.th').forEach(function(t){t.addEventListener('click',function(){zoom(t.dataset.zoom.split(',').map(Number))})});
lb.addEventListener('click',function(){lb.hidden=true});
document.addEventListener('keydown',function(e){if(e.key==='Escape')lb.hidden=true});
function mark(k,on){document.querySelectorAll('[data-k="'+k+'"]').forEach(function(n){if(n.classList.contains('mk')||n.classList.contains('ln'))n.classList.toggle('on',on)})}
document.querySelectorAll('.feat').forEach(function(f){f.addEventListener('mouseenter',function(){mark(f.dataset.k,true)});f.addEventListener('mouseleave',function(){mark(f.dataset.k,false)})});
document.querySelectorAll('a[href^="#f-"]').forEach(function(a){a.addEventListener('click',function(){var t=document.querySelector(a.getAttribute('href'));if(t){t.classList.remove('flash');void t.offsetWidth;t.classList.add('flash')}})});
})();
</script>
</body></html>'''


def write(content, photo, out_dir, observation):
    """输出目录须不存在；写 HTML、内容对象与回放记录（tmp-then-rename）。"""
    import hashlib
    import os
    out = Path(out_dir)
    if out.exists():
        raise SystemExit(f'输出目录已存在，不覆盖：{out}')
    if not out.parent.is_dir():
        raise SystemExit(f'输出目录的上级不存在：{out.parent}')
    tmp = out.with_name(out.name + '.tmp')
    if tmp.exists():
        raise SystemExit(f'临时目录已存在：{tmp}')
    tmp.mkdir()
    page = render(content, photo)
    (tmp / '掌中有话.html').write_text(page, encoding='utf-8')
    (tmp / '内容.json').write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    sha = lambda b: hashlib.sha256(b).hexdigest()
    replay = {'schema_version': '指南回放/1.0', '观察sha256': sha(json.dumps(observation, ensure_ascii=False, sort_keys=True).encode()),
              '原照sha256': sha(Path(photo).read_bytes()), '断语库版本': content['断语库版本'], '生成日期': content['生成日期'],
              '问事': content['问事'], '内容sha256': sha((tmp / '内容.json').read_bytes()), 'HTML sha256': sha(page.encode('utf-8'))}
    (tmp / '回放.json').write_text(json.dumps(replay, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.rename(tmp, out)
    return out
