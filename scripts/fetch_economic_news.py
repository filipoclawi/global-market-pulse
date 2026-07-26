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
class NewsFetchError(RuntimeError):pass

def iso(dt):return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def strip_html(value):
 text=re.sub(r'<[^>]+>',' ',html.unescape(value or ''));return re.sub(r'\s+',' ',text).strip()
def clean_url(url):
 p=urllib.parse.urlsplit((url or '').strip());q=urllib.parse.parse_qsl(p.query,keep_blank_values=True)
 q=[(k,v) for k,v in q if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid','mc_cid','mc_eid'}]
 path=re.sub(r'/+','/',p.path)
 return urllib.parse.urlunsplit(('https' if p.scheme=='http' else p.scheme,p.netloc.lower(),path,urllib.parse.urlencode(q),'')).rstrip('/')
def stable_id(url,title):return hashlib.sha256((clean_url(url)+'|'+re.sub(r'\W+',' ',title.lower()).strip()).encode()).hexdigest()[:16]
def parse_date(value):
 if not value:return None
 try:
  dt=parsedate_to_datetime(value)
  if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
  return dt.astimezone(timezone.utc)
 except Exception:
  try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)
  except Exception:return None
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
  if len((story['summary']+' '+story['whyItMatters']).split())>360:raise ValueError('story exceeds two-minute limit')
  ids.append(story['id'])
 if len(ids)!=len(set(ids)):raise ValueError('duplicate story ids across inbox and archive')
 return doc

def build_document(existing=None,now=None):
 now=now or datetime.now(timezone.utc);window=now-timedelta(days=WINDOW_DAYS);items=[];errors=[];checked=[]
 for source in SOURCES:
  try:items.extend(fetch_source(source));checked.append(source.name)
  except NewsFetchError as exc:errors.append({'source':source.name,'reason':str(exc)[:180]})
 if not checked:raise NewsFetchError('all economics news sources failed; preserving last-known-good artifact')
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
 seen_urls={clean_url(s['sourceUrl']) for s in stories}
 seen_clusters={(s['sourceLabel'],s['publishedAt'][:10],tag) for s in stories for tag in s.get('tags',[])}
 seen_topics=[(parse_date(s['publishedAt']),set(s.get('tags',[]))) for s in stories]
 for _,_,story in candidates:
  title_key=re.sub(r'\W+',' ',story['title'].lower()).strip()
  url_key=clean_url(story['sourceUrl']);clustered=any((story['sourceLabel'],story['publishedAt'][:10],tag) in seen_clusters for tag in story['tags'])
  story_date=parse_date(story['publishedAt']);topic_clustered=any(abs((story_date-seen_date).total_seconds())<=3*86400 and set(story['tags'])&tags for seen_date,tags in seen_topics if seen_date)
  if story['id'] not in seen and title_key not in seen_titles and url_key not in seen_urls and not clustered and not topic_clustered:
   stories.append(story);seen.add(story['id']);seen_titles.add(title_key);seen_urls.add(url_key)
   seen_clusters.update((story['sourceLabel'],story['publishedAt'][:10],tag) for tag in story['tags'])
   seen_topics.append((story_date,set(story['tags'])))
  if len(stories)>=MAX_STORIES:break
 if len(stories)<4 and existing:
  for story in existing.get('stories',[]):
   if story.get('id') not in seen:stories.append(story);seen.add(story.get('id'))
   if len(stories)>=4:break
 stories=sorted(stories[:MAX_STORIES],key=lambda s:s['publishedAt'],reverse=True)
 if len(stories)<4:raise NewsFetchError('fewer than four valid stories; preserving last-known-good artifact')
 active_ids={s['id'] for s in stories};archive_cutoff=now-timedelta(days=ARCHIVE_DAYS);archive=[];archive_seen=set()
 for story in ((existing or {}).get('stories',[])+(existing or {}).get('archive',[])):
  published=parse_date(story.get('publishedAt'))
  if story.get('id') not in active_ids and story.get('id') not in archive_seen and published and published>=archive_cutoff:
   archive.append(story);archive_seen.add(story['id'])
 archive=sorted(archive,key=lambda s:s['publishedAt'],reverse=True)[:MAX_ARCHIVE]
 content_fingerprint=[(s['id'],s['title'],s['summary']) for s in stories+archive]
 old_fingerprint=[(s.get('id'),s.get('title'),s.get('summary')) for s in ((existing or {}).get('stories',[])+(existing or {}).get('archive',[]))]
 generated=existing.get('generatedAt') if existing and content_fingerprint==old_fingerprint else iso(now)
 doc={'schemaVersion':1,'generatedAt':generated or iso(now),'checkedAt':iso(now),'dataAsOf':max(s['publishedAt'][:10] for s in stories),'windowStart':window.date().isoformat(),'refreshCadenceHours':6,'sourcesChecked':checked,'staleSources':errors,'stories':stories,'archive':archive}
 return validate_document(doc)
def main():
 existing=load_json(OUT,None)
 try:doc=build_document(existing);OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(doc,indent=2,ensure_ascii=False)+'\n');print(f"Wrote {len(doc['stories'])} stories to {OUT}")
 except NewsFetchError as exc:
  if existing:
   validate_document(existing);print(f'{exc}; preserving {OUT}',file=sys.stderr);return
  print(str(exc),file=sys.stderr);raise SystemExit(1)
if __name__=='__main__':main()
