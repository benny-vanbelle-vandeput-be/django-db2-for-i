"""Verify a release tag before anything is built or published.

Usage: RELEASE_SIGNING_KEY="<ASCII-armored public key>" \\
       python scripts/verify_release_tag.py v0.1.0a2 [--main-ref origin/main]

Run in a clone that has the tag object (not only the commit) and the main
branch. Fails unless all of these hold:

- RELEASE_SIGNING_KEY holds exactly one OpenPGP public key (the maintainer's);
- the tag is annotated;
- the tag carries a valid OpenPGP signature made by that key (checked in a
  temporary GnuPG home that contains only this key, and by the primary key
  fingerprint in GnuPG's VALIDSIG status line); expired or revoked keys and
  expired signatures are refused;
- the tagged commit is on the main branch;
- the tag is ``v`` + ``__version__`` of the tagged commit;
- CHANGELOG.md of the tagged commit has a section for that version.

Needs git and gpg. Prints one line per check; never prints the key.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from changelog_section import section

KEY_VARIABLE = "RELEASE_SIGNING_KEY"
VERSION_FILE = "django_db2_for_i/__init__.py"
_VERSION = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)
# GnuPG status lines that make a signature unacceptable.
_REFUSED_STATUS = ("BADSIG", "ERRSIG", "EXPSIG", "EXPKEYSIG", "REVKEYSIG", "NO_PUBKEY")


class TagError(Exception):
    pass


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, env=env, check=False)


def _git(*args: str) -> str:
    result = _run(["git", *args])
    if result.returncode != 0:
        raise TagError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def import_key(armored: str, gnupg_home: str) -> str:
    """Import the public key into an empty GnuPG home; return its fingerprint."""
    if not armored.strip():
        raise TagError(f"{KEY_VARIABLE} is empty or not set")
    env = {**os.environ, "GNUPGHOME": gnupg_home}
    imported = subprocess.run(
        ["gpg", "--batch", "--quiet", "--import"],
        input=armored,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if imported.returncode != 0:
        raise TagError(f"{KEY_VARIABLE} could not be imported as an OpenPGP key")
    secret = _run(["gpg", "--batch", "--with-colons", "--list-secret-keys"], env)
    if secret.stdout.strip():
        raise TagError(f"{KEY_VARIABLE} contains a secret key; store the public key only")
    listed = _run(["gpg", "--batch", "--with-colons", "--fingerprint", "--list-keys"], env)
    records = [line.split(":") for line in listed.stdout.splitlines()]
    primaries = [index for index, fields in enumerate(records) if fields[0] == "pub"]
    if len(primaries) != 1:
        raise TagError(f"{KEY_VARIABLE} must hold exactly one public key, found {len(primaries)}")
    following = records[primaries[0] + 1 :]
    fingerprint = next((fields[9] for fields in following if fields[0] == "fpr"), "")
    if not fingerprint:
        raise TagError(f"no fingerprint found for the key in {KEY_VARIABLE}")
    return fingerprint


def check_annotated(tag: str) -> None:
    kind = _run(["git", "cat-file", "-t", f"refs/tags/{tag}"])
    if kind.returncode != 0:
        raise TagError(f"tag {tag} not found (fetch the tag object, not only the commit)")
    if kind.stdout.strip() != "tag":
        raise TagError(f"tag {tag} is not annotated (lightweight tags are refused)")


def check_signature(tag: str, fingerprint: str, gnupg_home: str) -> None:
    env = {**os.environ, "GNUPGHOME": gnupg_home}
    result = _run(
        ["git", "-c", "gpg.format=openpgp", "-c", "gpg.program=gpg", "verify-tag", "--raw", tag],
        env,
    )
    status = [line.split() for line in result.stderr.splitlines() if line.startswith("[GNUPG:]")]
    keywords = {fields[1] for fields in status if len(fields) > 1}
    if not status:
        raise TagError(f"tag {tag} is not signed with OpenPGP")
    refused = sorted(keywords & set(_REFUSED_STATUS))
    if refused or result.returncode != 0 or "GOODSIG" not in keywords:
        reason = ", ".join(refused) or "no valid signature"
        raise TagError(f"tag {tag} has no valid signature by the release key ({reason})")
    signers = {fields[-1] for fields in status if len(fields) > 2 and fields[1] == "VALIDSIG"}
    if signers != {fingerprint}:
        raise TagError(f"tag {tag} is signed by another key")


def check_on_main(tag: str, main_ref: str) -> None:
    result = _run(["git", "merge-base", "--is-ancestor", f"{tag}^{{commit}}", main_ref])
    if result.returncode == 1:
        raise TagError(f"tag {tag} points to a commit that is not on {main_ref}")
    if result.returncode != 0:
        raise TagError(f"cannot compare tag {tag} with {main_ref}: {result.stderr.strip()}")


def tagged_version(tag: str) -> str:
    match = _VERSION.search(_git("show", f"{tag}^{{commit}}:{VERSION_FILE}"))
    if not match:
        raise TagError(f"no __version__ in {VERSION_FILE} of tag {tag}")
    return match.group(1)


def verify(tag: str, armored_key: str, main_ref: str = "origin/main") -> str:
    """Run every check; return the version. TagError on the first failure."""
    with tempfile.TemporaryDirectory(prefix="gnupg-") as gnupg_home:
        os.chmod(gnupg_home, 0o700)
        try:
            fingerprint = import_key(armored_key, gnupg_home)
            print(f"release key: {fingerprint}")
            check_annotated(tag)
            print(f"{tag}: annotated")
            check_signature(tag, fingerprint, gnupg_home)
            print(f"{tag}: signed by the release key")
        finally:
            _run(["gpgconf", "--kill", "all"], {**os.environ, "GNUPGHOME": gnupg_home})
    check_on_main(tag, main_ref)
    print(f"{tag}: on {main_ref}")
    version = tagged_version(tag)
    if tag != f"v{version}":
        raise TagError(f"tag {tag} does not match __version__ {version!r} (expected v{version})")
    print(f"{tag}: matches __version__ {version}")
    try:
        section(_git("show", f"{tag}^{{commit}}:CHANGELOG.md"), version)
    except LookupError as exc:
        raise TagError(str(exc)) from None
    print(f"{tag}: CHANGELOG.md has a section for {version}")
    return version


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag")
    parser.add_argument("--main-ref", default="origin/main")
    args = parser.parse_args(argv)
    try:
        verify(args.tag, os.environ.get(KEY_VARIABLE, ""), args.main_ref)
    except TagError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
