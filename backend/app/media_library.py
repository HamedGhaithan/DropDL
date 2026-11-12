"""Durable file catalogue, independent of the task queue."""
import json
import sqlite3
import time
from pathlib import Path
from threading import Lock
from uuid import uuid4
from .settings import CONFIG_ROOT

class MediaLibrary:
    def __init__(self,path):
        self.path=Path(path);self.lock=Lock()
    def connection(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=15)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('CREATE TABLE IF NOT EXISTS media (id TEXT PRIMARY KEY,path TEXT UNIQUE,title TEXT,kind TEXT,site TEXT,url TEXT,owned INTEGER,created REAL,metadata TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS removed (path TEXT PRIMARY KEY)')
        db.execute('CREATE TABLE IF NOT EXISTS collections (id TEXT PRIMARY KEY,name TEXT UNIQUE COLLATE NOCASE,created REAL)')
        db.execute('CREATE TABLE IF NOT EXISTS media_notes (media_id TEXT PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE,favorite INTEGER NOT NULL DEFAULT 0,collection_id TEXT REFERENCES collections(id) ON DELETE SET NULL,display_title TEXT)')
        return db
    def add(self,path,*,title='',kind='video',site='Local',url='',owned=False,metadata=None,ignore_removed=False):
        path=Path(path).resolve()
        if not path.is_file():raise ValueError('The media file is missing.')
        with self.lock,self.connection() as db:
            if ignore_removed and db.execute('SELECT path FROM removed WHERE path=?',(str(path),)).fetchone():return None
            db.execute('DELETE FROM removed WHERE path=?',(str(path),))
            old=db.execute('SELECT id,metadata FROM media WHERE path=?',(str(path),)).fetchone()
            identity=old['id'] if old else uuid4().hex
            metadata={**(json.loads(old['metadata']) if old else {}),**(metadata or {})}
            db.execute('INSERT INTO media VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET title=excluded.title,metadata=excluded.metadata',
                (identity,str(path),title or path.stem,kind,site,url,int(owned),time.time(),json.dumps(metadata or {},ensure_ascii=False)))
        return self.get(identity)
    def get(self,identity):
        with self.connection() as db:row=db.execute('SELECT m.*,n.favorite,n.collection_id,n.display_title,c.name AS collection_name FROM media m LEFT JOIN media_notes n ON n.media_id=m.id LEFT JOIN collections c ON c.id=n.collection_id WHERE m.id=?',(identity,)).fetchone()
        return self.public(row) if row else None
    def public(self,row):
        result=dict(row);p=Path(result['path']);result['metadata']=json.loads(result['metadata']);result['exists']=p.is_file();result['size']=0;result['filename']=p.name
        try:result['size']=p.stat().st_size if result['exists'] else 0
        except OSError:result['exists']=False
        result['owned']=bool(result['owned']);result['favorite']=bool(result.get('favorite'));result['collection_id']=result.get('collection_id');result['collection_name']=result.get('collection_name');result['title']=result.pop('display_title',None) or result['title'];return result
    def list(self):
        with self.connection() as db:rows=db.execute('SELECT m.*,n.favorite,n.collection_id,n.display_title,c.name AS collection_name FROM media m LEFT JOIN media_notes n ON n.media_id=m.id LEFT JOIN collections c ON c.id=n.collection_id ORDER BY m.created DESC,m.id').fetchall()
        return [self.public(row) for row in rows]
    def collections(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT c.*,COUNT(n.media_id) AS count FROM collections c LEFT JOIN media_notes n ON n.collection_id=c.id GROUP BY c.id ORDER BY c.name COLLATE NOCASE')]
    def save_collection(self,name,identity=None):
        name=name.strip()
        if not name or len(name)>60:raise ValueError('Use a collection name between 1 and 60 characters.')
        try:
            with self.lock,self.connection() as db:
                if identity:
                    if not db.execute('SELECT id FROM collections WHERE id=?',(identity,)).fetchone():raise ValueError('Collection not found.')
                    db.execute('UPDATE collections SET name=? WHERE id=?',(name,identity))
                else:
                    if db.execute('SELECT COUNT(*) FROM collections').fetchone()[0]>=100:raise ValueError('Maximum 100 collections.')
                    identity=uuid4().hex;db.execute('INSERT INTO collections VALUES (?,?,?)',(identity,name,time.time()))
        except sqlite3.IntegrityError as exc:raise ValueError('A collection with this name already exists.') from exc
        return next(c for c in self.collections() if c['id']==identity)
    def remove_collection(self,identity):
        with self.lock,self.connection() as db:
            if not db.execute('DELETE FROM collections WHERE id=?',(identity,)).rowcount:raise ValueError('Collection not found.')
    def organize(self,identities,*,favorite=None,collection_id=None,change_collection=False,title=None):
        identities=list(dict.fromkeys(identities))
        if not identities or len(identities)>500:raise ValueError('Choose 1 to 500 files.')
        if title is not None and (len(identities)!=1 or not title.strip() or len(title)>200):raise ValueError('Use a display title between 1 and 200 characters for one file.')
        with self.lock,self.connection() as db:
            if change_collection and collection_id is not None and not db.execute('SELECT id FROM collections WHERE id=?',(collection_id,)).fetchone():raise ValueError('Collection not found.')
            for identity in identities:
                if not db.execute('SELECT id FROM media WHERE id=?',(identity,)).fetchone():raise ValueError('Media not found.')
            for identity in identities:
                db.execute('INSERT OR IGNORE INTO media_notes(media_id) VALUES (?)',(identity,))
                if favorite is not None:db.execute('UPDATE media_notes SET favorite=? WHERE media_id=?',(int(favorite),identity))
                if change_collection:db.execute('UPDATE media_notes SET collection_id=? WHERE media_id=?',(collection_id,identity))
                if title is not None:db.execute('UPDATE media_notes SET display_title=? WHERE media_id=?',(title.strip(),identity))
        return [self.get(identity) for identity in identities]
    def cache_info(self,identity,path,metadata):
        with self.lock,self.connection() as db:
            row=db.execute('SELECT metadata FROM media WHERE id=? AND path=?',(identity,str(path))).fetchone()
            if row:db.execute('UPDATE media SET metadata=? WHERE id=?',(json.dumps({**json.loads(row['metadata']),**metadata},ensure_ascii=False),identity))
    def relink(self,identity,path,metadata):
        path=Path(path).resolve()
        if not path.is_file():raise ValueError('The replacement file is missing.')
        with self.lock,self.connection() as db:
            row=db.execute('SELECT * FROM media WHERE id=?',(identity,)).fetchone()
            if not row:raise ValueError('Media not found.')
            if Path(row['path']).is_file():raise ValueError('Relink is only available for missing files.')
            other=db.execute('SELECT id FROM media WHERE path=?',(str(path),)).fetchone()
            if other and other['id']!=identity:raise ValueError('This file is already in the library. Choose another file or use its existing entry.')
            info=json.loads(row['metadata']);info.pop('job_id',None);info.update(metadata)
            # An external replacement is an imported original, never a deletable output.
            db.execute('UPDATE media SET path=?,kind=?,owned=0,metadata=? WHERE id=?',(str(path),metadata['kind'],json.dumps(info,ensure_ascii=False),identity))
            db.execute('DELETE FROM removed WHERE path=?',(str(path),))
        return self.get(identity)
    def remove(self,identity,delete_file=False):
        record=self.get(identity)
        if not record:raise ValueError('Media not found.')
        # Imported files are references: the app never deletes an original.
        if delete_file:
            if not record['owned']:raise ValueError('Imported originals cannot be deleted by DropDL. Remove the library reference instead.')
            Path(record['path']).unlink(missing_ok=True)
        with self.lock,self.connection() as db:
            db.execute('DELETE FROM media WHERE id=?',(identity,))
            db.execute('INSERT OR IGNORE INTO removed VALUES (?)',(record['path'],))
        return record

library=MediaLibrary(CONFIG_ROOT/'library.sqlite3')

def remember_job(job):
    if job.purpose in {'preview','conversion_sample'} or not job.filename:return
    try:library.add(job.filename,title=job.title,kind=job.kind,site=job.site or 'Local',url=job.url,owned=True,ignore_removed=True,metadata={'purpose':job.purpose,'job_id':job.id,'container':job.container,'quality':job.quality,'clip_start':job.clip_start,'clip_end':job.clip_end})
    except (OSError,ValueError,sqlite3.Error):
        import logging
        logging.getLogger('dropdl.library').exception('Could not catalogue completed file')
