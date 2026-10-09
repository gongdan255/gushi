import unittest
from app import app, POEMS, normalize
import corpus_store as corpus

class PoetryTests(unittest.TestCase):
    def test_seasons_and_cooccurrence_are_body_counts(self):
        sample=corpus.build_insights(['春春月酒','秋月','春秋山水','无'])
        self.assertEqual(sample['seasons'],[{'name':'春','value':2},{'name':'夏','value':0},{'name':'秋','value':2},{'name':'冬','value':0}])
        self.assertEqual(next(x['value'] for x in sample['links'] if x['source']=='月' and x['target']=='酒'),1)
        d=self.client.get('/api/insights').get_json()
        self.assertEqual(len(d['nodes']),12)
        self.assertEqual(len(d['links']),18)
        spring=self.client.get('/api/poems',query_string={'kind':'诗词曲','body':'春'}).get_json()
        self.assertEqual(spring['total'],d['seasons'][0]['value'])
        link=d['links'][0]
        results=self.client.get('/api/poems',query_string={'kind':'诗词曲','body':link['source']+','+link['target']}).get_json()
        self.assertEqual(results['total'],link['value'])
        self.assertTrue(all(link['source'] in p['text'] and link['target'] in p['text'] for p in results['items']))
    def test_custom_feihua_keyword_and_related_words(self):
        self.assertTrue(self.check('低头思故乡','故')['ok'])
        for word in ['月','鄉']:
            d=self.client.get('/api/feihua/suggestions',query_string={'keyword':word}).get_json()
            self.assertTrue(d['available'])
            self.assertTrue(d['words'])
            self.assertTrue(all(d['keyword'] in w and 2<=len(w)<=4 for w in d['words']))
        for word in ['明月','A','1','月!','']:
            self.assertEqual(self.client.get('/api/feihua/suggestions',query_string={'keyword':word}).status_code,400)
            self.assertFalse(self.check('床前明月光',word)['ok'])
    def test_expanded_feihua_keywords(self):
        keywords=self.client.get('/api/feihua/keywords').get_json()['keywords']
        self.assertEqual(len(keywords),36)
        self.assertEqual(len(set(keywords)),36)
        self.assertTrue(all(len(k)==1 for k in keywords))
        for word,line in [('日','白日依山尽'),('海','海上生明月'),('人','空山不见人'),('乡','低头思故乡'),('柳','两个黄鹂鸣翠柳')]:
            with self.subTest(word=word):
                self.assertTrue(self.check(line,word)['ok'])
                self.assertFalse(self.check(line,word,[normalize(line)])['ok'])
        self.assertFalse(self.check('白日依山尽','星')['ok'])
        self.assertFalse(self.check('白日依山尽','电脑')['ok'])
    def test_puzzle_has_four_unique_shuffled_original_lines(self):
        for _ in range(8):
            questions=self.client.get('/api/puzzle').get_json()['questions']
            self.assertEqual(len(questions),5)
            self.assertEqual(len({q['poemId'] for q in questions}),5)
            for q in questions:
                original=next(p for p in POEMS if p['id']==q['poemId'])
                self.assertEqual(q['answer'],original['lines'])
                self.assertEqual(len(set(q['pieces'])),4)
                self.assertCountEqual(q['pieces'],q['answer'])
                self.assertNotEqual(q['pieces'],q['answer'])
                self.assertEqual(len({len(line) for line in q['answer']}),1)
                self.assertIn(len(q['answer'][0]),(5,7))
    def test_cascading_filters(self):
        d=self.client.get('/api/filters',query_string={'kind':'诗词曲','collection':'元曲','dynasty':'元','author':'刘克庄'}).get_json()
        self.assertEqual(d['selected']['author'],'')
        self.assertNotIn('刘克庄',d['options']['author'])
        self.assertIn('关汉卿',d['options']['author'])
        self.assertEqual(d['options']['dynasty'],['元'])
        d=self.client.get('/api/filters',query_string={'kind':'古文典籍','collection':'元曲','dynasty':'元','author':'关汉卿'}).get_json()
        self.assertNotIn('元曲',d['options']['collection'])
        self.assertEqual(d['selected']['collection'],'')
        self.assertEqual(d['selected']['author'],'')
        d=self.client.get('/api/filters',query_string={'kind':'古文典籍','collection':'论语'}).get_json()
        self.assertEqual(d['options']['theme'],[])
        self.assertEqual(d['options']['dynasty'],['先秦'])
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

    def test_statistics_are_corpus_based(self):
        d = self.client.get('/api/stats').get_json()
        if corpus.PATH.exists():
            with corpus.connection() as db:
                count = db.execute('SELECT count(*) FROM poems').fetchone()[0]
                moon = db.execute("SELECT count(*) FROM poems WHERE instr(text,'月')>0").fetchone()[0]
        else:
            count, moon = len(POEMS), sum('月' in p['text'] for p in POEMS)
        self.assertEqual(d['total'], count)
        self.assertEqual(sum(d['dynasties'].values()), count)
        self.assertEqual(next(m['count'] for m in d['motifs'] if m['name']=='月'), moon)

    def test_traditional_search_and_filters(self):
        d = self.client.get('/api/poems', query_string={'q':'靜夜思','author':'李白','dynasty':'唐'}).get_json()
        self.assertGreaterEqual(d['total'], 1)
        self.assertEqual(d['items'][0]['title'], '静夜思')
        self.assertEqual(self.client.get('/api/poems?ids=').get_json()['total'], 0)

    def test_pagination_and_empty(self):
        a = self.client.get('/api/poems?page=1').get_json()['items']
        b = self.client.get('/api/poems?page=2').get_json()['items']
        self.assertFalse({p['id'] for p in a} & {p['id'] for p in b})
        self.assertEqual(self.client.get('/api/poems?q=不存在的随机文本xyz').get_json()['total'], 0)
        self.assertEqual(self.client.get('/api/poems?page=bad').status_code, 200)

    def test_detail_and_recommendation(self):
        p = POEMS[0]
        d = self.client.get('/api/poems/'+p['id']).get_json()
        self.assertEqual(len(d['related']), 3)
        self.assertNotIn(p['id'], [x['id'] for x in d['related']])
        self.assertTrue(d['poem']['source'].startswith('https://github.com/'))
        self.assertEqual(self.client.get('/api/poems/missing').status_code, 404)

    def test_quiz_has_unique_choices_and_real_answers(self):
        for _ in range(10):
            questions = self.client.get('/api/quiz').get_json()['questions']
            self.assertEqual(len(questions), 5)
            for q in questions:
                self.assertEqual(len(set(q['options'])), 4)
                self.assertIn(q['answer'], q['options'])
                poem = next(p for p in POEMS if p['id']==q['poemId'])
                self.assertIn(q['prompt']+q['answer'], normalize(poem['text']))

    def check(self, text, keyword='月', used=None):
        return self.client.post('/api/feihua/check', json={'text':text, 'keyword':keyword, 'used':used or []}).get_json()

    def test_fly_accepts_traditional_and_punctuation(self):
        d = self.check('舉頭望明月。')
        self.assertTrue(d['ok'])
        self.assertEqual(d['poem']['title'], '静夜思')

    def test_fly_rejects_repeat_even_with_added_clause(self):
        self.assertFalse(self.check('床前明月光，疑是地上霜。', used=['床前明月光'])['ok'])

    def test_fly_rejects_wrong_keyword_fragment_and_invention(self):
        for text in ['白日依山尽','床前明月','我今天看到了月亮']:
            self.assertFalse(self.check(text)['ok'])

    def test_fly_rejects_spliced_poems(self):
        self.assertFalse(self.check('床前明月光，海上生明月。')['ok'])

    def test_bad_payload_does_not_crash(self):
        for payload in [[], {'text':None}, {'text':'床前明月光','keyword':'月','used':[{}]}]:
            self.assertIn(self.client.post('/api/feihua/check',json=payload).status_code,(200,400))

    @unittest.skipUnless(corpus.PATH.exists(), 'Expanded corpus not built')
    def test_full_corpus_and_song_ci_filter(self):
        stats = self.client.get('/api/stats').get_json()
        self.assertGreater(stats['total'], 300000)
        d = self.client.get('/api/poems',query_string={'collection':'宋词','q':'明月几时有'}).get_json()
        self.assertGreater(d['total'], 0)
        self.assertTrue(all(p['collection']=='宋词' for p in d['items']))
        self.assertTrue(self.check('明月几时有')['ok'])
        # A short clause is legitimate when present in the corpus (三台令).
        self.assertTrue(self.check('明月')['ok'])

    @unittest.skipUnless(corpus.PATH.exists(), 'Expanded corpus not built')
    def test_indexed_search_agrees_with_literal_scan(self):
        for q in ['明月几时有','春风','李白','江南']:
            d = self.client.get('/api/poems',query_string={'q':q}).get_json()
            with corpus.connection() as db:
                expected = db.execute('SELECT count(*) FROM poems WHERE instr(title,?)>0 OR instr(author,?)>0 OR instr(text,?)>0',(q,q,q)).fetchone()[0]
            self.assertEqual(d['total'], expected)

    @unittest.skipUnless(corpus.PATH.exists(), 'Expanded corpus not built')
    def test_additional_collections_and_classics(self):
        stats = self.client.get('/api/stats').get_json()
        self.assertEqual(sum(stats['kinds'].values()), stats['total'])
        for name in ['诗经','楚辞','元曲','花间集','南唐二主词','曹操诗集','纳兰性德诗集','御定全唐诗','论语','孟子','大学','中庸','幽梦影','古文观止','水墨唐诗','千字文','宋词三百首','唐诗补录']:
            with self.subTest(collection=name):
                d = self.client.get('/api/poems',query_string={'collection':name}).get_json()
                self.assertGreater(d['total'], 0)
                p = self.client.get('/api/poems/'+d['items'][0]['id']).get_json()['poem']
                self.assertIn(name,[m['collection'] for m in p['memberships']])
        d = self.client.get('/api/poems',query_string={'collection':'论语','kind':'古文典籍','q':'学而时习之'}).get_json()
        self.assertGreater(d['total'],0)
        p=d['items'][0]
        self.assertEqual(p['kind'],'古文典籍')
        with corpus.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM lines WHERE poem_id=?',(p['id'],)).fetchone()[0],0)
        self.assertEqual(self.client.get('/api/poems',query_string={'collection':'论语','kind':'诗词曲'}).get_json()['total'],0)
        for collection,query in [('诗经','关关雎鸠'),('元曲','枯藤老树')]:
            self.assertGreater(self.client.get('/api/poems',query_string={'collection':collection,'q':query}).get_json()['total'],0)

if __name__ == '__main__':
    unittest.main()
