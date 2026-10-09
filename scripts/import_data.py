"""Download a pinned, attributed corpus. Run once; the app works offline afterwards."""
import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from opencc import OpenCC

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
cc = OpenCC('t2s')
HEAD = json.load(urllib.request.urlopen('https://api.github.com/repos/chinese-poetry/chinese-poetry/commits/master'))['sha']
BASE = f'https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/{HEAD}/'

def fetch(path):
    return urllib.request.urlopen(BASE + urllib.parse.quote(path), timeout=60).read()

records, seen = [], set()
sources = ['蒙学/tangshisanbaishou.json', '蒙学/qianjiashi.json']
for source in sources:
    raw = fetch(source)
    (DATA / Path(source).name).write_bytes(raw)
    book = json.loads(raw)
    for group in book['content']:
        expanded = []
        for entry in group['content']:
            if entry['paragraphs'] and isinstance(entry['paragraphs'][0], dict):
                for part in entry['paragraphs']:
                    expanded.append({**entry, 'chapter': entry['chapter'] + '·' + part['subchapter'], 'paragraphs': part['paragraphs']})
            else:
                expanded.append(entry)
        group['content'] = expanded
        for p in group['content']:
            author = cc.convert(p['author'])
            m = re.match(r'[（(](.*?)[）)](.*)', author)
            dynasty, author = (m[1], m[2]) if m else ('唐', author)
            original = p['paragraphs']
            paragraphs = [re.sub(r'[（(][^）)]*[）)]', '', cc.convert(x)).strip() for x in original]
            key = re.sub(r'[^\u4e00-\u9fff]', '', ''.join(paragraphs))
            if not key or key in seen:
                continue
            seen.add(key)
            records.append(dict(id=hashlib.sha1(key.encode()).hexdigest()[:12], title=cc.convert(p['chapter']),
                                author=author, dynasty=dynasty, form=cc.convert(group['type']),
                                paragraphs=paragraphs, original=original, collection=cc.convert(book['title']),
                                source='https://github.com/chinese-poetry/chinese-poetry/blob/'+HEAD+'/'+source))
(DATA / 'poems.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
(DATA / 'SOURCE_LICENSE.txt').write_bytes(fetch('LICENSE'))
(DATA / 'provenance.json').write_text(json.dumps({'repository': 'https://github.com/chinese-poetry/chinese-poetry', 'commit': HEAD, 'files': sources, 'count': len(records), 'processing': 'OpenCC t2s; remove parenthetical variant notes from analysis text; deduplicate by normalized body; retain source paragraphs.'}, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Imported {len(records)} poems, commit {HEAD}')
