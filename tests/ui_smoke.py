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
  page.goto('http://127.0.0.1:8765',wait_until='networkidle');page.wait_for_function("document.documentElement.dataset.ready === 'true' && document.documentElement.dataset.newsReady === 'true'")

  # News is the default top-level view and every new stable story id begins unread.
  assert page.get_by_role('tab',name='News 5').get_attribute('aria-selected')=='true'
  assert page.locator('#news-panel').is_visible();assert not page.locator('#markets-panel').is_visible()
  assert page.locator('.news-story').count()==5
  assert page.locator('.news-story.is-unread').count()==5
  assert page.locator('#tab-unread-count').inner_text()=='5'
  assert page.locator('.source-link').count()==5
  for href in page.locator('.source-link').evaluate_all('(els)=>els.map(e=>e.href)'):
   assert href.startswith('https://') and 'utm_' not in href.lower(),href

  # Opening marks read; stars and read state survive a reload on this device.
  first=page.locator('.news-story').first;first_id=first.get_attribute('data-story-id');first.locator('.story-toggle').click();page.wait_for_timeout(50);assert first.locator('.story-body').is_visible();assert first.locator('.story-toggle').get_attribute('aria-expanded')=='true';assert page.locator('#tab-unread-count').inner_text()=='4';assert page.evaluate("document.activeElement.matches('.story-toggle') && document.activeElement.closest('[data-story-id]').dataset.storyId") == first_id
  first.locator('.star-toggle').click();page.wait_for_timeout(50);assert page.locator('.news-story').first.locator('.star-toggle').get_attribute('aria-pressed')=='true';assert page.evaluate("document.activeElement.matches('.star-toggle') && document.activeElement.closest('[data-story-id]').dataset.storyId") == first_id;assert 'added to Starred' in page.locator('#news-status').inner_text()
  page.reload(wait_until='networkidle');page.wait_for_function("document.documentElement.dataset.newsReady === 'true'");assert page.locator('#tab-unread-count').inner_text()=='4';assert page.locator('#filter-starred-count').inner_text()=='1'
  page.get_by_role('button',name='Starred 1').click();assert page.locator('.news-story').count()==1
  page.get_by_role('button',name='Inbox').click();page.locator('#mark-all-read').click();assert page.locator('#tab-unread-count').inner_text()=='0';page.get_by_role('button',name='Unread 0').click();assert page.locator('.news-story').count()==0;assert page.locator('#news-empty').is_visible()

  # ARIA tabs support keyboard navigation; existing market dashboard remains intact.
  page.get_by_role('tab',name='News 0').focus();page.keyboard.press('ArrowRight');assert page.get_by_role('tab',name='Markets').get_attribute('aria-selected')=='true';assert page.locator('#markets-panel').is_visible()
  assert page.get_by_role('heading',name='The world market, at a glance.').count()==1
  assert page.locator('.market-card').count()==10
  assert page.locator('[data-range]').count()==10
  assert page.locator('#updated-exact').inner_text()!='—';assert 'Data through' in page.locator('#data-as-of').inner_text()
  before=page.locator('#average-change').inner_text();page.locator('#comparison-date').fill('2024-01-02');page.locator('#comparison-date').dispatch_event('change');page.wait_for_timeout(200);after=page.locator('#average-change').inner_text();assert after!='—' and after!=before
  page.get_by_role('button',name='3Y',exact=True).click();assert page.get_by_role('button',name='3Y',exact=True).get_attribute('aria-pressed')=='true'
  chart_ranges=page.evaluate("Chart.getChart('comparison-chart').data.datasets.map(d=>{const ys=d.data.map(p=>p.y);return Math.max(...ys)-Math.min(...ys)})");assert max(chart_ranges)>5,chart_ranges
  assert page.evaluate('Object.keys(Chart.instances).length')==12
  latest=page.locator('#comparison-date').get_attribute('max');page.locator('#comparison-date').fill(latest);page.locator('#comparison-date').dispatch_event('change');page.wait_for_timeout(100);assert page.locator('#average-change').inner_text()!='—';assert page.locator('#advancing-count').inner_text().endswith('/ 10')
  page.locator('#comparison-date').fill('');page.locator('#comparison-date').dispatch_event('change');page.wait_for_timeout(100);assert page.locator('#comparison-date').input_value()
  for value in ('2024-01-02','2024-02-02','2024-03-02','2024-04-02','2024-05-02'):
   page.locator('#comparison-date').fill(value);page.locator('#comparison-date').dispatch_event('change')
  assert page.evaluate('Object.keys(Chart.instances).length')==12
  page.get_by_role('button',name='1D',exact=True).click();assert page.evaluate("Chart.getChart('pulse-chart').data.datasets[0].data.length")>=2
  assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
  page.get_by_role('tab',name='News 0').click();page.evaluate("localStorage.removeItem('global-market-pulse:news-state:v1')");page.reload(wait_until='networkidle');page.wait_for_function("document.documentElement.dataset.newsReady === 'true'");page.screenshot(path=str(ROOT/'test-results-dashboard.png'),full_page=True)

  mobile=browser.new_page(viewport={'width':390,'height':844});mobile.goto('http://127.0.0.1:8765',wait_until='networkidle');mobile.wait_for_function("document.documentElement.dataset.ready === 'true' && document.documentElement.dataset.newsReady === 'true'");assert mobile.locator('.news-story').count()==5;assert mobile.locator('#news-panel').is_visible();assert mobile.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth');mobile.screenshot(path=str(ROOT/'test-results-dashboard-mobile.png'),full_page=True);mobile.close()

  archive_payload=json.loads((ROOT/'data'/'economic-news.json').read_text());archived=dict(archive_payload['stories'][0]);archived['id']='archived-star-test';archive_payload['archive']=[archived]
  archived_page=browser.new_page();archived_page.add_init_script("localStorage.setItem('global-market-pulse:news-state:v1', JSON.stringify({readIds:['archived-star-test'],starredIds:['archived-star-test']}))");archived_page.route('**/data/economic-news.json*',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(archive_payload)));archived_page.goto('http://127.0.0.1:8765',wait_until='networkidle');archived_page.wait_for_function("document.documentElement.dataset.newsReady === 'true'");assert archived_page.locator('#filter-starred-count').inner_text()=='1';archived_page.get_by_role('button',name='Starred 1').click();assert archived_page.locator('[data-story-id="archived-star-test"]').count()==1;archived_page.locator('[data-story-id="archived-star-test"] .star-toggle').click();archived_page.wait_for_timeout(50);assert archived_page.locator('.news-story').count()==0;assert archived_page.evaluate("document.activeElement.dataset.newsFilter")=='starred';archived_page.close()

  stale_news_payload=json.loads((ROOT/'data'/'economic-news.json').read_text());stale_news_payload['briefingStale']=True;stale_news_payload['staleSources']=[{'source':'Briefing refresh','reason':'offline'}]
  stale_news=browser.new_page();stale_news.route('**/data/economic-news.json*',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(stale_news_payload)));stale_news.goto('http://127.0.0.1:8765',wait_until='networkidle');stale_news.wait_for_function("document.documentElement.dataset.newsReady === 'true'");assert stale_news.locator('#news-stale-warning').is_visible();assert 'Briefing is stale' in stale_news.locator('#news-stale-warning').inner_text();stale_news.close()

  stale_payload=json.loads((ROOT/'data'/'market-data.json').read_text());stale_payload['staleSeries']=[{'id':'sp500','reason':'test'}]
  stale=browser.new_page();stale.route('**/data/market-data.json*',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(stale_payload)));stale.goto('http://127.0.0.1:8765/#markets',wait_until='networkidle');stale.wait_for_function("document.documentElement.dataset.ready === 'true'");assert stale.locator('#stale-warning').is_visible();assert stale.locator('#stale-warning').inner_text()=='1 source stale';assert stale.locator('[data-market="sp500"] .stale-badge').inner_text().lower()=='stale';stale.close();browser.close()
  assert not errors,errors
 print('UI smoke passed: news inbox state, tabs, 10 markets, desktop/mobile, no console errors')
finally:server.terminate();server.wait(timeout=5)
