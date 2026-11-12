"""Meridian Dispatch: RSS-based geography/timekeeping news digest."""
import argparse
import datetime as dt
import email.message
import hashlib
import html
import json
import logging
import os
from pathlib import Path
import re
import smtplib
import sqlite3
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

LOG = logging.getLogger('meridian_dispatch')
TZ = ZoneInfo('America/Los_Angeles')
QUERIES = {
    'Timekeeping': '"time zone" OR "daylight saving" OR "leap second"',
    'Boundaries': '"border dispute" OR "maritime boundary" OR "territorial waters"',
    'Cartography': 'cartography OR "new map" OR "historical atlas"',
    'Navigation': '"nautical chart" OR geodesy OR GNSS',
    'Historical geography': '"historical maps" OR "ancient borders" OR "old maps"',
    'Unusual geography': 'enclave OR exclave OR "disappearing island"',
}

KEYWORDS = ('time zone', 'daylight saving', 'calendar', 'leap second', 'date line', 'boundary',
            'border', 'maritime', 'cartograph', 'map', 'atlas', 'geograph', 'meridian',
            'latitude', 'longitude', 'navigation', 'geodes', 'gnss', 'gps', 'nautical',
            'enclave', 'exclave', 'coastline', 'island', 'territor', 'coordinate')

def load_env(path):
    if not path.exists(): return
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        key,value=line.split('=',1)
        if key.strip() not in os.environ:
            os.environ[key.strip()]=value.strip().strip('"').strip("'")

def fetch(query, days=3):
    q=f'{query} when:{days}d'
    url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q,'hl':'en-US','gl':'US','ceid':'US:en'})
    request=urllib.request.Request(url,headers={'User-Agent':'MeridianDispatch/1.0 (+RSS digest)'})
    with urllib.request.urlopen(request,timeout=25) as response:
        root=ET.fromstring(response.read())
    for item in root.findall('./channel/item'):
        title=item.findtext('title','').strip()
        link=item.findtext('link','').strip()
        source=item.findtext('source','').strip()
        date=item.findtext('pubDate','').strip()
        description=re.sub('<[^>]*>',' ',html.unescape(item.findtext('description','')))
        description=' '.join(description.split())
        if title and link:
            yield {'title':title,'url':link,'source':source,'published':date,'description':description}

def relevance(item):
    title=item['title'].lower()
    return sum(3 for k in KEYWORDS if k in title)+sum(1 for k in KEYWORDS if k in item['description'].lower())

def collect(days=3, max_items=10):
    candidates={}
    fetched=0; rejected=0; failures=0
    for category,query in QUERIES.items():
        try:
            category_count=0
            for item in fetch(query,days):
                fetched+=1; category_count+=1
                item['category']=category
                item['score']=relevance(item)
                if item['score'] < 1:
                    rejected+=1; continue
                normalized=re.sub(r'\W+','',item['title'].split(' - ')[0].lower())
                key=hashlib.sha256(normalized.encode()).hexdigest()
                if key not in candidates or candidates[key]['score'] < item['score']:
                    candidates[key]=item
            LOG.info('RSS %s: %d fetched',category,category_count)
        except Exception as exc:
            failures+=1
            LOG.warning('Feed failed for %s: %s',category,exc)
    LOG.info('Collection totals: fetched=%d rejected=%d unique=%d failed_feeds=%d',fetched,rejected,len(candidates),failures)
    if fetched==0:
        raise RuntimeError('All RSS feeds returned zero articles or failed; check network, Google News access and query responses')
    return sorted(candidates.values(),key=lambda x:x['score'],reverse=True)[:max_items*3]

def connect_db(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS seen (article_key TEXT PRIMARY KEY, first_seen TEXT NOT NULL)')
    return db

def article_key(item):
    return hashlib.sha256(re.sub(r'\W+','',item['title'].split(' - ')[0].lower()).encode()).hexdigest()

def select_new(db,items,max_items):
    result=[]
    for item in items:
        if db.execute('SELECT 1 FROM seen WHERE article_key=?',(article_key(item),)).fetchone(): continue
        result.append(item)
        if len(result)>=max_items: break
    return result

def summary(item):
    # Extractive headline-based summary, not an invented article synopsis.
    headline=item['title'].rsplit(' - ',1)[0]
    return headline.rstrip('.')+'.'

def render(items,stamp):
    heading=f'The Meridian Dispatch | {stamp}'
    md=[f'# {heading}','','Global timekeeping, boundaries, cartography, navigation and unusual geography.','',
        f'{len(items)} new item(s). Titles are RSS-derived; consult linked reporting for full details.','']
    blocks=[]
    for i,item in enumerate(items,1):
        title=item['title']; url=item['url']; category=item['category']
        md.extend([f'## {i}. {title}',f'**{category}** · {item["source"] or "Source unspecified"} · {item["published"]}',
                   '',summary(item),'',f'[Read original coverage]({url})',''])
        blocks.append(f'<section><h2>{i}. {html.escape(title)}</h2><p><small>{html.escape(category)} | {html.escape(item["source"])} | {html.escape(item["published"])}</small></p><p>{html.escape(summary(item))}</p><p><a href="{html.escape(url,quote=True)}">Read coverage</a></p></section>')
    if not items:
        md.append('No new matching stories found in this run.')
        blocks.append('<p>No new matching stories found in this run.</p>')
    body='<!doctype html><html><head><meta charset="utf-8"><style>body{font-family:system-ui,Arial,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;line-height:1.55;color:#1f2937}h1{color:#153b56}section{border-top:1px solid #ddd;padding:12px 0}small{color:#667085}</style></head><body><h1>'+html.escape(heading)+'</h1><p>Global geography and timekeeping intelligence</p>'+''.join(blocks)+'</body></html>'
    return '\n'.join(md)+'\n',body

def send_email(subject,html_body,md_body):
    host=os.environ.get('SMTP_HOST','')
    if not host: raise RuntimeError('SMTP_HOST is not configured')
    msg=email.message.EmailMessage()
    msg['Subject']=subject
    msg['From']=os.environ['EMAIL_FROM']
    msg['To']=os.environ['EMAIL_TO']
    msg.set_content(md_body)
    msg.add_alternative(html_body,subtype='html')
    port=int(os.environ.get('SMTP_PORT','587'))
    if os.environ.get('SMTP_SSL','false').lower()=='true':
        client=smtplib.SMTP_SSL(host,port,timeout=30)
    else:
        client=smtplib.SMTP(host,port,timeout=30)
    with client:
        if os.environ.get('SMTP_SSL','false').lower()!='true': client.starttls()
        if os.environ.get('SMTP_USER'): client.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
        client.send_message(msg)

def upload_nextcloud(files):
    base=os.environ.get('NEXTCLOUD_WEBDAV_URL','').rstrip('/')
    if not base: raise RuntimeError('NEXTCLOUD_WEBDAV_URL is not configured')
    import base64
    auth=base64.b64encode((os.environ['NEXTCLOUD_USER']+':'+os.environ['NEXTCLOUD_APP_PASSWORD']).encode()).decode()
    for file in files:
        url=base+'/'+urllib.parse.quote(file.name)
        req=urllib.request.Request(url,data=file.read_bytes(),method='PUT',headers={'Authorization':'Basic '+auth,'Content-Type':'application/octet-stream'})
        with urllib.request.urlopen(req,timeout=40) as response:
            LOG.info('Uploaded %s (%s)',file.name,response.status)

def main(argv=None):
    parser=argparse.ArgumentParser(description='Daily geography news digest')
    parser.add_argument('--env',default='.env')
    parser.add_argument('--data-dir',default=os.environ.get('MERIDIAN_DATA_DIR','./data'))
    parser.add_argument('--days',type=int,default=3)
    parser.add_argument('--max-items',type=int,default=10)
    parser.add_argument('--dry-run',action='store_true',help='Fetch and render without sending, uploading, or marking seen')
    parser.add_argument('--send-email',action='store_true')
    parser.add_argument('--upload-nextcloud',action='store_true')
    args=parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    load_env(Path(args.env))
    data_dir=Path(args.data_dir); out=data_dir/'reports'; out.mkdir(parents=True,exist_ok=True)
    now=dt.datetime.now(TZ); stamp=now.strftime('%Y-%m-%d')
    db=connect_db(data_dir/'articles.sqlite3')
    candidates=collect(args.days,args.max_items)
    items=select_new(db,candidates,args.max_items)
    LOG.info('Selection: candidates=%d new=%d previously_seen_or_over_limit=%d',len(candidates),len(items),len(candidates)-len(items))
    if not candidates: LOG.warning('No RSS candidates returned; check network/feed access')
    markdown,html_body=render(items,stamp)
    base=out/f'meridian-dispatch-{stamp}'
    paths=[base.with_suffix('.md'),base.with_suffix('.html'),base.with_suffix('.json')]
    paths[0].write_text(markdown,encoding='utf-8'); paths[1].write_text(html_body,encoding='utf-8')
    paths[2].write_text(json.dumps({'date':stamp,'timezone':str(TZ),'items':items},indent=2,ensure_ascii=False),encoding='utf-8')
    LOG.info('Wrote %s items to %s',len(items),out)
    if not args.dry_run:
        # Delivery errors stop execution; seen rows are committed only after all requested deliveries succeed.
        if args.send_email: send_email('The Meridian Dispatch | '+stamp,html_body,markdown)
        if args.upload_nextcloud: upload_nextcloud(paths)
        for item in items:
            db.execute('INSERT OR IGNORE INTO seen VALUES (?,?)',(article_key(item),now.isoformat()))
        db.commit()
    db.close()
    print(markdown)
    return 0

if __name__=='__main__': sys.exit(main())
