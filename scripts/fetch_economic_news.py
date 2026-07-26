#!/usr/bin/env python3
"""Build a small, high-signal economics news artifact from editorial seeds and official RSS feeds."""
from __future__ import annotations
import hashlib,html,json,re,sys,urllib.parse,urllib.request,xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'economic-news.json';EDITORIAL=ROOT/'data'/'news-editorial.json'
USER_AGENT='GlobalMarketPulse/1.0 (+https://github.com/filipoclawi/global-market-pulse)'
MAX_STORIES=8;WINDOW_DAYS=10;ARCHIVE_DAYS=180;MAX_ARCHIVE=100

@dataclass(frozen=True)
class Source:
 name:str;url:str;base_score:int

SOURCES=(
 Source('Federal Reserve','https://www.federalreserve.gov/feeds/press_all.xml',6),
 Source('European Central Bank','https://www.ecb.europa.eu/rss/press.html',6),
 Source('U.S. Bureau of Economic Analysis','https://apps.bea.gov/rss/rss.xml',5),
 Source('Bank of England','https://www.bankofengland.co.uk/rss/news',5),
 Source('NPR','https://feeds.npr.org/1006/rss.xml',4),
 Source('BBC News','https://feeds.bbci.co.uk/news/business/rss.xml',4),
)
GOOD={
 'monetary policy':9,'interest rate':8,'inflation':8,'gdp':8,'economic outlook':8,
 'financial stability':7,'personal income and outlays':7,
 'international trade':6,'credit conditions':6,'employment':6,'labour market':6,
 'tariff':8,'oil price':7,'energy price':7,'recession':7,
}
BAD={'enforcement':-14,'appointment':-12,'appoints':-12,'fine':-12,'consults':-7,'technical':-7,'banknotes':-8,'meeting minutes':-4,'letter from':-8,'speech':-4,'decisions taken':-20,'with q&a':-10}
LENSES={
 'Rates':'Bond prices and borrowing costs are most sensitive to the path of policy rates. For a long-term portfolio, the useful question is whether the news changes expected inflation and the likely neutral rate—not whether one meeting surprises markets.',
 'Inflation':'Persistent inflation can keep bond yields higher and reduce the diversification benefit of nominal bonds during supply shocks. The practical response is usually broad diversification and an intentional duration mix, not a reaction to one data point.',
 'Growth':'Growth affects corporate earnings and credit risk, while slower growth can eventually support high-quality bonds. Treat one release as evidence for the cycle, not as a stand-alone signal to switch asset classes.',
 'Credit':'Tighter credit can slow investment and consumption with a lag. That can pressure risky assets while improving the relative role of high-quality bonds, but the direction depends on whether inflation is also cooling.',
 'Trade':'Trade restrictions can raise costs and weaken growth at the same time. This argues for geographic diversification and for avoiding a portfolio that depends on one inflation or policy outcome.',
}
class NewsFetchError(RuntimeError):
 def __init__(self,message,stale_sources=None):super().__init__(message);self.stale_sources=stale_sources or []

def iso(dt):return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def strip_html(value):
 text=re.sub(r'<[^>]+>',' ',html.unescape(value or ''));return re.sub(r'\s+',' ',text).strip()
def clean_url(url):
 p=urllib.parse.urlsplit((url or '').strip());q=urllib.parse.parse_qsl(p.query,keep_blank_values=True)
 q=sorted((k,v) for k,v in q if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid','mc_cid','mc_eid'})
 path=re.sub(r'/+','/',p.path)
 return urllib.parse.urlunsplit(('https' if p.scheme=='http' else p.scheme,p.netloc.lower(),path,urllib.parse.urlencode(q),'')).rstrip('/')
def stable_id(url,title=''):return hashlib.sha256(clean_url(url).encode()).hexdigest()[:16]
def parse_date(value):
 if not value:return None
 try:
  dt=parsedate_to_datetime(value)
  if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
  return dt.astimezone(timezone.utc)
 except Exception:
  try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)
  except Exception:return None
def parse_day(value):
 try:return datetime.strptime(value,'%Y-%m-%d').date()
 except (TypeError,ValueError):return None
def sentence_clip(text,limit=900):
 text=strip_html(text)
 if len(text)<=limit:return text
 clipped=text[:limit].rsplit(' ',1)[0]
 return clipped.rstrip(' ,;:')+'…'
def classify(title,description=''):
 text=(title+' '+description).lower();tags=[]
 for tag,words in [('Rates',('rate','monetary','central bank')),('Inflation',('inflation','price','energy')),('Growth',('gdp','growth','income','outlook')),('Credit',('credit','lending','financial stability')),('Trade',('trade','tariff','export','import'))]:
  if any(w in text for w in words):tags.append(tag)
 return tags[:4] or ['Macro']
def score(title):
 text=title.lower();return sum(v for k,v in GOOD.items() if k in text)+sum(v for k,v in BAD.items() if k in text)
def title_tokens(title):
 stop={'a','an','and','are','as','at','by','for','from','in','is','of','on','the','to','with','new'}
 return {token for token in re.findall(r'[a-z0-9]+',title.lower()) if len(token)>2 and token not in stop}
def title_similarity(a,b):
 left,right=title_tokens(a),title_tokens(b)
 return len(left&right)/len(left|right) if left and right else 0
def event_key(story):
 text=story['title'].lower();source=story['sourceLabel'].lower()
 scope='ecb' if 'central bank' in source else 'fed' if 'federal reserve' in source else 'boe' if 'bank of england' in source else 'bea' if 'economic analysis' in source else ''
 if 'tariff' in text:return 'tariffs'
 if any(word in text for word in ('oil','crude','energy price')):return 'oil'
 for key,terms in [('policy',('monetary policy','interest rate','rate decision')),('inflation',('inflation','consumer price')),('growth',('gdp','growth','economic outlook')),('jobs',('employment','labour market','jobs report'))]:
  if any(term in text for term in terms):return f'{scope}:{key}' if scope else key
 return None
def lens(tags):
 return next((LENSES[t] for t in tags if t in LENSES),'The long-term value is in whether this changes expected growth, inflation or the cost of capital. It is an input to diversification and rebalancing—not a reason for a rushed trade.')
def fetch_source(source):
 req=urllib.request.Request(source.url,headers={'User-Agent':USER_AGENT,'Accept':'application/rss+xml, application/xml, text/xml'})
 try:
  with urllib.request.urlopen(req,timeout=25) as response:raw=response.read(2_000_000)
  root=ET.fromstring(raw)
 except Exception as exc:raise NewsFetchError(f'{source.name}: {exc}') from exc
 items=[]
 for node in root.findall('.//item'):
  title=strip_html(node.findtext('title'));url=clean_url(node.findtext('link') or '')
  published=parse_date(node.findtext('pubDate') or node.findtext('date') or '')
  desc=strip_html(node.findtext('description') or '')
  if title and url and published:items.append({'title':title,'url':url,'published':published,'description':desc,'source':source})
 return items

def automated_story(item):
 tags=classify(item['title'],item['description']);summary=sentence_clip(item['description'],850)
 if not summary:summary=f"{item['source'].name} published this update. Open the source for the underlying release and methodology."
 preview=sentence_clip(summary,230)
 return {'id':stable_id(item['url'],item['title']),'title':item['title'],'preview':preview,'summary':summary,'whyItMatters':lens(tags),'publishedAt':iso(item['published']),'sourceLabel':item['source'].name,'sourceUrl':item['url'],'tags':tags,'readingMinutes':1,'editorial':False}
def load_json(path,default):
 try:return json.loads(path.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return default

def validate_document(doc):
 if doc.get('schemaVersion')!=1:raise ValueError('unsupported news schema')
 generated=parse_date(doc.get('generatedAt'));checked=parse_date(doc.get('checkedAt'))
 if not generated or not checked:raise ValueError('generatedAt and checkedAt must be valid timestamps')
 data_day,window_day=parse_day(doc.get('dataAsOf')),parse_day(doc.get('windowStart'))
 if not data_day or not window_day or (window_day>data_day and not doc.get('briefingStale')):raise ValueError('invalid dataAsOf/windowStart dates')
 if not isinstance(doc.get('sourcesChecked'),list) or not all(isinstance(x,str) and x for x in doc['sourcesChecked']):raise ValueError('sourcesChecked must be a string list')
 stale=doc.get('staleSources')
 if not isinstance(stale,list) or not all(isinstance(x,dict) and isinstance(x.get('source'),str) and isinstance(x.get('reason'),str) for x in stale):raise ValueError('invalid staleSources')
 if 'lastAttemptAt' in doc and not parse_date(doc['lastAttemptAt']):raise ValueError('invalid lastAttemptAt')
 if 'briefingStale' in doc and not isinstance(doc['briefingStale'],bool):raise ValueError('briefingStale must be boolean')
 if 'freshStoryCount' in doc and (not isinstance(doc['freshStoryCount'],int) or doc['freshStoryCount']<0):raise ValueError('invalid freshStoryCount')
 stories=doc.get('stories') or []
 if not isinstance(stories,list):raise ValueError('stories must be a list')
 if not 4<=len(stories)<=MAX_STORIES:raise ValueError('news artifact must contain 4-8 stories')
 archive=doc.get('archive') or []
 if not isinstance(archive,list):raise ValueError('archive must be a list')
 if len(archive)>MAX_ARCHIVE:raise ValueError('news archive is too large')
 ids=[]
 for story in stories+archive:
  for key in ('id','title','preview','summary','whyItMatters','publishedAt','sourceLabel','sourceUrl','tags','readingMinutes'):
   if not story.get(key):raise ValueError(f'missing {key}')
  if not story['sourceUrl'].startswith('https://'):raise ValueError('source URL must use HTTPS')
  if story['readingMinutes'] not in (1,2):raise ValueError('reading time must be 1-2 minutes')
  if not isinstance(story['tags'],list) or not 1<=len(story['tags'])<=4 or not all(isinstance(tag,str) and tag for tag in story['tags']):raise ValueError('invalid story tags')
  published=parse_date(story['publishedAt'])
  if not published or published>checked+timedelta(hours=2):raise ValueError('invalid or future publishedAt')
  if len((story['summary']+' '+story['whyItMatters']).split())>360:raise ValueError('story exceeds two-minute limit')
  ids.append(story['id'])
 if len(ids)!=len(set(ids)):raise ValueError('duplicate story ids across inbox and archive')
 if data_day!=max(parse_date(story['publishedAt']).date() for story in stories):raise ValueError('dataAsOf must match newest inbox story')
 return doc

def build_document(existing=None,now=None):
 now=now or datetime.now(timezone.utc);window=now-timedelta(days=WINDOW_DAYS);items=[];errors=[];checked=[]
 for source in SOURCES:
  try:items.extend(fetch_source(source));checked.append(source.name)
  except NewsFetchError as exc:errors.append({'source':source.name,'reason':str(exc)[:180]})
 if not checked:raise NewsFetchError('all economics news sources failed; preserving last-known-good artifact',errors)
 editorial=load_json(EDITORIAL,{}).get('stories',[]);stories=[]
 for story in editorial:
  dt=parse_date(story.get('publishedAt'))
  if dt and dt>=window:stories.append(story)
 candidates=[]
 for item in items:
  if window<=item['published']<=now+timedelta(hours=2):
   value=item['source'].base_score+score(item['title'])
   if value>=11:candidates.append((value,item['published'],automated_story(item)))
 candidates.sort(key=lambda x:(x[0],x[1]),reverse=True)
 seen={s['id'] for s in stories};seen_titles={re.sub(r'\W+',' ',s['title'].lower()).strip() for s in stories}
 seen_urls={clean_url(s['sourceUrl']) for s in stories};seen_events=[(parse_date(s['publishedAt']),event_key(s),s['title']) for s in stories]
 source_counts={name:sum(1 for story in stories if story['sourceLabel']==name) for name in {story['sourceLabel'] for story in stories}}
 for _,_,story in candidates:
  title_key=re.sub(r'\W+',' ',story['title'].lower()).strip();url_key=clean_url(story['sourceUrl']);story_date=parse_date(story['publishedAt']);key=event_key(story)
  duplicate_event=any(abs((story_date-seen_date).total_seconds())<=3*86400 and ((key and key==seen_key) or title_similarity(story['title'],seen_title)>=.24) for seen_date,seen_key,seen_title in seen_events if seen_date)
  if story['id'] not in seen and title_key not in seen_titles and url_key not in seen_urls and not duplicate_event and source_counts.get(story['sourceLabel'],0)<2:
   stories.append(story);seen.add(story['id']);seen_titles.add(title_key);seen_urls.add(url_key);seen_events.append((story_date,key,story['title']));source_counts[story['sourceLabel']]=source_counts.get(story['sourceLabel'],0)+1
  if len(stories)>=MAX_STORIES:break
 fresh_story_count=len(stories)
 if len(stories)<4 and existing:
  fallback_cutoff=now-timedelta(days=30)
  for story in existing.get('stories',[]):
   published=parse_date(story.get('publishedAt'))
   if story.get('id') not in seen and published and published>=fallback_cutoff:stories.append(story);seen.add(story.get('id'))
   if len(stories)>=4:break
 stories=sorted(stories[:MAX_STORIES],key=lambda s:s['publishedAt'],reverse=True)
 if len(stories)<4:raise NewsFetchError('fewer than four current stories; preserving last-known-good artifact')
 briefing_stale=fresh_story_count<4 or any(parse_date(story['publishedAt'])<window for story in stories)
 active_ids={s['id'] for s in stories};archive_cutoff=now-timedelta(days=ARCHIVE_DAYS);archive=[];archive_seen=set()
 for story in ((existing or {}).get('stories',[])+(existing or {}).get('archive',[])):
  published=parse_date(story.get('publishedAt'))
  if story.get('id') not in active_ids and story.get('id') not in archive_seen and published and published>=archive_cutoff:
   archive.append(story);archive_seen.add(story['id'])
 archive=sorted(archive,key=lambda s:s['publishedAt'],reverse=True)[:MAX_ARCHIVE]
 content_fingerprint=[(s['id'],s['title'],s['summary']) for s in stories+archive]
 old_fingerprint=[(s.get('id'),s.get('title'),s.get('summary')) for s in ((existing or {}).get('stories',[])+(existing or {}).get('archive',[]))]
 generated=existing.get('generatedAt') if existing and content_fingerprint==old_fingerprint else iso(now)
 doc={'schemaVersion':1,'generatedAt':generated or iso(now),'checkedAt':iso(now),'lastAttemptAt':iso(now),'dataAsOf':max(s['publishedAt'][:10] for s in stories),'windowStart':window.date().isoformat(),'refreshCadenceHours':6,'sourcesChecked':checked,'staleSources':errors,'briefingStale':briefing_stale,'freshStoryCount':fresh_story_count,'stories':stories,'archive':archive}
 return validate_document(doc)
def main():
 existing=load_json(OUT,None)
 try:doc=build_document(existing);OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(doc,indent=2,ensure_ascii=False)+'\n');print(f"Wrote {len(doc['stories'])} stories to {OUT}")
 except NewsFetchError as exc:
  if existing:
   validate_document(existing);failed=dict(existing);failed['lastAttemptAt']=iso(datetime.now(timezone.utc));failed['briefingStale']=True;failed['staleSources']=exc.stale_sources or [{'source':'Briefing refresh','reason':str(exc)[:180]}];OUT.write_text(json.dumps(validate_document(failed),indent=2,ensure_ascii=False)+'\n');print(f'{exc}; preserving {OUT}',file=sys.stderr);return
  print(str(exc),file=sys.stderr);raise SystemExit(1)
if __name__=='__main__':main()
