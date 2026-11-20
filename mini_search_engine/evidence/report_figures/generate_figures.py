"""Generate report-sized SVG figures from the current corpus and measurements.

Run with Python's standard library. PNG copies in this folder are export assets.
"""
import csv
import math
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from corpus import load_documents
from search_engine import SearchEngine


def chart(rows, series, ylabel, filename, decimals=0, divisor=1):
    width, height = 1400, 560
    left, top, right, bottom = 115, 100, 35, 85
    xmax = width - right
    ymax = height - bottom
    data = [[float(row[key]) / divisor for key, _ in series] for row in rows]
    highest = max(max(row) for row in data)
    raw = highest * 1.25 / 4
    magnitude = 10 ** math.floor(math.log10(raw))
    step = math.ceil(raw / magnitude) * magnitude
    maximum = step * 4
    colors = ['#2563eb', '#0f766e', '#9a5517']
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<style>text{font:26px Arial,sans-serif;fill:#172554}</style>',
           f'<text x="{left}" y="30">{escape(ylabel)}</text>']
    for j, (_, label) in enumerate(series):
        x = left + j * 400
        svg += [f'<rect x="{x}" y="51" width="20" height="20" fill="{colors[j]}"/>',
                f'<text x="{x+30}" y="69">{escape(label)}</text>']
    for tick in range(5):
        value = tick * step
        y = ymax - value / maximum * (ymax - top)
        tick_text = f'{value:g}'
        svg += [f'<line x1="{left}" y1="{y}" x2="{xmax}" y2="{y}" stroke="#d9dfe7"/>',
                f'<text x="{left-15}" y="{y+8}" text-anchor="end">{tick_text}</text>']
    svg.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{ymax}" stroke="#334155"/>')
    group_width = (xmax - left) / len(rows)
    bar_width = group_width * .68 / len(series)
    for i, (row, values) in enumerate(zip(rows, data)):
        center = left + group_width * (i + .5)
        for j, value in enumerate(values):
            x = center - len(series)*bar_width/2 + j*bar_width
            h = value / maximum * (ymax-top)
            svg += [f'<rect x="{x}" y="{ymax-h}" width="{bar_width-8}" height="{h}" fill="{colors[j]}"/>',
                    f'<text x="{x+(bar_width-8)/2}" y="{ymax-h-12}" text-anchor="middle" style="font-size:22px">{value:.{decimals}f}</text>']
        svg.append(f'<text x="{center}" y="{ymax+40}" text-anchor="middle">{row["documents"]}</text>')
    svg.append(f'<text x="{(left+xmax)/2}" y="{height-12}" text-anchor="middle">Number of documents</text></svg>')
    (OUT / filename).write_text('\n'.join(svg), encoding='utf-8')


def branch(root, compressed, filename):
    # Follow the actual app prefix node, then retain its whole descendant subtree.
    node = root
    if compressed:
        offset = 0
        while offset < 3:
            label, node = node.edges['app'[offset]]
            assert 'app'.startswith(label, offset)
            offset += len(label)
        assert offset == 3
    else:
        for char in 'app':
            node = node.children[char]
    records = []
    children = {}
    def visit(current, parent, label, prefix, depth):
        index = len(records)
        records.append((current, parent, label, prefix, depth))
        children[index] = []
        if parent is not None:
            children[parent].append(index)
        items = current.edges.values() if compressed else current.children.items()
        for edge, child in sorted(items):
            visit(child, index, edge, prefix+edge, depth+1)
    visit(node, None, '', 'app', 0)
    positions = {}
    leaves = 0
    def place(index):
        nonlocal leaves
        ys = [place(i) for i in children[index]]
        if ys:
            y = (ys[0]+ys[-1])/2
        else:
            y = 75 + leaves*115
            leaves += 1
        positions[index] = (70 + records[index][4]*125, y)
        return y
    place(0)
    width = max(1100, max(x for x, _ in positions.values())+120)
    height = max(260, leaves*115+70)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<style>text{font:23px Arial,sans-serif;fill:#172554}</style>']
    for i,(current,parent,label,prefix,depth) in enumerate(records):
        x,y=positions[i]
        if parent is not None:
            px,py=positions[parent]
            svg += [f'<path d="M {px+29} {py} H {x-65} V {y} H {x-29}" fill="none" stroke="#94a3b8" stroke-width="2"/>',
                    f'<text x="{x-37}" y="{y-12}" text-anchor="end">{escape(label)}</text>']
        fill = '#dcfce7' if current.posting_index is not None else '#eef2f6'
        svg.append(f'<circle cx="{x}" cy="{y}" r="29" fill="{fill}" stroke="#334155" stroke-width="2"/>')
        text = str(current.posting_index) if current.posting_index is not None else ''
        svg.append(f'<text x="{x}" y="{y+8}" text-anchor="middle">{text}</text>')
        if current.posting_index is not None:
            svg.append(f'<text x="{x}" y="{y+53}" text-anchor="middle" style="font-size:21px">{escape(prefix)}</text>')
    svg.append('</svg>')
    (OUT/filename).write_text('\n'.join(svg),encoding='utf-8')


def main():
    rows = list(csv.DictReader((ROOT/'evidence/measurements.csv').open()))
    chart(rows,[('standard_nodes','Standard Trie'),('compressed_nodes','Compressed Trie')],
          'Trie nodes including the root','node_comparison.svg')
    chart(rows,[('standard_trie_bytes','Standard Trie'),('compressed_trie_bytes','Compressed Trie')],
          'Estimated reachable memory in KiB','memory_comparison.svg',decimals=1,divisor=1024)
    chart(rows,[('index_build_us','Inverted index'),('standard_build_us','Standard Trie'),('compressed_build_us','Compressed Trie')],
          'Construction time in microseconds per operation','construction_comparison.svg',decimals=1)
    chart(rows,[('standard_lookup_us','Standard lookup'),('compressed_lookup_us','Compressed lookup'),('single_search_us','Single keyword search')],
          'Lookup and retrieval time in microseconds per operation','lookup_comparison.svg',decimals=3)
    engine=SearchEngine(load_documents())
    branch(engine.standard.root,False,'standard_app_branch.svg')
    branch(engine.compressed.root,True,'compressed_app_branch.svg')

if __name__ == '__main__':
    main()
