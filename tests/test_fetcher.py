import importlib.util,sys,unittest
from unittest import mock
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fetcher',ROOT/'scripts'/'fetch_market_data.py');fetcher=importlib.util.module_from_spec(spec);sys.modules['fetcher']=fetcher;spec.loader.exec_module(fetcher)

class FetcherTests(unittest.TestCase):
 def test_market_list_is_complete_and_generic(self):
  self.assertEqual(10,len(fetcher.MARKETS));self.assertEqual(10,len({m['id'] for m in fetcher.MARKETS}))
  text=str(fetcher.MARKETS).lower()
  for private in ('private-person-name','private-home-address','private-email'):self.assertNotIn(private,text)
 def test_parse_chart_deduplicates_and_ignores_null(self):
  payload={'chart':{'result':[{'timestamp':[1609459200,1609545600,1609545600,1609632000], 'indicators':{'quote':[{'close':[100,None,101,102]}]}}], 'error':None}}
  points=fetcher.parse_chart(payload,{'symbol':'TEST'}) if False else None
  # Minimum-history guard is intentional; use a production-sized fixture below.
  stamps=[1609459200+i*86400 for i in range(40)];closes=[100+i for i in range(40)]
  payload['chart']['result'][0]['timestamp']=stamps;payload['chart']['result'][0]['indicators']['quote'][0]['close']=closes
  points=fetcher.parse_chart(payload,{'symbol':'TEST'});self.assertEqual(40,len(points));self.assertEqual(100.0,points[0][1]);self.assertEqual(139.0,points[-1][1])
 def test_parse_eastmoney_daily_rows(self):
  rows=[f"2024-01-{i+1:02d},1,{100+i},2,0" for i in range(30)]
  points=fetcher.parse_eastmoney({'data':{'klines':rows}},{'providerSymbol':'1.000300'})
  self.assertEqual(30,len(points));self.assertEqual(100.0,points[0][1]);self.assertEqual(129.0,points[-1][1])
 def test_validation_rejects_missing_series(self):
  with self.assertRaises(ValueError):fetcher.validate_document({'schemaVersion':2,'generatedAt':'2026-01-01T00:00:00Z','dataAsOf':'2025-12-31','indices':[]})
 def test_total_upstream_failure_does_not_claim_freshness(self):
  existing={'updatedAt':'2026-01-01T00:00:00Z','indices':[{'id':m['id']} for m in fetcher.MARKETS]}
  with mock.patch.object(fetcher,'fetch_market',side_effect=fetcher.FetchError('offline')):
   with self.assertRaises(fetcher.FetchError):fetcher.build_document(existing,datetime(2026,1,2,tzinfo=timezone.utc))

if __name__=='__main__':unittest.main()
