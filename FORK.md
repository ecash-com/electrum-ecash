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
git log 4.8.1..HEAD          # ~10 commits, each one self-contained
git diff 4.8.1..HEAD
```

**~56 lines touch upstream files.** Everything else lives in `electrum/ecx.py`,
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

Synced against `ssl://explorer.beta.ecash.ninja:50002` (Fulcrum 2.1.2, protocol
1.6) on 2026-09-21: the full header chain PoW-verified to tip **969,952**, i.e.
2,272 blocks past the beta fork at 967,680, with zero rejected headers. That
exercises the difficulty-reset patch on real post-fork headers, which is the only
way to prove it.

Betanet already runs **ahead of Bitcoin mainnet** (969,952 vs 968,017 the same
day): the fork resets difficulty to 1e9 against Bitcoin's ~127e12, so it mines
far faster and the gap widens.

## The changes, and why

ECX is byte-identical to Bitcoin for keys and addresses: same genesis, same
`bc` HRP, same WIF/xpub prefixes, SLIP-44 coin type `0'`. **A BTC address is an
ECX address.** Only three consensus rules differ, and only two matter to a
wallet.

| Change | Why |
|---|---|
| `blockchain.py` -- reset difficulty at the fork chunk | ECX forces a fixed target at the fork block (`bnNew.SetCompact(EcashForkBits)`). Without this, every ECX header fails PoW validation. The value is **per phase and not derivable** -- see `ecx.FORK_BITS`. |
| `wallet.py` -- `nLockTime = 499999999` on all new txs | ECX's replay-protection marker: final on ECX, permanently non-final on Bitcoin. |
| `interface.py` -- refuse to broadcast unprotected txs | Defence in depth. The failure it prevents is silent and irreversible. |
| `wallet.py` -- disable Lightning | No LN infrastructure on ECX. |
| `util.py` -- `~/.electrum-ecash` | Otherwise this shares wallet files and headers with the user's real Bitcoin Electrum and corrupts both. |
| `bip21.py` + packaging -- `ecx:` URI scheme | **Money-loss risk.** Claiming `bitcoin:` would let this wallet answer a BTC invoice with an ECX payment. |
| `util.py` -- ECX block explorers | Shared pre-fork history means a Bitcoin explorer renders a real BTC tx for a pre-fork txid. The wrong-chain link looks right. |
| `simple_config.py` -- default explorer | Upstream defaults to `Blockstream.info`, which is not in our list, and `block_explorer()` falls back to *the default* -- so it resolves to nothing and every explorer link is silently dead. Also catches configs naming a previous phase's host. |
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

- Checkpoints are generated through chunk 480 (height 969,695), which pins
  **only one** post-fork chunk -- betanet forked on 2026-09-20 and there is not
  yet more chain to pin. Regenerate with a proper `--margin` once betanet has
  depth, and at every phase switch: `contrib/ecx/make-checkpoints.py`. See
  "Per-phase rebuilds" below.
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
   PoW threshold. C1 makes us expect `ecx.FORK_BITS` (`0x19044b7e` on beta) for the
   fork chunk; Bitcoin's real header at 967,680 carries `0x17021ec5`, so it is
   rejected on the first post-fork block.

   Measured, not asserted. Pointed at `electrum.emzy.de:50002` (a real Bitcoin
   server) with checkpoints truncated to height 961,631 so that nothing *but* C1
   could object, the client syncs Bitcoin's chain to exactly 967,679 -- the last
   pre-fork block -- and then stops:

   ```
   InvalidHeader('bits mismatch: 419711870 vs 386014917')
                                 0x19044b7e   0x17021ec5
                                 (expected)   (Bitcoin's)
   ```

   It never connects and never advances. That is the guard doing its whole job.

2. **Checkpoints**, which pin real post-fork block hashes. These are what separate
   this chain from another that *also* reset difficulty at the same height with the
   same bits -- the bits check alone cannot see that difference.

   Incidentally, a third guard is live right now: our top checkpoint (969,695) is
   above Bitcoin's own tip, so a Bitcoin server is dropped as
   `server tip below max checkpoint` before any header is even fetched. Do not
   rely on it -- it is a side effect of betanet mining faster, not a designed
   check.

So checkpoints are defence in depth and a startup optimisation, not the only thing
standing between a user and Bitcoin's chain. Ship them anyway: the cost is one
command, and (2) is a real gap without them.

## Maintaining the fork

The fork is a patch series on a **signed** upstream tag -- never on `master`,
so every release has verifiable provenance.

```sh
git tag -v 4.8.1                                  # verify upstream's signature
git rebase --onto <new-tag> <old-tag> ecx/<old-tag>
```

One branch per upstream release (`ecx/4.8.1`, `ecx/4.9.0`, ...). Old branches are
never force-pushed, so released history and its tags stay valid. `master`
tracks upstream untouched.

After each rebase:

```sh
contrib/ecx/run-tests.sh            # must be green
contrib/ecx/run-tests.sh --audit    # catches a stale known-failures list
```

The functions we patch are cold upstream -- `get_target`, `can_have_lightning`
and `user_dir` saw **zero** commits in three years, and
`get_locktime_for_new_transaction` saw one -- so conflicts should be rare. Keep
it that way: every line added to the diff is a line to be re-merged forever.

## Per-phase rebuilds

ECX launches in three phases, and alpha/beta coins are destroyed and reissued at
full launch. **Alpha, beta and full are three different chains**, each forked from
Bitcoin at a different height:

| Phase | Height | Fork chunk | Bitcoin-identical through |
|---|---|---|---|
| alpha | 963648 | 478 | chunk 477 |
| beta | 967680 | 480 | chunk 479 |
| full | 973728 | 483 | chunk 482 |

Between alpha's fork and beta's, the alpha chain has its own blocks while the beta
chain still has Bitcoin's. So **alpha checkpoints past chunk 478 make a beta build
reject the beta chain outright** -- the client refuses to sync at all. Loud rather
than silent, but it means checkpoints and `ECASH_HEIGHT` are a matched pair.

**Two things move per phase, not one.** Alpha reset difficulty to `powLimit`;
beta resets to a fixed difficulty of 1e9. Betanet added
`consensus.EcashForkBits` for exactly this and enforces it as its own consensus
rule (`bad-diffbits-ecash-da` in `validation.cpp`). So `ecx.FORK_BITS` has to be
read off that phase's `chainparams.cpp` -- it cannot be derived, and assuming it
is still `powLimit` yields a client that rejects every post-fork header.

Switching phase:

```sh
# 1. two lines in electrum/ecx.py, both from that phase's chainparams.cpp
ECASH_HEIGHT = 967680
FORK_BITS    = 0x19044b7e

# 2. drop the previous phase's checkpoints, or the daemon cannot sync at all.
#    Pass the height you are LEAVING.
.venv/bin/python contrib/ecx/make-checkpoints.py --truncate-for-sync 963648

# 3. resync from scratch -- the old chain's headers are a different chain
rm -rf ~/.electrum-ecash/blockchain_headers ~/.electrum-ecash/forks
.venv/bin/python ./run_electrum daemon -d      # wait for getinfo to catch up

# 4. regenerate checkpoints
.venv/bin/python contrib/ecx/make-checkpoints.py --dry-run
.venv/bin/python contrib/ecx/make-checkpoints.py

# 5. verify
contrib/ecx/check.sh && contrib/ecx/run-tests.sh
```

Step 2 is not optional and its cut is one entry earlier than it looks.
`checkpoints[i]` is a *pair*: the hash of the last block in chunk `i`, and the
target used by chunk `i+1`. At the previous phase's fork chunk F, entry `F-1`
therefore carries **that phase's reset target** even though its hash is still
shared Bitcoin history. Keep it and the client demands alpha's `0x1d00ffff` of
beta's first post-shared chunk, and the sync dies with `unexpected bad header`.
So the safe prefix is `F-1` entries. `--truncate-for-sync` computes this for you;
it is worth using rather than counting by hand.

`make-checkpoints.py` refuses to run if the chain it is reading did not reset
difficulty exactly at `ECASH_HEIGHT`, with exactly `FORK_BITS` -- that check is
what stops you generating beta checkpoints from an alpha chain, or from Bitcoin.
It also refuses if any pre-fork entry would change, and if the fork-chunk target
is not the `FORK_BITS` target (which would mean C1 was not applied first;
`get_checkpoints()` calls `get_target()`, so the order matters). Note the
generator *reads the file it is about to replace* -- `get_hash()` and
`get_target()` both consult it -- so a stale file silently poisons its output as
well as blocking the sync. That is why truncation comes first.

It leaves a `--margin` of 10 chunks below the tip unpinned by default. Post-fork
difficulty is far below Bitcoin's, so recent blocks are comparatively cheap to
reorg and should not be pinned. **Right after a fork there is not enough chain to
allow any margin**: beta's first generation needed `--margin 0` to reach past the
fork chunk at all, and pins a single post-fork chunk. Regenerate with the default
margin once the chain has depth.

## Upstream

Licence, build instructions and everything else: see `README.md` and
`contrib/`. Electrum is MIT licensed.
