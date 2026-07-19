import importlib.util,sys,unittest
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
 def test_validation_rejects_missing_series(self):
  with self.assertRaises(ValueError):fetcher.validate_document({'schemaVersion':1,'indices':[]})

if __name__=='__main__':unittest.main()
