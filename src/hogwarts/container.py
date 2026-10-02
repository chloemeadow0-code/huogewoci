"""Container volume ownership setup, then permanently drop root privileges."""
import os
from pathlib import Path

from .http_app import main


def run():
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        directory = Path(os.environ.get('DATA_DIR','/app/server/data')).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        os.chown(directory, 10001, 10001)
        for name in ('accounts.db','accounts.db-wal','accounts.db-shm',
                     'hogwarts.db','hogwarts.db-wal','hogwarts.db-shm'):
            target = directory / name
            if target.exists() and not target.is_symlink():
                os.chown(target,10001,10001)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    main()


if __name__ == '__main__':
    run()
