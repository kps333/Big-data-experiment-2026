# -*- coding: utf-8 -*-
"""把 pptx 的全部文字按页导出成 txt。只用标准库，不需要 python-pptx。

用法（在项目根目录）：
    python scripts/dump_pptx.py
    python scripts/dump_pptx.py slides/naive-bayes-experiment-intro.pptx slides/_extract.txt

输出格式每页以 `### 第 N 页` 开头，页内每个段落一行。
"""
import sys
import re
import html
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def slide_files_in_order(z):
    """按 presentation.xml 的 sldIdLst 排序；失败则退回文件名数字序。"""
    names = [n for n in z.namelist()
             if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)]
    order = {}
    try:
        rels = z.read('ppt/_rels/presentation.xml.rels').decode('utf-8', 'ignore')
        rid2target = dict(re.findall(r'Id="(rId\d+)"[^>]*?Target="([^"]+)"', rels))
        pres = z.read('ppt/presentation.xml').decode('utf-8', 'ignore')
        rids = re.findall(r'<p:sldId[^>]*?r:id="(rId\d+)"', pres)
        for i, rid in enumerate(rids, 1):
            target = rid2target.get(rid, '')
            path = 'ppt/' + target.lstrip('/').replace('ppt/', '', 1)
            order[path] = i
    except Exception:
        order = {}

    def key(name):
        if name in order:
            return order[name]
        m = re.search(r'(\d+)', name)
        return int(m.group(1)) + 1000 if m else 10 ** 6

    return sorted(names, key=key)


def paragraphs(xml):
    """抽出 <a:p> 段落里的文字，<a:br/> 当换行。表格单元格同样适用。"""
    out = []
    for p in re.findall(r'<a:p(?:\s[^>]*)?>.*?</a:p>', xml, re.S):
        buf = []
        for tok in re.findall(r'<a:br\s*/?>|<a:t[^>]*>.*?</a:t>', p, re.S):
            if tok.startswith('<a:br'):
                buf.append('\n')
            else:
                buf.append(html.unescape(re.sub(r'<[^>]+>', '', tok)))
        text = ''.join(buf).strip()
        if text:
            out.append(text)
    return out


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        BASE / 'slides' / 'naive-bayes-experiment-intro.pptx'
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name('_extract.txt')

    if not src.exists():
        print(f'找不到文件: {src}')
        return 1

    blocks, stats = [], []
    with zipfile.ZipFile(src) as z:
        names = slide_files_in_order(z)
        for i, name in enumerate(names, 1):
            paras = paragraphs(z.read(name).decode('utf-8', 'ignore'))
            body = '\n'.join(paras) if paras else '（本页无可提取文字）'
            blocks.append(f'### 第 {i} 页\n{body}')
            stats.append((i, len(paras)))

    text = '\n\n'.join(blocks) + '\n'
    dst.write_text(text, encoding='utf-8')
    print(f'写好 {dst}')
    print(f'共 {len(stats)} 页，{len(text)} 字符')
    for i, n in stats:
        print(f'  第 {i:>2} 页：{n} 段')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())