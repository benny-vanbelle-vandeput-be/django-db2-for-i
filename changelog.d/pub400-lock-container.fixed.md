Tooling: stopping a PUB400 run released the PUB400 lock while the run's
container kept its connection open, so a second job could start. The lock
now stops the run's container (`docker stop`, then `docker kill` after a
timeout) before it releases the lock. A new run removes an exited container
of an earlier run and refuses to start while one still runs.
