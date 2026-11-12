from urllib.parse import urlsplit,urlunsplit,parse_qs,urlencode

def source_key(url):
    parsed=urlsplit(url);host=(parsed.hostname or '').lower().removeprefix('www.');query=parse_qs(parsed.query)
    if host in {'youtu.be','youtube.com','m.youtube.com','music.youtube.com'}:
        identity=parsed.path.strip('/') if host=='youtu.be' else query.get('v',[None])[0]
        if parsed.path.startswith(('/shorts/','/embed/')):identity=parsed.path.split('/')[2]
        if identity:return 'youtube:'+identity
    filtered=[(k,v) for k,values in query.items() if not k.startswith('utm_') and k not in {'si','fbclid'} for v in values]
    return urlunsplit((parsed.scheme.lower(),host,parsed.path,urlencode(sorted(filtered)),''))

def same_output(record,url,kind,container,quality,start=None,finish=None):
    metadata=record.get('metadata',record)
    return source_key(record.get('url',''))==source_key(url) and record.get('kind')==kind and metadata.get('container')==container and metadata.get('quality')==quality and metadata.get('clip_start')==start and metadata.get('clip_end')==finish

def already_have(url,kind,container,quality,start=None,finish=None):
    from .jobs import jobs
    from .media_library import library
    for item in jobs.list():
        if item['purpose']=='download' and item['status'] not in {'failed','cancelled'} and same_output(item,url,kind,container,quality,start,finish):
            if item['status']!='completed' or jobs.get(item['id']).filename and __import__('pathlib').Path(jobs.get(item['id']).filename).exists():return True
    for item in library.list():
        if item['exists'] and item['metadata'].get('purpose','download')=='download' and same_output(item,url,kind,container,quality,start,finish):return True
    return False

def output_key(url,kind,container,quality,start=None,finish=None):return (source_key(url),kind,container,quality,start,finish)
def existing_keys():
    from .jobs import jobs
    from .media_library import library
    from pathlib import Path
    keys=set()
    for item in jobs.list():
        if item['purpose']=='download' and item['status'] not in {'failed','cancelled'}:
            raw=jobs.get(item['id'])
            if item['status']!='completed' or raw.filename and Path(raw.filename).is_file():keys.add(output_key(item['url'],item['kind'],item['container'],item['quality'],item['clip_start'],item['clip_end']))
    for item in library.list():
        metadata=item['metadata']
        if item['exists'] and metadata.get('purpose','download')=='download':keys.add(output_key(item['url'],item['kind'],metadata.get('container'),metadata.get('quality'),metadata.get('clip_start'),metadata.get('clip_end')))
    return keys
