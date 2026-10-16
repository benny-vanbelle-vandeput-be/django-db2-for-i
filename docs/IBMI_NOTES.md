# IBM i notes

IBM i quirks and probe findings. Every claim here is backed by a probe in
`probes/` or by a cited IBM source, with the date it was checked.

## IBM i Access ODBC Driver for Linux

Checked 2026-10-16 against IBM's repository
(`https://public.dhe.ibm.com/software/ibmi/products/odbc/debs/dists/1.1.0/`):

- Package `ibm-iaccess`, latest version `1.1.0.29-1.0` (amd64).
  Depends on `libodbc2, libodbcinst2, odbcinst, libstdc++6`.
- Architectures published: **amd64, i386, ppc64el. No arm64.** Apple Silicon
  hosts must run the `full` image as `linux/amd64` (emulated).
- The repository is **unsigned** (no `Release.gpg` / `InRelease`); IBM's own
  `.list` file uses `[trusted=yes]`. We pin the `.deb` by SHA256 instead.
- The package's postinst registers drivers from
  `/opt/ibm/iaccess/unixodbcregistration`:
  - `IBM i Access ODBC Driver`: `Driver=/opt/ibm/iaccess/lib/libcwbodbc.so`
    (32-bit path, not shipped in the amd64 package) and
    `Driver64=/opt/ibm/iaccess/lib64/libcwbodbc.so`;
  - `IBM i Access ODBC Driver 64-bit`: `Driver=/opt/ibm/iaccess/lib64/libcwbodbc.so`.
  - Both with `Threading = 0`, `DontDLClose = 1`.
- The package ships its license at `/opt/ibm/iaccess/doc/license.txt`.

## Test system: PUB400

Terms of use reviewed by the project owner on 2026-10-16 before any live probe.

### Reachability and TLS
Pending: `nox -s probe -- reachability`.

### Connection (`SELECT 1 FROM SYSIBM.SYSDUMMY1`)
Pending: `nox -s probe -- connect`.

### OS release, TR level, Db2 PTF Group level, CCSID
Pending: `nox -s probe -- sysinfo`.

### Libraries and journaling
Pending: `nox -s probe -- libraries`. The libraries are referred to here as
`<default library>` and `<other library>`, not by name.
