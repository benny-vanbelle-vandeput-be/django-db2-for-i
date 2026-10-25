Tooling: a stop signal that arrived right after the PUB400 lock was taken,
before the run started, ended the lock process without its container
cleanup. The lock now handles signals from the moment it holds the lock. A
signal before the start skips the run, and the container check still runs
before the lock is released.
