#!/usr/bin/env bash
# Make sure a Python new enough to run this exists, and print its path.
#
#   PYTHON="$(deploy/bootstrap-python.sh)"
#
# Everything here needs Python 3.10 or newer. mcp, starlette, uvicorn, py-cord
# and Pillow all declare it, so an older interpreter fails at pip install
# rather than at runtime, which at least fails early.
#
# On Ubuntu 24.04 the system python3 is 3.12 and this does nothing at all. It
# exists for 20.04, which ships 3.8 and cannot be talked into anything newer:
# deadsnakes dropped that release when it went end of life, so apt has nothing.
#
# The way out is a prebuilt standalone interpreter. These are ordinary CPython
# builds linked against glibc 2.17 or newer, which covers every Ubuntu since
# 2014, and they unpack into a folder and run. No compiler, no PPA, nothing
# that touches the system Python or anything apt manages. On a 1GB machine
# that matters: building CPython from source there takes the better part of an
# hour and needs a toolchain this box has no other use for.
#
# The version and its checksum are pinned. An unpinned download of an
# interpreter is a supply chain the size of the internet, and this one runs the
# server.

set -euo pipefail

MINIMUM_MINOR=10

# Pinned release. Bumping it means updating the URL and the checksum together,
# from the SHA256SUMS file published alongside the release.
PY_VERSION="3.12.14"
PY_RELEASE="20260814"
PY_SHA256="3297691ae34f75fed81ac424e040145fccb0bafe8e581cd5cadbddfa1c0766c0"

PREFIX="$HOME/.local/share/buried-star"
TARGET="$PREFIX/python/bin/python3"

# Everything this prints that is not the interpreter path goes to stderr, so
# the caller can use the output directly.
log() { echo "$@" >&2; }

usable() {
    local candidate="$1"
    [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1 || return 1
    "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, $MINIMUM_MINOR) else 1)" \
        >/dev/null 2>&1
}

# 1. Already bootstrapped by an earlier run.
if usable "$TARGET"; then
    log "   using the standalone Python at $TARGET"
    echo "$TARGET"
    exit 0
fi

# 2. The system one, if it is new enough. This is the 24.04 path.
if usable python3; then
    log "   system python3 is new enough ($(python3 --version 2>&1))"
    command -v python3
    exit 0
fi

# 3. Anything else apt happens to have. Someone may have installed 3.11 by hand.
for minor in 13 12 11 10; do
    if usable "python3.$minor"; then
        log "   using python3.$minor"
        command -v "python3.$minor"
        exit 0
    fi
done

# 4. Fetch one.
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  TRIPLE="x86_64-unknown-linux-gnu" ;;
    aarch64) TRIPLE="aarch64-unknown-linux-gnu" ;;
    *)
        log "No prebuilt Python for $ARCH, and the system one is too old."
        log "Rebuild the machine on Ubuntu 24.04, which ships 3.12."
        exit 1
        ;;
esac

# The checksum is pinned for x86_64 only, because that is the machine this was
# needed for. Refusing is better than downloading something unverified.
if [ "$ARCH" != "x86_64" ]; then
    log "The pinned checksum covers x86_64 only. On $ARCH, use Ubuntu 24.04."
    exit 1
fi

ASSET="cpython-${PY_VERSION}+${PY_RELEASE}-${TRIPLE}-install_only.tar.gz"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_RELEASE}/${ASSET//+/%2B}"

log ""
log "   system python3 is $(python3 --version 2>&1), which is too old."
log "   fetching a standalone Python $PY_VERSION (about 105MB)"

mkdir -p "$PREFIX"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl -fsSL -o "$TMP/python.tar.gz" "$URL"

echo "$PY_SHA256  $TMP/python.tar.gz" | sha256sum -c - >/dev/null 2>&1 || {
    log ""
    log "   CHECKSUM MISMATCH. Refusing to install it."
    log "   Expected $PY_SHA256"
    log "   Got      $(sha256sum "$TMP/python.tar.gz" | cut -d' ' -f1)"
    log ""
    log "   This is either a corrupted download or something worse. Run it"
    log "   again; if it keeps failing, do not work around it."
    exit 1
}
log "   checksum verified"

tar -xzf "$TMP/python.tar.gz" -C "$TMP"
# The tarball unpacks to a folder called python/. Replace any previous one
# atomically enough that a failure partway leaves the old one alone.
rm -rf "$PREFIX/python.old"
[ -d "$PREFIX/python" ] && mv "$PREFIX/python" "$PREFIX/python.old"
mv "$TMP/python" "$PREFIX/python"
rm -rf "$PREFIX/python.old"

if ! usable "$TARGET"; then
    log "   unpacked, but it will not run. Leaving it for inspection at $TARGET"
    exit 1
fi

log "   installed $("$TARGET" --version 2>&1) at $TARGET"
echo "$TARGET"
