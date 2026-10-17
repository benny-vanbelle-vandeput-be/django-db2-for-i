# ODBC driver setup

The backend talks to IBM i through pyodbc and the **IBM i Access ODBC
Driver**. You install the driver yourself.

> **License:** the IBM i Access ODBC Driver is IBM software under IBM's license
> terms. It is not part of this project and is never redistributed by it. Do
> not publish container images that contain the driver to a public registry.

## Linux (tested)

Only Linux on x86_64 (amd64) has been tested so far (Debian, driver package
`ibm-iaccess` 1.1.0.29).

1. Install unixODBC: `apt-get install unixodbc` (Debian/Ubuntu).
2. Install IBM's `ibm-iaccess` package from IBM's repository; see IBM's page
   [ODBC Driver for IBM i Access Client Solutions](https://www.ibm.com/support/pages/odbc-driver-ibm-i-access-client-solutions).
3. Check that the driver is registered:

   ```sh
   odbcinst -q -d
   ```

   The backend uses the driver name **`IBM i Access ODBC Driver`**. The package
   registers that name with a `Driver64` entry; if it does not resolve on your
   system, add an explicit entry to `/etc/odbcinst.ini`:

   ```ini
   [IBM i Access ODBC Driver]
   Description = IBM i Access for Linux ODBC Driver (64-bit)
   Driver      = /opt/ibm/iaccess/lib64/libcwbodbc.so
   Setup       = /opt/ibm/iaccess/lib64/libcwbodbcs.so
   Threading   = 0
   DontDLClose = 1
   ```

   (Values from the package's own registration file,
   `/opt/ibm/iaccess/unixodbcregistration`, for `ibm-iaccess` 1.1.0.29.)

Notes:
- IBM publishes the Linux driver for amd64, i386 and ppc64el; **there is no
  arm64 build**. On Apple Silicon, run an amd64 container
  (`--platform linux/amd64`).
- No DSN is needed: the backend builds a DSN-less connection string from your
  `DATABASES` settings.

## Windows and macOS

> **Not documented yet.** IBM also ships the driver for these platforms, but
> the backend has not been tested there.
