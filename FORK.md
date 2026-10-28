# electrum-ecash

A fork of [Electrum](https://github.com/spesmilo/electrum) for **ECX**, the
Layer Two Labs Bitcoin hard fork. Not affiliated with or endorsed by the
Electrum developers. Do not report issues with this software to them.

## What changed

Everything, in one command:

```sh
contrib/ecx/show-fork-diff.sh            # commits + files + line counts
contrib/ecx/show-fork-diff.sh --full     # the complete patch
contrib/ecx/show-fork-diff.sh --markers  # every '# ECX:' line in the tree
```

Or directly, since the fork is a linear patch series on a signed upstream tag:

```sh
git log 4.8.3..HEAD          # ~45 commits, each one self-contained
git diff 4.8.3..HEAD
```

**About 290 added lines touch upstream Python files**, most of them in
`blockchain.py` for the post-fork difficulty algorithm; the rest are one-liners.
Everything else lives in `electrum/ecx.py`,
a new file holding every ECX parameter. Each edit in an existing file is a
one-liner tagged `# ECX:` that reads a constant from there, so
`grep -rn '# ECX:' electrum/` enumerates the whole fork surface.

That is deliberate. This is a wallet for claiming a forkcoin, a category with a
long history of malware, so "here is signed upstream Electrum, and here are our
ten commits" needs to be checkable in a few minutes.

## Running from source

Verified on macOS with Python 3.14 (Homebrew).

```sh
python3 -m venv .venv
.venv/bin/pip install --upgrade pip setuptools wheel
.venv/bin/pip install -r contrib/requirements/requirements.txt

# NOT in requirements.txt: that file is pure-python only, but electrum/crypto.py
# hard-requires one of pycryptodomex/cryptography, and dnspython needs the
# DNSSEC extra. Without these you get "Some dependencies are missing".
.venv/bin/pip install cryptography "dnspython[DNSSEC]"

.venv/bin/pip install PyQt6            # GUI only
.venv/bin/pip install -r contrib/requirements/requirements-hw.txt   # hardware wallets only
```

Then:

```sh
.venv/bin/python ./run_electrum                 # GUI
.venv/bin/python ./run_electrum daemon -d       # background daemon
.venv/bin/python ./run_electrum getinfo         # sync status
.venv/bin/python ./run_electrum stop
.venv/bin/python ./run_electrum --offline version
```

`.venv/` is already covered by upstream's `.gitignore`.

Data lives in `~/.electrum-ecash`, never `~/.electrum`. To throw away all local
state (wallets included) and resync: `rm -rf ~/.electrum-ecash`.

> **Careful with the test suite.** Some upstream tests instantiate a config
> against the real data directory and persist settings into it -- e.g.
> `tests/test_onion_message.py` leaves `lightning_forward_payments: true` in
> `~/.electrum-ecash/config`, which then logs a scary mainnet warning at every
> startup. Harmless, but delete the key if you see it. (On stock Electrum this
> lands in the user's real `~/.electrum`; our separate datadir contains it.)

### Verified against the live chain

Synced against `ssl://explorer.ecash.ninja:50002` (Fulcrum 2.1.4, protocol 1.6)
on 2026-10-28: the full header chain PoW-verified to tip **973,578**, with zero
rejected headers. That is still *before* the fork at 973,728, so the chain is
Bitcoin's and the post-fork code paths (the reset, the 288-block retarget) are
exercised only by unit tests so far. **Re-run this once the fork block is a few
hundred blocks deep**, and expect to regenerate the final checkpoint entry then
(see "Checkpoints").

The same code did sync the betanet chain on 2026-09-21: 2,272 blocks past that
network's fork, zero rejected headers. Betanet used Bitcoin's 2016-block
retarget after its reset; mainnet's 288-block dampened algorithm is new.

## The changes, and why

ECX is byte-identical to Bitcoin for keys and addresses: same genesis, same
`bc` HRP, same WIF/xpub prefixes, SLIP-44 coin type `0'`. **A BTC address is an
ECX address.** The consensus rules that differ and that a wallet can see are the
replay-protection locktime, the difficulty reset at the fork block, and the new
difficulty algorithm after it.

| Change | Why |
|---|---|
| `blockchain.py` -- reset difficulty at the fork block | ECX forces a fixed target at block 973,728 (`bnNew.SetCompact(EcashForkBits)`). Without this, every ECX header fails PoW validation. The value is **not derivable** -- see `ecx.FORK_BITS`. |
| `blockchain.py` -- post-fork difficulty algorithm | From the fork on, ECX retargets every **288** blocks with a 6:1 dampened adjustment instead of every 2016. A header's target is no longer a property of its 2016-header chunk, so `verify_chunk`, `can_connect` and the chainwork accounting compute it per height (`get_target_for_height`). See "Post-fork difficulty". |
| `wallet.py` -- `nLockTime = 499999998` on all new txs | ECX's replay-protection marker (`LOCKTIME_THRESHOLD - 2`): final on ECX, permanently non-final on Bitcoin. Betanet used `- 1`; a tx with the old value is simply time-locked for ever on mainnet. |
| `interface.py` -- refuse to broadcast unprotected txs | Defence in depth. The failure it prevents is silent and irreversible. |
| `wallet.py` -- disable Lightning | No LN infrastructure on ECX. |
| `util.py` -- `~/.electrum-ecash` | Otherwise this shares wallet files and headers with the user's real Bitcoin Electrum and corrupts both. |
| `bip21.py` + packaging -- `ecx:` URI scheme | **Money-loss risk.** Claiming `bitcoin:` would let this wallet answer a BTC invoice with an ECX payment. |
| `util.py` -- ECX block explorers | Shared pre-fork history means a Bitcoin explorer renders a real BTC tx for a pre-fork txid. The wrong-chain link looks right. |
| `simple_config.py` -- default explorer | Upstream defaults to `Blockstream.info`, which is not in our list, and `block_explorer()` falls back to *the default* -- so it resolves to nothing and every explorer link is silently dead. Also catches configs naming a pre-launch (betanet) host. |
| `constants.py` -- `GIT_REPO_URL` | Stops our crash reports going to upstream's crashhub. |
| `chains/mainnet/servers.json` -- ECX servers | A Bitcoin server passes every check Electrum makes (see below). |

Bitcoin mainnet is **not** retained. `mainnet` *is* ECX, so there is no way to
accidentally broadcast onto Bitcoin.

## Icons

Which file is the actual app icon, per platform:

| Platform | File | Wired in |
|---|---|---|
| **macOS** | `electrum.icns` (1024) | `contrib/osx/pyinstaller.spec:16,119,131` -- .app bundle, Dock, Finder |
| **Windows** | `electrum.ico` (multi-size) | `contrib/build-wine/pyinstaller.spec:15,124` (the .exe) and `electrum.nsi:75,171,195,216` (installer, `ecx:` URI, Add/Remove Programs) |
| **Linux** | `electrum.png` (128) | `setup.py:39-40` -> `share/pixmaps` + `hicolor/128x128/apps`; `electrum.desktop:10` `Icon=electrum`; AppImage copies it to `$APPDIR/electrum.png` |
| **Android** | `android_electrum_icon_legacy.png` (192) | `contrib/android/buildozer_qml.spec:88` |
| in-app, all | `electrum.png` | `gui/qt/__init__.py:168`, `main_window.py:256` (window + taskbar) |

To replace them all from one master:

```sh
.venv/bin/pip install Pillow
python3 contrib/ecx/make-icons.py path/to/master.png --dry-run   # preview
python3 contrib/ecx/make-icons.py path/to/master.png
```

Master must be **square, at least 1024x1024, RGBA with a transparent
background**. The script keeps upstream's filenames, so no code or packaging
file changes.

It regenerates `electrum.icns`, `electrum.ico`, `electrum.png`,
`electrum_launcher.png`, `electrum_presplash.png`,
`android_electrum_icon_legacy.png`, `electrum_darkblue_1.png`, and both tray
icons. macOS `.icns` is built via `iconutil` from a full iconset including @2x
slices; the `.ico` embeds 16/24/32/48/64/128/256.

**Four files it deliberately does not touch, because they are artwork rather
than scalings:**
- `electrum_text.png` -- wordmark, contains lettering
- `electrum_darkblue.svg`, `electrum_lightblue.svg` -- vector sources
- `electrumb.png` -- non-square, revealer plugin

**Also note** `electrum_dark_icon.png` and `electrum_light_icon.png` are the
system-tray icons, and upstream ships them as two *different* images -- one
tuned for dark menu bars, one for light. The script writes both from the same
master, so check contrast under both themes and hand-supply variants if the
logo does not read on one of them.

## Known gaps

- The post-fork difficulty code has not yet met a real post-fork header: the
  fork block did not exist when this was written. It is unit-tested against
  `pow.cpp`'s arithmetic (`tests/test_ecx.py`), but **sync against the live
  chain once the fork is in** before calling it verified.
- Checkpoints run through chunk 481 (height 971,711); the final entry, which pins
  the last shared block 973,727 with the reset target, needs the fork block to
  exist. `contrib/ecx/make-checkpoints.py` adds it. See "Checkpoints".
- `testnet`/`signet`/`regtest` still point at Bitcoin's. The locktime change is
  unconditional, so they produce ECX-style transactions; repoint them at ECX's
  equivalents (ports 18533/38533/48533) before relying on them.
- Fiat rates are BTC-denominated and would price ECX at the BTC rate. Guarded
  only by `FX_USE_EXCHANGE_RATE` defaulting to off.
- Branding (name, icons, `ELECTRUM_VERSION`) is untouched.

## How this client knows it is on ECX and not Bitcoin

ECX inherits Bitcoin's genesis block, so Electrum's normal chain-identity check --
comparing `server.features` `genesis_hash` -- passes against a Bitcoin server. Two
things actually separate the chains:

1. **The difficulty-reset patch (C1), which is the primary guard.**
   `verify_header` compares bits *exactly* (`if bits != header['bits']`), not as a
   PoW threshold. C1 makes us expect `ecx.FORK_BITS` (`0x1901a6e1`, difficulty
   ~2.6e9) at block 973,728; Bitcoin's real header there will carry Bitcoin's
   ~0x17xxxxxx difficulty, so it is rejected on the first post-fork block.

   Measured on betanet, not asserted. Pointed at `electrum.emzy.de:50002` (a real
   Bitcoin server) with checkpoints truncated so that nothing *but* C1 could
   object, the client synced Bitcoin's chain to exactly the last pre-fork block
   and then stopped:

   ```
   InvalidHeader('bits mismatch: 419711870 vs 386014917')
                                 0x19044b7e   0x17021ec5
                                 (expected)   (Bitcoin's)
   ```

   It never connects and never advances. That is the guard doing its whole job.

2. **The post-fork difficulty algorithm.** Every post-fork header must carry
   exactly the bits the 288-block dampened retarget predicts from the preceding
   window. A chain that reset at the same height with the same bits but retargets
   differently fails at its first retarget.

Checkpoints do **not** take part in this: they stop at the fork (a post-fork
chunk has no single target, so the format cannot express one). They remain a
startup optimisation and a pin of the shared Bitcoin history. A consequence worth
knowing: nothing pins a specific post-fork *hash*, so a second chain with
identical consensus rules, forked from the same block, would be told apart only
by proof of work -- exactly as Bitcoin itself handles competing chains.

## Maintaining the fork

The fork is a patch series on a **signed** upstream tag -- never on `master`,
so every release has verifiable provenance.

```sh
git tag -v 4.8.3                                  # verify upstream's signature (keys in pubkeys/)
git rebase --onto <new-tag> <old-tag> ecx/<old-tag>
```

One branch per upstream release (`ecx/4.8.1`, `ecx/4.8.3`, ...). Old branches are
never force-pushed, so released history and its tags stay valid. `master`
tracks upstream untouched.

The move from 4.8.1 to 4.8.3 (two upstream security releases) took eleven small
conflicts, all import-adjacency or packaging text, and dropped four of our
commits that upstream had made redundant (zbar, Android scanner, two appimage
fixes we had cherry-picked).

After each rebase:

```sh
contrib/ecx/run-tests.sh            # must be green
contrib/ecx/run-tests.sh --audit    # catches a stale known-failures list
```

Most functions we patch are cold upstream (`can_have_lightning`, `user_dir`,
`get_locktime_for_new_transaction`), so conflicts there should be rare. The one
real patch is in `blockchain.py`: the post-fork difficulty algorithm touches
`verify_chunk`, `can_connect`, `get_chainwork` and adds `get_target_for_height`.
Upstream refactored that file between 4.8.1 and 4.8.3 (`BlockchainManager`), so
expect to re-read it on each rebase. This is a fork, not a patch set we intend to
upstream; correctness on ECX comes before diff size.

## Post-fork difficulty

Source: `ecash-com/bitcoin` `master`, `src/pow.cpp` and
`Consensus::Params::DifficultyAdjustmentInterval(int height)` in
`src/consensus/params.h` (commit "Add 288-block dampened retarget after eCash
fork"). In terms of a header at height `h`:

| `h` | bits |
|---|---|
| `< 973728` | Bitcoin's rules, unchanged |
| `== 973728` | exactly `0x1901a6e1` (`EcashForkBits`; `validation.cpp` also enforces it: `bad-diffbits-ecash-da`) |
| `% 288 != 0` | same as `h - 1` |
| `% 288 == 0` | `old * (6T + actual) / 7T`, `T = 288 * 600`, `actual` clamped to `[T/4, 4T]`, capped at powLimit, rounded through compact bits |

where `old` is the target of `h - 1` and `actual` is `time(h-1) - time(first)`,
with `first = max(h - 289, 973728)`. The window is **289 blocks**, sharing its
first block with the previous window's last (`nHeightFirst = max(nHeightFirst - 1,
EcashHeight)` in `GetNextWorkRequired`); only the first post-fork window is 288.
Getting that off by one rejects every header from the second retarget on.

The arithmetic is `ecx.post_fork_next_target` / `ecx.post_fork_window_start`,
pure functions with no Electrum imports, tested in `tests/test_ecx.py`.
`Blockchain.get_target_for_height(height, header_at)` applies them; `verify_chunk`
passes a lookup that sees the chunk being verified, because a retarget window
usually straddles the chunk boundary and those headers are not on disk yet.
Chainwork after the fork is summed per 288-block period from the stored headers.

## Checkpoints

`checkpoints[i]` is a pair: the hash of the last block of chunk `i`, and the
single target of chunk `i+1`. **Post-fork chunks have no single target**, so pins
stop at the fork: at most 483 entries, the last of which (index 482) pins the
final shared Bitcoin block 973,727 together with the fork block's reset target.
Everything from 973,728 on is downloaded and verified header by header. That is
cheap -- the post-fork chain is tiny next to Bitcoin's 973k blocks.

Currently shipped: **482 entries**, through height 971,711, generated 2026-10-28
from a chain synced to 973,578. The last entry needs the fork block to exist.
Once it is a day deep:

```sh
.venv/bin/python ./run_electrum daemon -d        # sync past the fork
.venv/bin/python contrib/ecx/make-checkpoints.py --dry-run
.venv/bin/python contrib/ecx/make-checkpoints.py
contrib/ecx/check.sh && contrib/ecx/run-tests.sh
```

The generator refuses to change any existing entry (they are Bitcoin history and
must never move), refuses to shrink the file, checks that the fork block carries
`FORK_BITS` once it exists, and works on a *copy* of the daemon's header file so
the client's own consistency repair can never touch the real one.

The alpha and beta networks are history. If you ever find a `checkpoints.json`
with more than 483 entries, or whose entry 479 carries `0x19044b7e`, it is a
betanet file: delete those entries, they describe a dead chain.

## Upstream

Licence, build instructions and everything else: see `README.md` and
`contrib/`. Electrum is MIT licensed.
