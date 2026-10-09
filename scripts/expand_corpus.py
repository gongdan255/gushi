"""Build a reproducible full Tang/Song corpus and indexed SQLite search store."""
import concurrent.futures
import hashlib
import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
import jieba
from opencc import OpenCC

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
HEAD = json.loads((DATA / 'provenance.json').read_text(encoding='utf-8'))['commit']
BASE = f'https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/{HEAD}/'
CACHE = DATA / 'upstream' / HEAD
CACHE.mkdir(parents=True, exist_ok=True)
TREE = json.load(urllib.request.urlopen(f'https://api.github.com/repos/chinese-poetry/chinese-poetry/git/trees/{HEAD}?recursive=1'))
PREFIXES = ['全唐诗/poet.tang.', '全唐诗/poet.song.', '宋词/ci.song.']
FILES = sorted(x['path'] for x in TREE['tree'] if any(x['path'].startswith(p) for p in PREFIXES) and x['path'].endswith('.json'))

def download(name):
    target = CACHE / name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(4):
            try:
                raw = urllib.request.urlopen(BASE + urllib.parse.quote(name), timeout=60).read()
                json.loads(raw)
                target.write_bytes(raw)
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(attempt+1)
    return name

print(f'Downloading {len(FILES)} source files at {HEAD}', flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    for n, result in enumerate(pool.map(download, FILES), 1):
        if n % 30 == 0:
            print(f'Downloaded {n}/{len(FILES)}', flush=True)

cc = OpenCC('t2s')
temp = DATA / 'corpus.build.sqlite3'
if temp.exists():
    temp.unlink()
db = sqlite3.connect(temp)
db.executescript('''
PRAGMA journal_mode=OFF;
PRAGMA synchronous=OFF;
CREATE TABLE poems (id TEXT UNIQUE, title TEXT, author TEXT, dynasty TEXT, form TEXT,
 collection TEXT, text TEXT, normalized TEXT, themes TEXT, curated INTEGER, payload TEXT);
CREATE TABLE lines (line TEXT, poem_id TEXT);
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
''')
themes = {'思乡':['故乡','乡','故园','归心'],'送别':['送','别','离人'],'山水':['山','江','溪','湖'],'边塞':['塞','边','胡','征','烽'],'咏物':['咏','梅','竹','菊']}
motif_chars = '月山花酒春雨江风云雁雪梦'
words, authors, dynasties, forms, collections, motifs = (Counter() for _ in range(6))
stop = {'不知','何处','何人','何事','何时','不能','可以','不是','不见','一作','不可','不得'}
seen, author_cache = set(), {}
total = characters = duplicates = skipped = 0
raw_counts = Counter()

def add(p, curated=False):
    global total, characters, duplicates, skipped
    text = ''.join(p['paragraphs'])
    normalized = re.sub(r'[^\u4e00-\u9fff]', '', text)
    if not normalized:
        skipped += 1
        return
    id = hashlib.sha1(normalized.encode()).hexdigest()[:12]
    if id in seen:
        duplicates += 1
        return
    seen.add(id)
    p.update(id=id, text=text, motifs=[m for m in motif_chars if m in text],
             themes=[t for t, terms in themes.items() if any(w in p['title']+text for w in terms)])
    db.execute('INSERT INTO poems VALUES (?,?,?,?,?,?,?,?,?,?,?)',
               (id,p['title'],p['author'],p['dynasty'],p['form'],p['collection'],text,normalized,json.dumps(p['themes'],ensure_ascii=False),int(curated),json.dumps(p,ensure_ascii=False)))
    lines = {re.sub(r'[^\u4e00-\u9fff]', '', s) for s in re.split(r'[，。！？；、,!?;\n]',text)} - {''}
    db.executemany('INSERT INTO lines VALUES (?,?)', ((s,id) for s in lines))
    authors[p['author']] += 1
    dynasties[p['dynasty']] += 1
    forms[p['form']] += 1
    collections[p['collection']] += 1
    motifs.update(p['motifs'])
    words.update(w for w in jieba.cut(text) if len(w)>1 and re.fullmatch(r'[\u4e00-\u9fff]+',w) and w not in stop)
    characters += len(normalized)
    total += 1

# Preserve existing IDs, favourites and the lightweight curated quiz corpus.
for p in json.loads((DATA/'poems.json').read_text(encoding='utf-8')):
    add(p, True)
for index, file in enumerate(FILES, 1):
    collection, dynasty = ('宋词','宋') if file.startswith('宋词/') else (('全唐诗','唐') if '/poet.tang.' in file else ('全宋诗','宋'))
    items = json.loads((CACHE/file).read_text(encoding='utf-8'))
    raw_counts[collection] += len(items)
    # Convert a complete JSON file once; retain untouched source paragraphs separately.
    converted = json.loads(cc.convert(json.dumps(items,ensure_ascii=False)))
    for original, item in zip(items, converted):
        if not isinstance(item.get('paragraphs'),list) or not all(isinstance(s,str) for s in item['paragraphs']):
            skipped += 1
            continue
        paragraphs = [re.sub(r'[（(][^）)]*[）)]','',s).strip() for s in item['paragraphs']]
        add(dict(title=item.get('title') or item.get('rhythmic') or '无题',author=item.get('author') or '佚名',
                 dynasty=dynasty, form='词' if collection=='宋词' else '诗', paragraphs=paragraphs,
                 original=original['paragraphs'],collection=collection,source='https://github.com/chinese-poetry/chinese-poetry/blob/'+HEAD+'/'+file))
    if index % 10 == 0:
        db.commit()
        print(f'Indexed {index}/{len(FILES)} files; {total:,} unique poems',flush=True)

print('Building search and verse indexes…',flush=True)
db.executescript('''
CREATE INDEX poem_author ON poems(author);
CREATE INDEX poem_dynasty ON poems(dynasty);
CREATE INDEX poem_collection ON poems(collection);
CREATE INDEX line_lookup ON lines(line);
CREATE VIRTUAL TABLE search USING fts5(title,author,text,content='poems',content_rowid='rowid',tokenize='trigram');
INSERT INTO search(search) VALUES ('rebuild');
''')
provenance = dict(repository='https://github.com/chinese-poetry/chinese-poetry',commit=HEAD,files=FILES,
                 rawCounts=dict(raw_counts),curatedCount=527,count=total,duplicates=duplicates,skipped=skipped,
                 processing='OpenCC t2s; remove parenthetical notes; deduplicate normalized body, curated entries first; retain original paragraphs. Collection and dynasty follow upstream directories.')
stats = dict(total=total,authors=len(authors),characters=characters,dynasties=dict(dynasties),authorRanking=authors.most_common(8),
             words=words.most_common(35),motifs=[dict(name=m,count=motifs[m]) for m in motif_chars],forms=dict(forms),collections=dict(collections),
             filters=dict(authors=[a for a,_ in authors.most_common(200)],dynasties=sorted(dynasties),themes=list(themes),collections=list(collections)),
             provenance=provenance)
db.execute('INSERT INTO metadata VALUES (?,?)',('stats',json.dumps(stats,ensure_ascii=False)))
db.commit()
db.execute('ANALYZE')
db.close()
temp.replace(DATA/'corpus.sqlite3')
(DATA/'full_provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(total=total,rawCounts=dict(raw_counts),duplicates=duplicates,skipped=skipped),ensure_ascii=False),flush=True)
