`bin/doctor` (environment check and one PUB400 connection), `bin/probe`
(read-only probes by name), `bin/ibmi-test` (own IBM i tests, Django test
labels or the full tier) and `bin/ibmi-cleanup` (drops the leftover test
objects of a crashed run, only those test runs listed before creating them,
only in a library with the test marker table), all through the PUB400 lock.
