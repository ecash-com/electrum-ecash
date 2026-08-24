# Electrum eCash — lightweight ECX wallet

A fork of [Electrum](https://github.com/spesmilo/electrum) for **ECX**, the
Layer Two Labs Bitcoin hard fork ("eCash").

```
Licence:  MIT
Language: Python (>= 3.10)
Upstream: https://github.com/spesmilo/electrum  (v4.8.1)
```

> **Not affiliated with, endorsed by, or supported by the Electrum developers or
> Electrum Technologies GmbH.** Do not report issues with this software to them.
> If you want the *Bitcoin* Electrum wallet, get it from
> [electrum.org](https://electrum.org/) — not from here. This wallet cannot
> connect to Bitcoin.

> **⚠ Pre-release. Do not use with funds you cannot afford to lose.**
> There are no signed binaries, no reproducible-build attestation, and no update
> mechanism yet. Known gaps are listed in [FORK.md](FORK.md#known-gaps). Build
> from source and read the diff.

## What this is

ECX is a Bitcoin hard fork. Everything key- and address-related is byte-identical
to Bitcoin — same genesis block, same `bc` bech32 prefix, same WIF/xpub prefixes,
same SLIP-44 coin type. **A Bitcoin address is an ECX address**, and nothing in
the string tells you which chain it belongs to.

That similarity is the whole reason this fork exists rather than a config file:
almost every place upstream says "Bitcoin" becomes silently wrong rather than
obviously broken. This wallet talks only to ECX, sets ECX's replay-protection
marker on every transaction, and refuses to broadcast one that could replay onto
Bitcoin.

## What we changed

The fork is a linear patch series on the GPG-signed upstream `4.8.1` tag.
**About 220 lines touch pre-existing upstream files**; everything else lives in
new files, chiefly `electrum/ecx.py`, which holds every ECX parameter.

Read the whole thing in one command:

```sh
git log 4.8.1..HEAD                     # ~30 self-contained commits
contrib/ecx/show-fork-diff.sh           # summary
contrib/ecx/show-fork-diff.sh --full    # the complete patch
contrib/ecx/show-fork-diff.sh --markers # every '# ECX:' line in the tree
```

Every edit in an existing file is a one-liner tagged `# ECX:`, so
`grep -rn '# ECX:' electrum/` enumerates the entire fork surface.

That is deliberate. Wallets for claiming forkcoins are a classic malware lure, so
"here is signed upstream Electrum, and here are our commits" needs to be
checkable in a few minutes. See [FORK.md](FORK.md) for what each change does and
why.

## Running from source

Verified on macOS with Python 3.14 and on Linux.

```sh
git clone https://github.com/ecash-com/electrum-ecash.git
cd electrum-ecash
git checkout ecx/4.8.1
git submodule update --init

python3 -m venv .venv
.venv/bin/pip install -r contrib/requirements/requirements.txt

# NOT in requirements.txt -- that file is restricted to pure-python packages,
# but electrum/crypto.py hard-requires one of pycryptodomex/cryptography.
.venv/bin/pip install cryptography "dnspython[DNSSEC]"

.venv/bin/pip install PyQt6                                        # GUI
.venv/bin/pip install -r contrib/requirements/requirements-hw.txt  # hardware wallets

.venv/bin/python ./run_electrum
```

Data lives in `~/.electrum-ecash`, never `~/.electrum`, so this cannot disturb an
existing Bitcoin Electrum install.

On Debian/Ubuntu you may also want `libsecp256k1-dev` (otherwise `electrum-ecc`
compiles it locally, which needs `automake` and `libtool`) and `python3-pyqt6`.

## Tests

```sh
contrib/ecx/run-tests.sh          # upstream's suite, minus tests our changes invalidate
contrib/ecx/run-tests.sh --audit  # re-run the excluded ones, to catch a stale list
contrib/ecx/check.sh              # static checks (undefined names, ecx imports)
```

Exclusions are listed with their cause in
`contrib/ecx/known-test-failures.txt`, and were established by diffing against a
pristine `4.8.1` checkout — not assumed. Upstream's test files are deliberately
left unedited so they keep merging cleanly.

## Building binaries

Upstream's tooling, unchanged and reproducible:
[Linux tarball](contrib/build-linux/sdist/README.md) ·
[AppImage](contrib/build-linux/appimage/README.md) ·
[macOS](contrib/osx/README.md) ·
[Windows](contrib/build-wine/README.md) ·
[Android](contrib/android/Readme.md)

No signed releases are published yet. Code signing, notarization and
reproducible-build attestation are outstanding — see [FORK.md](FORK.md).

## Maintaining the fork

`master` tracks upstream untouched; our work lives on `ecx/<upstream-tag>`
branches, rebased onto **signed** upstream tags so every release has verifiable
provenance. ECX also relaunches twice more (beta and full), and each relaunch is
a different chain — the procedure for both is in
[FORK.md](FORK.md#maintaining-the-fork).

## Contributing

Issues and pull requests here:
<https://github.com/ecash-com/electrum-ecash>.

Please do **not** take questions about this fork to upstream's issue tracker,
IRC channel, or Crowdin project. Bugs in unmodified upstream code should go
upstream; bugs in the ECX changes belong here.

The guiding constraint is that the diff stays small: every line added is a line
to be re-merged on every upstream security release.

## Credit

Electrum is the work of Thomas Voegtlin and the Electrum contributors, MIT
licensed. This fork only exists because of theirs.
