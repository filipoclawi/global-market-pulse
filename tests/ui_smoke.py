#!/usr/bin/env python3
import sys,time,subprocess,urllib.request,json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
server=subprocess.Popen([sys.executable,'-m','http.server','8765'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(30):
  try:urllib.request.urlopen('http://127.0.0.1:8765',timeout=1);break
  except Exception:time.sleep(.2)
 errors=[]
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None);page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8765',wait_until='networkidle');page.wait_for_function("document.documentElement.dataset.ready === 'true'")
  assert page.get_by_role('heading',name='The world market, at a glance.').count()==1
  assert page.locator('.market-card').count()==10
  assert page.locator('[data-range]').count()==10
  assert page.locator('#updated-exact').inner_text()!='—'
  assert 'Data through' in page.locator('#data-as-of').inner_text()
  before=page.locator('#average-change').inner_text();page.locator('#comparison-date').fill('2024-01-02');page.locator('#comparison-date').dispatch_event('change');page.wait_for_timeout(200);after=page.locator('#average-change').inner_text();assert after!='—' and after!=before
  page.get_by_role('button',name='3Y',exact=True).click();assert page.get_by_role('button',name='3Y',exact=True).get_attribute('aria-pressed')=='true'
  chart_ranges=page.evaluate("Chart.getChart('comparison-chart').data.datasets.map(d=>{const ys=d.data.map(p=>p.y);return Math.max(...ys)-Math.min(...ys)})")
  assert max(chart_ranges)>5,chart_ranges
  initial_instances=page.evaluate('Object.keys(Chart.instances).length');assert initial_instances==12,initial_instances
  latest=page.locator('#comparison-date').get_attribute('max');page.locator('#comparison-date').fill(latest);page.locator('#comparison-date').dispatch_event('change');page.wait_for_timeout(100);assert page.locator('#average-change').inner_text()!='—';assert page.locator('#advancing-count').inner_text().endswith('/ 10')
  page.locator('#comparison-date').fill('');page.locator('#comparison-date').dispatch_event('change');page.wait_for_timeout(100);assert page.locator('#comparison-date').input_value()
  for value in ('2024-01-02','2024-02-02','2024-03-02','2024-04-02','2024-05-02'):
   page.locator('#comparison-date').fill(value);page.locator('#comparison-date').dispatch_event('change')
  assert page.evaluate('Object.keys(Chart.instances).length')==12
  page.get_by_role('button',name='1D',exact=True).click();assert page.evaluate("Chart.getChart('pulse-chart').data.datasets[0].data.length")>=2
  assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
  body=page.locator('body').inner_text().lower()
  for private in ('private-person-name','private-home-address','private-email'):assert private not in body
  page.screenshot(path=str(ROOT/'test-results-dashboard.png'),full_page=True)
  mobile=browser.new_page(viewport={'width':390,'height':844});mobile.goto('http://127.0.0.1:8765',wait_until='networkidle');mobile.wait_for_function("document.documentElement.dataset.ready === 'true'");assert mobile.locator('.market-card').count()==10;assert mobile.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth');mobile.screenshot(path=str(ROOT/'test-results-dashboard-mobile.png'),full_page=True);mobile.close()
  stale_payload=json.loads((ROOT/'data'/'market-data.json').read_text());stale_payload['staleSeries']=[{'id':'sp500','reason':'test'}]
  stale=browser.new_page();stale.route('**/data/market-data.json*',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(stale_payload)));stale.goto('http://127.0.0.1:8765',wait_until='networkidle');stale.wait_for_function("document.documentElement.dataset.ready === 'true'");assert stale.locator('#stale-warning').is_visible();assert stale.locator('#stale-warning').inner_text()=='1 source stale';assert stale.locator('#update-status').get_attribute('class').endswith('has-stale');assert stale.locator('[data-market="sp500"] .stale-badge').inner_text().lower()=='stale';stale.close();browser.close()
 assert not errors,errors
 print('UI smoke tests passed: 10 cards, controls, date calculation, no overflow, no console errors')
finally:server.terminate();server.wait(timeout=5)
