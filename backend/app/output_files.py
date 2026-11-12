"""Reserve names exclusively, including across isolated download workers."""
import os
import shutil
from pathlib import Path

def publish_download(source,destination,stem):
    source=Path(source);destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    for number in range(100000):
        suffix=f' (+{number})' if number else ''
        target=destination/(stem[:160]+suffix+source.suffix)
        try:
            handle=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:continue
        os.close(handle)
        try:
            shutil.move(str(source),str(target))
            return target,number
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    raise OSError('Too many copies with this filename.')
