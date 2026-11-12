"""A bounded queue: enqueueing 1000 tasks never creates 1000 futures/processes."""
import logging
import time
from threading import Lock,Thread,Event
from .jobs import jobs
from .task_errors import classify

# Error categories that are worth retrying automatically. Permanent failures
# (unavailable, private, unsupported, disk full...) stay failed for review.
RETRYABLE={'network','worker_crash','stalled','rate_limited'}


def retry_delay(attempt,code):
    """Seconds to wait before automatic retry number ``attempt`` (0-based)."""
    if code=='stalled':return 3  # Partial data is kept; reconnect almost immediately.
    base=60 if code=='rate_limited' else 10
    return min(300,base*(2**attempt))


class Scheduler:
    def __init__(self,workers,preferences,execute=None):
        self.workers=workers;self.preferences=preferences;self.execute=execute;self.pending={};self.running=set();self.lock=Lock();self.stopped=Event();self.paused=False
        Thread(target=self.loop,daemon=True,name='queue-dispatcher').start()

    def slots(self):
        """Parallel task limit; Preferences can change it while the app runs."""
        try:
            value=int(self.preferences().get('max_concurrent_downloads') or self.workers)
        except (TypeError,ValueError):value=self.workers
        return max(1,min(8,value))

    def submit(self,function,job):
        with self.lock:self.pending[job.id]=(function,job)

    def maybe_retry(self,function,job):
        if job.status!='failed' or job.purpose!='download' or job.cancel_event.is_set():return None
        code=classify(job.error)
        if code not in RETRYABLE:return None
        try:limit=int(self.preferences().get('max_auto_retries',4))
        except (TypeError,ValueError):limit=4
        if job.auto_retries>=max(0,min(10,limit)):return None
        replacement=jobs.retry(job.id)
        if not replacement:return None
        delay=retry_delay(job.auto_retries,code)
        replacement.auto_retries=job.auto_retries+1
        replacement.stalls=job.stalls
        reason=(job.error or 'Temporary failure').split('\n')[0][:300]
        jobs.update(replacement.id,scheduled_at=time.time()+delay,retry_at=time.time()+delay,phase='retry_wait',
                    error=f'{reason} Automatic retry {replacement.auto_retries}/{limit} scheduled.')
        logging.getLogger('dropdl.queue').info('Task %s: %s failure, retry %s in %ss',job.id[:8],code,replacement.auto_retries,delay)
        self.submit(function,replacement)
        return replacement

    def run(self,function,job):
        try:
            if self.execute:self.execute(job)
            else:function(job)
            self.maybe_retry(function,job)
        except Exception as exc:
            logging.getLogger('dropdl.queue').exception('Task failed');jobs.update_attempt(job,status='failed',error=str(exc))
        finally:
            with self.lock:self.running.discard(job.id)

    def loop(self):
        while not self.stopped.wait(.15):
            try:self.dispatch()
            except Exception:logging.getLogger('dropdl.queue').exception('Dispatcher iteration failed; continuing')

    def dispatch(self):
        with self.lock:
            self.pending={k:v for k,v in self.pending.items() if jobs.get(k) is v[1] and v[1].status=='queued' and not v[1].cancel_event.is_set()}
            if self.paused:return
            slots=self.slots()
            available=slots-len(self.running)
            if available<=0:return
            now=time.time()
            eligible=sorted((v for v in self.pending.values() if v[1].scheduled_at<=now),key=lambda v:(-v[1].priority,v[1].created_at))[:available]
            for function,job in eligible:
                self.pending.pop(job.id,None);self.running.add(job.id)
                if job.phase=='retry_wait':job.phase='resuming'
                job.retry_at=0
                limit=self.preferences().get('global_speed_limit_kbps',0)
                if limit:
                    allocation=max(1,limit//slots)
                    job.speed_limit_kbps=min(job.speed_limit_kbps or allocation,allocation)
                Thread(target=self.run,args=(function,job),daemon=True,name='task-'+job.id[:8]).start()

    def close(self):self.stopped.set()
