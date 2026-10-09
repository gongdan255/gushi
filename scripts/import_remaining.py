"""Import remaining content collections, preserving duplicate source membership."""
import concurrent.futures
import hashlib
import json
import re
import sqlite3
import time
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
import jieba
from opencc import OpenCC

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'data'
HEAD = json.loads((DATA/'provenance.json').read_text(encoding='utf-8'))['commit']
CACHE = DATA/'upstream'/HEAD
TREE = json.loads((DATA/'tree.json').read_text(encoding='utf-8'))
FILES = sorted(x['path'] for x in TREE['tree'] if x['path'].endswith('.json') and not x['path'].startswith(('全唐诗/','宋词/','rank/','strains/','loader/')))
SUPPLEMENTS=['全唐诗/唐诗补录.json','全唐诗/唐诗三百首.json','宋词/宋词三百首.json']
FILES=SUPPLEMENTS if '--supplement' in sys.argv else sorted(set(FILES+SUPPLEMENTS))
cc = OpenCC('t2s')

def download(name):
    file = CACHE/name
    if not file.exists():
        file.parent.mkdir(parents=True,exist_ok=True)
        for attempt in range(4):
            try:
                raw = urllib.request.urlopen('https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/'+HEAD+'/'+urllib.parse.quote(name),timeout=60).read()
                json.loads(raw)
                file.write_bytes(raw)
                break
            except Exception:
                if attempt==3: raise
                time.sleep(attempt+1)
    return name

BOOKS = {'daxue':'大学','mengzi':'孟子','zhongyong':'中庸','baijiaxing':'百家姓','dizigui':'弟子规','guwenguanzhi':'古文观止','qianjiashi':'千家诗','qianziwen':'千字文','sanzijing-new':'三字经（新版）','sanzijing-traditional':'三字经（传统版）','shenglvqimeng':'声律启蒙','tangshisanbaishou':'唐诗三百首','wenzimengqiu':'文字蒙求','youxueqionglin':'幼学琼林','zengguangxianwen':'增广贤文','zhuzijiaxun':'朱子家训'}

def specification(path):
    if path=='全唐诗/唐诗补录.json':return '唐诗补录','唐','诗','诗词曲','佚名'
    if path=='全唐诗/唐诗三百首.json':return '唐诗三百首','唐','诗','诗词曲','佚名'
    if path=='宋词/宋词三百首.json':return '宋词三百首','宋','词','诗词曲','佚名'
    if path.startswith('御定全唐詩/'): return '御定全唐诗','唐','诗','诗词曲','佚名'
    if '/huajianji/' in path: return '花间集','唐·五代','词','诗词曲','佚名'
    if '/nantang/' in path: return '南唐二主词','五代','词','诗词曲','佚名'
    group=path.split('/')[0]
    if group=='元曲':return '元曲','元','曲','诗词曲','佚名'
    if group=='诗经':return '诗经','先秦','诗','诗词曲','佚名'
    if group=='楚辞':return '楚辞','先秦·汉','楚辞','诗词曲','佚名'
    if group=='曹操诗集':return group,'汉末','诗','诗词曲','曹操'
    if group=='纳兰性德':return '纳兰性德诗集','清','诗词','诗词曲','纳兰性德'
    if group=='水墨唐诗':return group,'唐','诗','诗词曲','佚名'
    if group=='幽梦影':return group,'清','随笔','古文典籍','张潮'
    if group=='论语':return group,'先秦','典籍','古文典籍','孔子及弟子（编纂）'
    name=BOOKS[Path(path).stem]
    if group=='四书五经':return name,'先秦','典籍','古文典籍','编者未标注'
    if name in ('唐诗三百首','千家诗'):return name,'唐' if name=='唐诗三百首' else '未详','诗','诗词曲','佚名'
    return name,'未详','古文' if name=='古文观止' else '蒙学','古文典籍','编者未标注'

def leaves(node, inherited=None, trail=()):
    """Walk only content-bearing keys. Never import notes as original verse."""
    inherited=inherited or {}
    if isinstance(node,list):
        for i,item in enumerate(node):
            yield from leaves(item,inherited,trail+(str(i+1),))
        return
    if not isinstance(node,dict):raise ValueError(f'Unsupported node at {trail}')
    metadata={**inherited,**{k:node[k] for k in ['author','dynasty','type'] if isinstance(node.get(k),str)}}
    title=node.get('title') or node.get('chapter') or node.get('subchapter') or node.get('rhythmic')
    route=trail+((title,) if title else ())
    for key in ['paragraphs','para','content']:
        value=node.get(key)
        if value == []:
            yield {**metadata,'title':title or '无题','paragraphs':[],'sectionPath':list(route),'extra':{}}
            return
        if isinstance(value,str):
            yield {**metadata,'title':title or f'第{trail[-1] if trail else 1}则','paragraphs':[value],'sectionPath':list(route),'extra':{k:v for k,v in node.items() if k in ['notes','comment','section','chapter','tags','prologue']}}
            return
        if isinstance(value,list) and value:
            if all(isinstance(s,str) for s in value):
                yield {**metadata,'title':title or f'第{trail[-1] if trail else 1}章','paragraphs':value,'sectionPath':list(route),'extra':{k:v for k,v in node.items() if k in ['notes','comment','section','chapter','tags','prologue']}}
            elif all(isinstance(s,dict) for s in value):
                yield from leaves(value,metadata,route)
            else:raise ValueError(f'Mixed content at {route}')
            return
    raise ValueError(f'No body at {route}: {list(node)}')

def run():
    print(f'Downloading {len(FILES)} additional JSON files…',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for n,_ in enumerate(pool.map(download,FILES),1):
            if n%100==0:print(f'Downloaded {n}/{len(FILES)}',flush=True)
    target=DATA/'corpus.remaining.sqlite3'
    if target.exists():target.unlink()
    db=sqlite3.connect(target)
    with sqlite3.connect(DATA/'corpus.sqlite3') as old:old.backup(db)
    old.close()
    db.execute('PRAGMA synchronous=OFF')
    db.execute('PRAGMA journal_mode=OFF')
    if 'kind' not in [x[1] for x in db.execute('PRAGMA table_info(poems)')]:
        db.execute("ALTER TABLE poems ADD COLUMN kind TEXT NOT NULL DEFAULT '诗词曲'")
    db.executescript('''CREATE TABLE IF NOT EXISTS memberships (poem_id TEXT, collection TEXT, source TEXT, UNIQUE(poem_id,collection,source));
    CREATE INDEX IF NOT EXISTS membership_collection ON memberships(collection,poem_id);
    CREATE INDEX IF NOT EXISTS membership_poem ON memberships(poem_id);
    CREATE TABLE IF NOT EXISTS reference_metadata (source TEXT PRIMARY KEY, payload TEXT);
    CREATE INDEX IF NOT EXISTS poem_kind ON poems(kind);''')
    db.execute("INSERT OR IGNORE INTO memberships SELECT id,collection,json_extract(payload,'$.source') FROM poems")
    prior=json.loads(db.execute("SELECT value FROM metadata WHERE key='stats'").fetchone()[0])
    initial=prior['total'];seen={r[0] for r in db.execute('SELECT id FROM poems')}
    report={};new_count=duplicate_count=0
    motifs='月山花酒春雨江风云雁雪梦'
    themes={'思乡':['故乡','乡','故园','归心'],'送别':['送','别','离人'],'山水':['山','江','溪','湖'],'边塞':['塞','边','胡','征','烽'],'咏物':['咏','梅','竹','菊']}
    for fi,file in enumerate(FILES,1):
        raw=json.loads((CACHE/file).read_text(encoding='utf-8'))
        url='https://github.com/chinese-poetry/chinese-poetry/blob/'+HEAD+'/'+file
        if file.endswith(('authors.json','intro.json')):
            db.execute('INSERT OR REPLACE INTO reference_metadata VALUES (?,?)',(url,json.dumps(raw,ensure_ascii=False)))
            report[file]={'referenceOnly':True};continue
        collection,dynasty,form,kind,author=specification(file)
        if 'preface' in file:form,kind='序文','古文典籍'
        records=list(leaves(raw))
        if file=='全唐诗/唐诗补录.json':
            for item in records:
                if item['title'].startswith('第'):item['title']='无题（长沙窑诗）'
        converted=json.loads(cc.convert(json.dumps(records,ensure_ascii=False)))
        added=duplicates=empty=0
        for original,p in zip(records,converted):
            paragraphs=[re.sub(r'[（(][^）)]*[）)]','',s).strip() for s in p['paragraphs']]
            text=''.join(paragraphs);normalized=re.sub(r'[^\u4e00-\u9fff]','',text)
            if not normalized:empty+=1;continue
            id=hashlib.sha1(normalized.encode()).hexdigest()[:12]
            db.execute('INSERT OR IGNORE INTO memberships VALUES (?,?,?)',(id,collection,url))
            if id in seen:duplicates+=1;duplicate_count+=1;continue
            person=p.get('author') or author
            era=p.get('dynasty') or dynasty
            era={'yuan':'元','ming':'明','qing':'清','tang':'唐','song':'宋'}.get(era,era)
            m=re.match(r'^[（(](.*?)[）)](.*)$',person) or re.match(r'^([^：:]{1,6})[：:](.*)$',person)
            if m:era,person=m[1],m[2].strip()
            era={'唐代':'唐','宋代':'宋','元代':'元','明代':'明','清代':'清'}.get(era,era)
            if len(person)>40:person=person.split('（')[0].split('，')[0]
            work=dict(id=id,title=p['title'],author=person,dynasty=era,form=p.get('type') or form,kind=kind,
                      collection=collection,paragraphs=paragraphs,original=original['paragraphs'],text=text,
                      source=url,sectionPath=p['sectionPath'],sourceMetadata=p['extra'],
                      motifs=[m for m in motifs if m in text],themes=[t for t,terms in themes.items() if kind=='诗词曲' and any(x in p['title']+text for x in terms)])
            db.execute('INSERT INTO poems(id,title,author,dynasty,form,collection,text,normalized,themes,curated,payload,kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (id,work['title'],person,era,work['form'],collection,text,normalized,json.dumps(work['themes'],ensure_ascii=False),0,json.dumps(work,ensure_ascii=False),kind))
            rowid=db.execute('SELECT last_insert_rowid()').fetchone()[0]
            db.execute('INSERT INTO search(rowid,title,author,text) VALUES (?,?,?,?)',(rowid,work['title'],person,text))
            if kind=='诗词曲':
                lines={re.sub(r'[^\u4e00-\u9fff]','',s) for s in re.split(r'[，。！？；、,!?;\n]',text)}-{''}
                db.executemany('INSERT INTO lines VALUES (?,?)',((line,id) for line in lines))
            seen.add(id);added+=1;new_count+=1
        report[file]=dict(records=len(records),added=added,duplicates=duplicates,empty=empty,collection=collection)
        if fi%50==0:
            db.commit();print(f'Imported {fi}/{len(FILES)} files; added {new_count:,}',flush=True)
    db.commit()
    print('Recomputing full-library statistics and word frequencies…',flush=True)
    words=Counter();motif_counts=Counter();characters=0
    stop={'不知','何处','何人','何事','何时','不能','可以','不是','不见','一作','不可','不得'}
    for i,(text,normalized) in enumerate(db.execute('SELECT text,normalized FROM poems'),1):
        characters+=len(normalized);motif_counts.update(m for m in motifs if m in text)
        words.update(w for w in jieba.cut(text) if len(w)>1 and re.fullmatch(r'[\u4e00-\u9fff]+',w) and w not in stop)
        if i%100000==0:print(f'Analysed {i:,} entries',flush=True)
    def counts(col):return dict(db.execute(f'SELECT {col},count(*) FROM poems GROUP BY {col} ORDER BY count(*) DESC'))
    authors=counts('author');dynasties=counts('dynasty');forms=counts('form');kinds=counts('kind')
    collections=dict(db.execute('SELECT collection,count(DISTINCT poem_id) FROM memberships GROUP BY collection'))
    provenance={**prior['provenance'],'additionalFiles':sorted(set(prior['provenance'].get('additionalFiles',[])+FILES)),
                'additionalCount':prior['provenance'].get('additionalCount',0)+new_count,'count':len(seen),
                'additionalReport':{**prior['provenance'].get('additionalReport',{}),**report},
                'scope':'Literary-content JSON collections at pinned commit; supplemental anthologies included; metadata, rankings, metrical error records and loader configuration are not counted as works.'}
    stats=dict(total=len(seen),authors=len(authors),characters=characters,dynasties=dynasties,authorRanking=list(authors.items())[:8],words=words.most_common(35),
               motifs=[dict(name=m,count=motif_counts[m]) for m in motifs],forms=forms,kinds=kinds,collections=collections,
               filters=dict(authors=list(authors)[:200],dynasties=list(dynasties),themes=list(themes),collections=list(collections),kinds=list(kinds)),provenance=provenance)
    db.execute('UPDATE metadata SET value=? WHERE key=?',(json.dumps(stats,ensure_ascii=False),'stats'))
    db.commit();db.execute('ANALYZE');db.close()
    (DATA/'remaining_provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    target.replace(DATA/'corpus.sqlite3')
    print(json.dumps(dict(before=initial,added=new_count,total=len(seen),kinds=kinds,collections=collections),ensure_ascii=False),flush=True)

if __name__=='__main__':run()
