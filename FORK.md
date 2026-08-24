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
> against the real data directory and persist settings into it — e.g.
> `tests/test_onion_message.py` leaves `lightning_forward_payments: true` in
> `~/.electrum-ecash/config`, which then logs a scary mainnet warning at every
> startup. Harmless, but delete the key if you see it. (On stock Electrum this
> lands in the user's real `~/.electrum`; our separate datadir contains it.)

### Verified against the live chain

Synced against `ssl://fulcrum.alpha.ecash.ninja:50002` after alphanet crossed
the fork: 991,911 headers (~79 MB) PoW-verified to tip 991,910, i.e. **28,262
blocks past the fork at 963,648**. That exercises the difficulty-reset patch on
real post-fork headers, which is the only way to prove it.

## The changes, and why

ECX is byte-identical to Bitcoin for keys and addresses: same genesis, same
`bc` HRP, same WIF/xpub prefixes, SLIP-44 coin type `0'`. **A BTC address is an
ECX address.** Only three consensus rules differ, and only two matter to a
wallet.

| Change | Why |
|---|---|
| `blockchain.py` — reset difficulty at the fork chunk | ECX sets `bnNew = bnPowLimit` at the fork block. Without this, every ECX header fails PoW validation. |
| `wallet.py` — `nLockTime = 499999999` on all new txs | ECX's replay-protection marker: final on ECX, permanently non-final on Bitcoin. |
| `interface.py` — refuse to broadcast unprotected txs | Defence in depth. The failure it prevents is silent and irreversible. |
| `wallet.py` — disable Lightning | No LN infrastructure on ECX. |
| `util.py` — `~/.electrum-ecash` | Otherwise this shares wallet files and headers with the user's real Bitcoin Electrum and corrupts both. |
| `bip21.py` + packaging — `ecx:` URI scheme | **Money-loss risk.** Claiming `bitcoin:` would let this wallet answer a BTC invoice with an ECX payment. |
| `util.py` — ECX block explorers | Shared pre-fork history means a Bitcoin explorer renders a real BTC tx for a pre-fork txid. The wrong-chain link looks right. |
| `constants.py` — `GIT_REPO_URL` | Stops our crash reports going to upstream's crashhub. |
| `chains/mainnet/servers.json` — ECX servers | A Bitcoin server passes every check Electrum makes (see below). |

Bitcoin mainnet is **not** retained. `mainnet` *is* ECX, so there is no way to
accidentally broadcast onto Bitcoin.

## Known gaps

- **Checkpoints past the fork are not yet generated, and they are required.**
  Electrum's only chain-identity guard is the `server.features` genesis hash,
  and ECX inherits Bitcoin's genesis, so a Bitcoin server passes it. Worse, the
  difficulty-reset patch makes chunk `FORK_CHUNK - 1` return `MAX_TARGET` — the
  easiest possible target — so real Bitcoin headers pass the PoW check too.
  Until post-fork ECX block hashes are pinned in
  `electrum/chains/mainnet/checkpoints.json`, **the client cannot tell an ECX
  server from a Bitcoin one.** Do not ship a release handling real funds until
  this is done. Generate them only after the difficulty patch is in place:
  `get_checkpoints()` calls `get_target()`, so doing it in the wrong order
  bakes Bitcoin's target in permanently.
- `testnet`/`signet`/`regtest` still point at Bitcoin's. The locktime change is
  unconditional, so they produce ECX-style transactions; repoint them at ECX's
  equivalents (ports 18533/38533/48533) before relying on them.
- Fiat rates are BTC-denominated and would price ECX at the BTC rate. Guarded
  only by `FX_USE_EXCHANGE_RATE` defaulting to off.
- Branding (name, icons, `ELECTRUM_VERSION`) is untouched.

## Maintaining the fork

The fork is a patch series on a **signed** upstream tag — never on `master`,
so every release has verifiable provenance.

```sh
git tag -v 4.8.1                                  # verify upstream's signature
git rebase --onto <new-tag> <old-tag> ecx/<old-tag>
```

One branch per upstream release (`ecx/4.8.1`, `ecx/4.9.0`, …). Old branches are
never force-pushed, so released history and its tags stay valid. `master`
tracks upstream untouched.

After each rebase:

```sh
contrib/ecx/run-tests.sh            # must be green
contrib/ecx/run-tests.sh --audit    # catches a stale known-failures list
```

The functions we patch are cold upstream — `get_target`, `can_have_lightning`
and `user_dir` saw **zero** commits in three years, and
`get_locktime_for_new_transaction` saw one — so conflicts should be rare. Keep
it that way: every line added to the diff is a line to be re-merged forever.

## Per-phase rebuilds

ECX launches in three phases, and alpha/beta coins are destroyed and reissued
at full launch. Each phase changes exactly one line — `ECASH_HEIGHT` in
`electrum/ecx.py`:

| Phase | Height | Date |
|---|---|---|
| alpha | 963648 | 2026-08-23 |
| beta | 967680 | 2026-09-20 |
| full | 973728 | 2026-10-31 |

All three are exact multiples of 2016; `ecx.py` asserts it, since a
non-boundary height would straddle a retarget chunk and need more than the
current one-line override. Checkpoints must be regenerated per phase.

## Upstream

Licence, build instructions and everything else: see `README.md` and
`contrib/`. Electrum is MIT licensed.
