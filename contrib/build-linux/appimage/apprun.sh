#!/bin/bash

set -e

APPDIR="$(dirname "$(readlink -e "$0")")"

export LD_LIBRARY_PATH="${APPDIR}/usr/lib/:${APPDIR}/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH+:$LD_LIBRARY_PATH}"
export PATH="${APPDIR}/usr/bin:${PATH}"
export LDFLAGS="-L${APPDIR}/usr/lib/x86_64-linux-gnu -L${APPDIR}/usr/lib"

# ECX: setup.py installs the launcher as "electrum-ecash", so it is not a binary
# named "electrum" that could shadow a real Electrum install.
exec "${APPDIR}/usr/bin/python3" -s "${APPDIR}/usr/bin/electrum-ecash" "$@"
