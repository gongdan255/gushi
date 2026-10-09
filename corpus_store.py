"""Read-only indexed access to the expanded corpus; no full-corpus RAM load."""
import json
import random
import itertools
from collections import Counter
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from functools import lru_cache
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PATH = Path(__file__).parent / 'data/corpus.sqlite3'

@contextmanager
def connection():
    db = sqlite3.connect(PATH.resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()

@lru_cache(maxsize=1)
def stats():
    with connection() as db:
        return json.loads(db.execute("SELECT value FROM metadata WHERE key='stats'").fetchone()[0])

def get(id):
    with connection() as db:
        row = db.execute('SELECT payload FROM poems WHERE id=?',(id,)).fetchone()
        memberships=[]
        if row and db.execute("SELECT 1 FROM sqlite_master WHERE name='memberships'").fetchone():
            memberships=[dict(r) for r in db.execute('SELECT collection,source FROM memberships WHERE poem_id=?',(id,))]
    if not row:return None
    p=json.loads(row[0]);p.setdefault('kind','诗词曲');p['memberships']=memberships
    return p

def search(args, q, page):
    where, params = [], []
    for word in args.get('body','').split(',')[:2]:
        if len(word)==1 and '\u4e00'<=word<='\u9fff':
            where.append('instr(text,?)>0');params.append(word)
    if q:
        if len(q)>=3 and all('\u4e00'<=c<='\u9fff' for c in q):
            where.append('rowid IN (SELECT rowid FROM search WHERE search MATCH ?)')
            params.append('"'+q.replace('"','""')+'"')
        where.append('(instr(title,?)>0 OR instr(author,?)>0 OR instr(text,?)>0)')
        params += [q,q,q]
    expanded = 'kinds' in stats()
    for field in ['author','dynasty','form']+(['kind'] if expanded else []):
        if args.get(field):
            where.append(f'{field}=?')
            params.append(args[field])
    if args.get('collection'):
        where.append('id IN (SELECT poem_id FROM memberships WHERE collection=?)' if expanded else 'collection=?')
        params.append(args['collection'])
    if args.get('theme'):
        where.append('instr(themes,?)>0')
        params.append('"'+args['theme']+'"')
    if args.get('ids') is not None:
        ids = args.get('ids','').split(',')[:1000]
        where.append('id IN ('+','.join('?' for _ in ids)+')')
        params.extend(ids)
    clause = ' WHERE '+' AND '.join(where) if where else ''
    with connection() as db:
        count = db.execute('SELECT count(*) FROM poems'+clause,params).fetchone()[0]
        rows = db.execute('SELECT payload FROM poems'+clause+' ORDER BY rowid LIMIT 12 OFFSET ?',params+[(page-1)*12]).fetchall()
    return dict(total=count,page=page,items=[json.loads(r[0]) for r in rows])

def build_insights(texts):
    seasons=Counter();nodes=Counter();pairs=Counter();total=0
    labels=list('月酒山水花春风雨云雪江梦')
    for text in texts:
        total+=1
        seasons.update(c for c in '春夏秋冬' if c in text)
        present=[c for c in labels if c in text]
        nodes.update(present);pairs.update(itertools.combinations(present,2))
    return dict(total=total,seasons=[dict(name=c,value=seasons[c]) for c in '春夏秋冬'],
                nodes=[dict(name=c,value=nodes[c]) for c in labels],
                links=[dict(source=a,target=b,value=n) for (a,b),n in pairs.most_common(18)])

@lru_cache(maxsize=1)
def insights():
    with connection() as db:
        condition=" WHERE kind='诗词曲'" if 'kinds' in stats() else ''
        return build_insights(r[0] for r in db.execute('SELECT text FROM poems'+condition))

def random_poem():
    with connection() as db:
        row = db.execute('SELECT payload FROM poems WHERE rowid=?',(random.randint(1,stats()['total']),)).fetchone()
    return json.loads(row[0])

@lru_cache(maxsize=256)
def related(id):
    p = get(id)
    if not p:
        return None
    with connection() as db:
        kind=p.get('kind','诗词曲')
        kind_filter=' AND kind=?' if 'kinds' in stats() else ''
        kind_params=[kind] if kind_filter else []
        rows = db.execute('SELECT payload FROM poems WHERE author=? AND id<>?'+kind_filter+' LIMIT 160',[p['author'],id]+kind_params).fetchall()
        if len(rows)<60:
            for term in p['motifs'][:2]:
                rows += db.execute('SELECT payload FROM poems WHERE instr(text,?)>0 AND id<>?'+kind_filter+' LIMIT 80',[term,id]+kind_params).fetchall()
    pool = list({x['id']:x for x in (json.loads(r[0]) for r in rows)}.values())
    if not pool:
        return []
    matrix = TfidfVectorizer(analyzer='char',ngram_range=(1,2)).fit_transform([p['text']]+[x['text'] for x in pool])
    scores = cosine_similarity(matrix[0],matrix[1:]).ravel()
    return [pool[i] for i in scores.argsort()[::-1][:3]]

def line_ids(line):
    with connection() as db:
        return {r[0] for r in db.execute('SELECT poem_id FROM lines WHERE line=?',(line,))}

@lru_cache(maxsize=128)
def filter_options(kind='', collection='', dynasty='', author='', theme=''):
    """Each selector depends only on valid selections to its left."""
    selected={}; options={}; where=[]; params=[]
    with connection() as db:
        for field,value in [('kind',kind),('collection',collection),('dynasty',dynasty),('author',author),('theme',theme)]:
            clause=' WHERE '+' AND '.join(where) if where else ''
            if field=='collection':
                sql='SELECT DISTINCT m.collection FROM memberships m WHERE m.poem_id IN (SELECT id FROM poems'+clause+') ORDER BY m.collection'
            elif field=='theme':
                sql='SELECT DISTINCT j.value FROM poems,json_each(poems.themes) j'+clause+' ORDER BY j.value'
            else:
                sql=f'SELECT {field} FROM poems'+clause+f' GROUP BY {field} ORDER BY count(*) DESC, {field}'
                # Keep the existing common-author scope, within the selected corpus.
                if field=='author':sql+=' LIMIT 200'
            choices=[r[0] for r in db.execute(sql,params)]
            options[field]=choices
            selected[field]=value if value in choices else ''
            if selected[field]:
                if field=='collection':where.append('poems.id IN (SELECT poem_id FROM memberships WHERE collection=?)')
                elif field=='theme':where.append('instr(themes,?)>0')
                else:where.append(f'{field}=?')
                params.append('"'+value+'"' if field=='theme' else value)
    return dict(options=options,selected=selected)
