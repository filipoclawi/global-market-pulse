import importlib.util,json,sys,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts'/'fetch_economic_news.py'

class NewsArtifactTests(unittest.TestCase):
 def test_generated_artifact_is_weekly_high_signal_and_public_safe(self):
  doc=json.loads((ROOT/'data'/'economic-news.json').read_text())
  self.assertEqual(1,doc['schemaVersion'])
  self.assertGreaterEqual(len(doc['stories']),4);self.assertLessEqual(len(doc['stories']),8)
  ids=[x['id'] for x in doc['stories']];self.assertEqual(len(ids),len(set(ids)))
  for story in doc['stories']:
   self.assertTrue(story['title']);self.assertTrue(story['preview']);self.assertTrue(story['summary']);self.assertTrue(story['whyItMatters'])
   self.assertIn(story['readingMinutes'],(1,2));self.assertLessEqual(len((story['summary']+' '+story['whyItMatters']).split()),360)
   self.assertGreaterEqual(len(story['tags']),1);self.assertLessEqual(len(story['tags']),4)
   self.assertTrue(story['sourceUrl'].startswith('https://'))
   self.assertNotIn('<script',json.dumps(story).lower())
  self.assertIsInstance(doc.get('archive'),list)

class NewsFetcherTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  spec=importlib.util.spec_from_file_location('news_fetcher',SCRIPT);cls.mod=importlib.util.module_from_spec(spec);sys.modules['news_fetcher']=cls.mod;spec.loader.exec_module(cls.mod)
 def test_stable_id_ignores_tracking_parameters(self):
  a=self.mod.stable_id('https://example.org/report?b=2&id=4&utm_source=x','Original title')
  b=self.mod.stable_id('https://example.org/report?id=4&utm_medium=y&b=2','Corrected title')
  self.assertEqual(a,b)
 def test_validate_rejects_duplicate_ids(self):
  story={'id':'x','title':'Title','preview':'Preview','summary':'Summary','whyItMatters':'Lens','publishedAt':'2026-07-25T00:00:00Z','sourceLabel':'Official','sourceUrl':'https://example.org/a','tags':['Rates'],'readingMinutes':1}
  doc={'schemaVersion':1,'generatedAt':'2026-07-26T00:00:00Z','checkedAt':'2026-07-26T00:00:00Z','dataAsOf':'2026-07-25','windowStart':'2026-07-19','sourcesChecked':['Official'],'staleSources':[],'stories':[story,dict(story)],'archive':[]}
  with self.assertRaises(ValueError):self.mod.validate_document(doc)
 def test_total_feed_failure_preserves_last_good_without_claiming_freshness(self):
  existing={'schemaVersion':1,'generatedAt':'2026-07-25T00:00:00Z','dataAsOf':'2026-07-24','windowStart':'2026-07-18','stories':[{'id':'x'}]}
  with mock.patch.object(self.mod,'fetch_source',side_effect=self.mod.NewsFetchError('offline')):
   with self.assertRaises(self.mod.NewsFetchError):self.mod.build_document(existing,datetime(2026,7,26,tzinfo=timezone.utc))
 def test_main_keeps_valid_artifact_when_every_source_is_offline(self):
  original=(ROOT/'data'/'economic-news.json').read_text()
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory)/'economic-news.json';out.write_text(original)
   with mock.patch.object(self.mod,'OUT',out),mock.patch.object(self.mod,'build_document',side_effect=self.mod.NewsFetchError('offline')):
    self.mod.main()
   before=json.loads(original);after=json.loads(out.read_text())
   self.assertEqual(before['stories'],after['stories']);self.assertEqual(before['checkedAt'],after['checkedAt'])
   self.assertTrue(after['briefingStale']);self.assertGreater(after['lastAttemptAt'],before['checkedAt']);self.assertEqual('Briefing refresh',after['staleSources'][0]['source'])
 def test_partial_failure_is_visible_without_blocking_valid_artifact(self):
  sources=(self.mod.Source('Working','https://example.org/working',5),self.mod.Source('Offline','https://example.org/offline',5))
  def fetch(source):
   if source.name=='Offline':raise self.mod.NewsFetchError('offline')
   return []
  with mock.patch.object(self.mod,'SOURCES',sources),mock.patch.object(self.mod,'fetch_source',side_effect=fetch):
   doc=self.mod.build_document(None,datetime(2026,7,26,tzinfo=timezone.utc))
  self.assertEqual(['Working'],doc['sourcesChecked']);self.assertEqual(1,len(doc['staleSources']))
 def test_same_week_topic_is_deduplicated_across_publishers(self):
  source=self.mod.Source('BBC News','https://example.org/feed',4)
  item={'title':'New US tariff and inflation implications','url':'https://example.org/tariffs','published':datetime(2026,7,24,tzinfo=timezone.utc),'description':'A new tariff package raises import costs and inflation uncertainty for households and companies.','source':source}
  with mock.patch.object(self.mod,'SOURCES',(source,)),mock.patch.object(self.mod,'fetch_source',return_value=[item]):
   doc=self.mod.build_document(None,datetime(2026,7,26,tzinfo=timezone.utc))
  self.assertNotIn(self.mod.stable_id(item['url'],item['title']),[story['id'] for story in doc['stories']])
 def test_story_leaving_inbox_is_retained_for_starred_collection(self):
  old={'id':'older-story','title':'Older macro story','preview':'Preview','summary':'Summary','whyItMatters':'Long-term lens','publishedAt':'2026-07-01T00:00:00Z','sourceLabel':'Official','sourceUrl':'https://example.org/older','tags':['Growth'],'readingMinutes':1}
  existing={'schemaVersion':1,'generatedAt':'2026-07-02T00:00:00Z','stories':[old],'archive':[]}
  source=self.mod.Source('Working','https://example.org/feed',5)
  with mock.patch.object(self.mod,'SOURCES',(source,)),mock.patch.object(self.mod,'fetch_source',return_value=[]):
   doc=self.mod.build_document(existing,datetime(2026,7,26,tzinfo=timezone.utc))
  self.assertIn('older-story',[story['id'] for story in doc['archive']]);self.assertNotIn('older-story',[story['id'] for story in doc['stories']])
 def test_old_fallback_never_looks_fresh(self):
  story={'id':'old','title':'Old story','preview':'Preview','summary':'Summary','whyItMatters':'Lens','publishedAt':'2026-07-01T00:00:00Z','sourceLabel':'Official','sourceUrl':'https://example.org/old','tags':['Growth'],'readingMinutes':1}
  existing={'stories':[dict(story,id=f'old-{i}',sourceUrl=f'https://example.org/old-{i}') for i in range(4)],'archive':[]}
  source=self.mod.Source('Working','https://example.org/feed',5)
  with mock.patch.object(self.mod,'SOURCES',(source,)),mock.patch.object(self.mod,'fetch_source',return_value=[]),mock.patch.object(self.mod,'load_json',return_value={'stories':[]}):
   doc=self.mod.build_document(existing,datetime(2026,7,26,tzinfo=timezone.utc))
  self.assertTrue(doc['briefingStale']);self.assertEqual(0,doc['freshStoryCount'])
 def test_validation_rejects_bad_freshness_metadata(self):
  doc=json.loads((ROOT/'data'/'economic-news.json').read_text());doc['dataAsOf']='2026-01-01'
  with self.assertRaises(ValueError):self.mod.validate_document(doc)

if __name__=='__main__':unittest.main()
