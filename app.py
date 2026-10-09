import json
import random
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timezone, timedelta

import jieba
import corpus_store as corpus
from flask import Flask, jsonify, render_template, request
from opencc import OpenCC
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024
cc = OpenCC('t2s')
POEMS = json.loads((ROOT / 'data/poems.json').read_text(encoding='utf-8'))
BY_ID = {p['id']: p for p in POEMS}
MOTIFS = {'月': '月', '山': '山', '花': '花', '酒': '酒', '春': '春', '雨': '雨', '江': '江', '风': '风', '云': '云', '雁': '雁', '雪': '雪', '梦': '梦'}
FEIHUA_KEYWORDS = list('月花春山酒雨云雪江风雁梦秋冬夏日星水海河湖泉松竹梅柳荷菊鸟舟夜乡人心天叶')
THEMES = {'思乡': ['故乡', '乡', '故园', '归心'], '送别': ['送', '别', '离人'], '山水': ['山', '江', '溪', '湖'], '边塞': ['塞', '边', '胡', '征', '烽'], '咏物': ['咏', '梅', '竹', '菊']}
STOP = set('不有无是何人一上中下来去与之为自此时日处谁君我尔还多能如知见未得到已将却相更又其以于但欲可应只今莫从及也而矣兮所乃皆向'.split())
# Single characters are excluded from segmented word frequency; imagery is counted separately.
STOP.update(['不知', '何处', '何人', '何事', '何时', '不能', '可以', '不是', '不见', '一作'])
for p in POEMS:
    p['text'] = ''.join(p['paragraphs'])
    p['motifs'] = [m for m in MOTIFS if m in p['text']]
    p['themes'] = [t for t, words in THEMES.items() if any(w in p['title'] + p['text'] for w in words)]
    p['lines'] = [s for s in re.split(r'[，。！？；、]', p['text']) if s]

LINE_INDEX = defaultdict(list)

def normalize(text):
    return re.sub(r'[^\u4e00-\u9fff]', '', cc.convert(text))

for p in POEMS:
    for line in p['lines']:
        LINE_INDEX[normalize(line)].append(p['id'])

VECTORIZER = TfidfVectorizer(analyzer='char', ngram_range=(1, 2))
MATRIX = VECTORIZER.fit_transform(p['text'] for p in POEMS)

def public(p):
    return {k: v for k, v in p.items() if k != 'lines'}

@app.get('/')
def index():
    return render_template('index.html')

@app.get('/api/stats')
@lru_cache(maxsize=1)
def stats():
    if corpus.PATH.exists():
        return jsonify(corpus.stats())
    words = Counter()
    for p in POEMS:
        words.update(w for w in jieba.cut(p['text']) if len(w) > 1 and re.fullmatch(r'[\u4e00-\u9fff]+', w) and w not in STOP)
    return jsonify(total=len(POEMS), authors=len({p['author'] for p in POEMS}),
                   characters=sum(len(normalize(p['text'])) for p in POEMS),
                   dynasties=dict(Counter(p['dynasty'] for p in POEMS)),
                   authorRanking=Counter(p['author'] for p in POEMS).most_common(8),
                   words=words.most_common(35),
                   motifs=[{'name': m, 'count': sum(m in p['text'] for p in POEMS)} for m in MOTIFS],
                   forms=dict(Counter(p['form'] for p in POEMS)),
                   collections=dict(Counter(p['collection'] for p in POEMS)),
                   kinds={'诗词曲':len(POEMS)},
                   filters={'authors': sorted({p['author'] for p in POEMS}), 'dynasties': sorted({p['dynasty'] for p in POEMS}), 'themes': list(THEMES), 'kinds':['诗词曲']},
                   provenance=json.loads((ROOT / 'data/provenance.json').read_text(encoding='utf-8')))

@app.get('/api/poems')
def poems():
    q = cc.convert(request.args.get('q', '').strip())[:100]
    if corpus.PATH.exists():
        try:
            page = max(1,int(request.args.get('page',1)))
        except ValueError:
            page = 1
        return jsonify(corpus.search(request.args,q,page))
    filtered = [p for p in POEMS if (not q or q in p['title'] or q in p['author'] or q in p['text'])]
    for word in request.args.get('body','').split(',')[:2]:
        if re.fullmatch(r'[\u4e00-\u9fff]',word):
            filtered=[p for p in filtered if word in p['text']]
    if request.args.get('kind') not in (None,'','诗词曲'):
        filtered=[]
    for key in ['author', 'dynasty', 'form', 'collection']:
        value = request.args.get(key)
        if value:
            filtered = [p for p in filtered if p[key] == value]
    theme = request.args.get('theme')
    if theme:
        filtered = [p for p in filtered if theme in p['themes']]
    if request.args.get('ids') is not None:
        ids = set(request.args.get('ids', '').split(','))
        filtered = [p for p in filtered if p['id'] in ids]
    try:
        page = max(1, int(request.args.get('page', 1)))
    except ValueError:
        page = 1
    return jsonify(total=len(filtered), page=page, items=[public(p) for p in filtered[(page-1)*12:page*12]])

@app.get('/api/filters')
def filters():
    fields=['kind','collection','dynasty','author','theme']
    if corpus.PATH.exists() and 'kinds' in corpus.stats():
        return jsonify(corpus.filter_options(*(request.args.get(k,'') for k in fields)))
    pool=POEMS;options={};selected={}
    for field in fields:
        values=Counter(v for p in pool for v in (p['themes'] if field=='theme' else [p.get(field,'诗词曲' if field=='kind' else '')]))
        choices=[k for k,_ in values.most_common(200 if field=='author' else None)]
        value=request.args.get(field,'')
        options[field]=choices;selected[field]=value if value in choices else ''
        if selected[field]:pool=[p for p in pool if (value in p['themes'] if field=='theme' else p.get(field,'诗词曲' if field=='kind' else '')==value)]
    return jsonify(options=options,selected=selected)

@app.get('/api/insights')
@lru_cache(maxsize=1)
def insights():
    return jsonify(corpus.insights() if corpus.PATH.exists() else corpus.build_insights(p['text'] for p in POEMS))

@app.get('/api/poems/random')
def random_poem():
    if corpus.PATH.exists():
        return jsonify(corpus.random_poem())
    return jsonify(public(random.choice(POEMS)))

@app.get('/api/poems/daily')
def daily_poem():
    day = datetime.now(timezone(timedelta(hours=8))).date().toordinal()
    short = [p for p in POEMS if len(p['lines']) == 4 and all(len(s) in (5, 7) for s in p['lines'])]
    return jsonify(public(short[day % len(short)]))

@app.get('/api/poems/<poem_id>')
def detail(poem_id):
    if corpus.PATH.exists():
        p = corpus.get(poem_id)
        if p is None:
            return jsonify(error='未找到这首诗'),404
        return jsonify(poem=p,related=corpus.related(poem_id))
    if poem_id not in BY_ID:
        return jsonify(error='未找到这首诗'), 404
    i = next(i for i, p in enumerate(POEMS) if p['id'] == poem_id)
    scores = cosine_similarity(MATRIX[i], MATRIX).ravel()
    related = [public(POEMS[j]) for j in scores.argsort()[::-1] if j != i][:3]
    return jsonify(poem=public(BY_ID[poem_id]), related=related)

@app.get('/api/quiz')
def quiz():
    candidates = [p for p in POEMS if len(p['lines']) >= 2 and all(len(x) in (5, 7) for x in p['lines']) and len(p['lines']) <= 8]
    chosen = random.sample(candidates, min(5, len(candidates)))
    questions = []
    for p in chosen:
        position = random.randrange(0, len(p['lines'])-1, 2)
        answer = p['lines'][position+1]
        pool = list({s for other in candidates for s in other['lines'] if len(s) == len(answer) and s != answer})
        options = random.sample(pool, 3) + [answer]
        random.shuffle(options)
        questions.append(dict(poemId=p['id'], title=p['title'], author=p['author'], prompt=p['lines'][position], options=options, answer=answer))
    return jsonify(questions=questions)

@app.get('/api/puzzle')
def puzzle():
    candidates = [p for p in POEMS if len(p['lines']) == 4 and len(set(p['lines'])) == 4
                  and len({len(s) for s in p['lines']}) == 1
                  and all(re.fullmatch(r'[\u4e00-\u9fff]{5}|[\u4e00-\u9fff]{7}', s) for s in p['lines'])]
    questions = []
    for p in random.sample(candidates, min(5, len(candidates))):
        pieces = random.sample(p['lines'], 4)
        if pieces == p['lines']:
            pieces = pieces[1:] + pieces[:1]
        questions.append(dict(poemId=p['id'], title=p['title'], author=p['author'],
                              pieces=pieces, answer=p['lines']))
    return jsonify(questions=questions)

@app.get('/api/feihua/keywords')
def feihua_keywords():
    return jsonify(keywords=FEIHUA_KEYWORDS)

@lru_cache(maxsize=256)
def related_keyword_words(keyword):
    if corpus.PATH.exists():
        with corpus.connection() as db:
            expanded='kinds' in corpus.stats()
            texts=[r[0] for r in db.execute("SELECT text FROM poems WHERE instr(text,?)>0"+
                   (" AND kind='诗词曲'" if expanded else '')+" LIMIT 300",(keyword,))]
    else:
        texts=[p['text'] for p in POEMS if keyword in p['text']][:300]
    counts=Counter(word for text in texts for word in jieba.cut(text)
                   if keyword in word and 2<=len(word)<=4 and re.fullmatch(r'[\u4e00-\u9fff]+',word))
    return dict(keyword=keyword,words=[w for w,_ in counts.most_common(12)],available=bool(texts))

@app.get('/api/feihua/suggestions')
def feihua_suggestions():
    keyword=cc.convert(request.args.get('keyword','').strip())
    if not re.fullmatch(r'[\u4e00-\u9fff]',keyword):
        return jsonify(error='请输入一个汉字作为令字。'),400
    return jsonify(related_keyword_words(keyword))

@app.post('/api/feihua/check')
def feihua():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(ok=False, message='请输入有效诗句。'), 400
    text, keyword = data.get('text', ''), data.get('keyword', '')
    if not isinstance(text, str) or not isinstance(keyword, str) or len(text) > 200:
        return jsonify(ok=False, message='请输入 200 字以内的诗句。'), 400
    line = normalize(text)
    keyword = cc.convert(keyword.strip())
    if not re.fullmatch(r'[\u4e00-\u9fff]',keyword):
        return jsonify(ok=False, message='请输入一个汉字作为令字。'), 400
    if keyword not in line:
        return jsonify(ok=False, message=f'诗句中需要包含“{keyword}”。')
    used = data.get('used', [])
    if not isinstance(used, list) or any(not isinstance(x, str) for x in used):
        return jsonify(ok=False, message='答题记录格式错误。'), 400
    parts = [normalize(s) for s in re.split(r'[，。！？；,!?;\n]', text) if normalize(s)]
    lookup = corpus.line_ids if corpus.PATH.exists() else lambda s: set(LINE_INDEX.get(s,[]))
    line_sets = [lookup(p) for p in parts]
    if not parts or any(not ids for ids in line_sets):
        return jsonify(ok=False, message='本库暂未匹配到，请检查诗句或换一句。')
    common = set.intersection(*line_sets)
    candidates = [corpus.get(i) if corpus.PATH.exists() else BY_ID[i] for i in sorted(common)]
    matches = [p for p in candidates if line in normalize(p['text'])]
    matches.sort(key=lambda p: p['collection'] not in ('唐诗三百首', '千家诗'))
    if not matches:
        return jsonify(ok=False, message='请提交同一首诗中连续的完整诗句。')
    scoring = list(dict.fromkeys(p for p in parts if keyword in p))
    previous = {normalize(x) for x in used}
    if any(p in previous for p in scoring):
        return jsonify(ok=False, message='这句已经答过了，换一句试试。')
    return jsonify(ok=True, normalized=line, accepted=scoring, poem=public(matches[0]), message='答对了！')

if __name__ == '__main__':
    from waitress import serve
    print('诗境: http://127.0.0.1:5180', flush=True)
    serve(app, host='127.0.0.1', port=5180)
