# Copyright (C) 2026 The electrum-ecash developers
# Distributed under the MIT software license, see the accompanying
# file LICENCE or http://www.opensource.org/licenses/mit-license.php
"""ECX (eCash) chain parameters.

This module is the whole of the fork's configuration. It is the ONLY new file
electrum-ecash adds to upstream Electrum; every other change is a one-line edit
in an existing file that reads a constant from here, marked with `# ECX:`.

    $ grep -rn '# ECX:' electrum/     # enumerates the entire fork surface

Deliberately imports nothing from `electrum`: it is pulled in by util.py and
constants.py, which sit near the bottom of the import graph.

ECX forks Bitcoin at ECASH_HEIGHT. Everything key- and address-related is
byte-identical to Bitcoin (same genesis, HRP, WIF/xpub prefixes, SLIP-44 coin
type 0'), so a BTC address IS an ECX address. The consensus rules that differ,
and that a wallet can see, are:

  1. Replay protection via a magic nLockTime      -> LOCKTIME below
  2. A difficulty reset at the fork block         -> FORK_BITS below
  3. A new difficulty algorithm after the fork:
     288-block retarget, dampened 6:1             -> post_fork_next_target() below

Everything else (reassigned Satoshi-era coins, OP_DRIVECHAIN, the BIP300/301
rules) is invisible to a light client.

Source of truth: https://github.com/ecash-com/bitcoin, branch `master`, files
src/kernel/chainparams.cpp, src/pow.cpp, src/consensus/tx_verify.cpp; and
https://drivechain.dev/config (network id "ecash") for the infrastructure.
"""

# -- Fork activation ---------------------------------------------------------

# `consensus.EcashHeight` in ecash-com/bitcoin, src/kernel/chainparams.cpp
# (branch `master`, the mainnet launch branch).
#
# CURRENT PHASE: MAINNET -- the real eCash. Launch was phased (alphanet forked
# at 963648, betanet at 967680); those chains are abandoned and their coins
# void. This build tracks only the launch chain. Note the fork height is
# 2016 * 483 exactly, a Bitcoin retarget boundary.
ECASH_HEIGHT = 973728

# Bitcoin's difficulty retarget interval. Same as blockchain.CHUNK_SIZE, but
# redeclared so this module stays import-free.
RETARGET_INTERVAL = 2016

# The fork height is an exact multiple of 2016, i.e. a Bitcoin retarget
# boundary. blockchain.py relies on this in two places: the pre-fork chunk
# arithmetic ends cleanly at the fork, and every 2016-header chunk after it
# starts on a 288-block retarget boundary (2016 == 7 * 288). Assert rather than
# trust it.
assert ECASH_HEIGHT % RETARGET_INTERVAL == 0, \
    f"ECASH_HEIGHT {ECASH_HEIGHT} is not a retarget boundary"

# The chunk whose headers use the reset target.
FORK_CHUNK = ECASH_HEIGHT // RETARGET_INTERVAL

# blockchain.verify_chunk(index) validates against get_target(index - 1), so the
# override belongs on the chunk *before* the fork chunk.
FORK_TARGET_OVERRIDE_CHUNK = FORK_CHUNK - 1

# `consensus.EcashForkBits` -- the compact target the fork block must carry
# (`bnNew.SetCompact(params.EcashForkBits)` in src/pow.cpp). Mainnet resets to
# a fixed difficulty of about 2.6e9. It is not derivable; it was different on
# every pre-launch network (alphanet: powLimit, betanet: 0x19044b7e). Read it
# off chainparams.cpp.
#
# validation.cpp enforces this as a consensus rule in its own right
# ("bad-diffbits-ecash-da"), so the fork block carries exactly these bits.
#
# This is the fork's PRIMARY chain-identity guard, and the reason it works is
# that blockchain.verify_header compares bits for EXACT equality rather than as
# a proof-of-work threshold. Real Bitcoin's header at height 973728 carries
# Bitcoin's ~0x17xxxxxx difficulty, so it fails against our expected 0x1901a6e1
# and a Bitcoin server is rejected at the first post-fork header. Nothing else
# can do this job: ECX shares Bitcoin's genesis hash, so Electrum's usual
# genesis check (interface.py) passes against a BTC server.
FORK_BITS = 0x1901a6e1

# Sanity: a compact target's mantissa must not have its sign bit set, or
# SetCompact reads it as negative and the round-trip through target_to_bits that
# verify_header relies on would not be exact.
assert not (FORK_BITS & 0x00800000), f"FORK_BITS {FORK_BITS:#010x} has the sign bit set"


# -- Post-fork difficulty algorithm -------------------------------------------

# From the fork block on, ECX retargets every 288 blocks (two days at the
# 10-minute spacing) instead of every 2016, and dampens each adjustment:
#
#     new_target = old_target * (6 * T + actual) / (7 * T)        T = 288 * 600
#
# i.e. a 6:1 weighted average of the old target and the "measured" one, so a
# single window moves difficulty by at most 1/7 of what Bitcoin's rule would.
# `actual` is clamped to [T/4, 4T] as in Bitcoin, and the result is capped at
# powLimit. Source: ecash-com/bitcoin src/pow.cpp (CalculateNextWorkRequired,
# the `ecash_daa` branch) and Consensus::Params::DifficultyAdjustmentInterval
# (int height) in src/consensus/params.h, commit "Add 288-block dampened
# retarget after eCash fork".
#
# Between retargets every block carries the previous block's bits. The block AT
# the fork height carries FORK_BITS regardless of this formula.
#
# The measurement window is unusual, and getting it wrong rejects every header
# from the second retarget on: it is 289 blocks, sharing its first block with
# the previous window's last block --
#     nHeightFirst = (height - 1) - (288 - 1);  nHeightFirst = max(nHeightFirst - 1, EcashHeight)
# -- except for the very first post-fork window, which is clamped at the fork
# block and so spans only 288. post_fork_window_start() encodes exactly that.
#
# Consequence for a light client: a header's target is no longer a property of
# its 2016-header chunk. blockchain.py computes it per height from the preceding
# headers (Blockchain.get_target_for_height). The pure arithmetic lives here so
# it can be tested against pow.cpp line by line, with no Electrum imports.
POST_FORK_RETARGET_INTERVAL = 288
POST_FORK_TARGET_TIMESPAN = POST_FORK_RETARGET_INTERVAL * 10 * 60   # 172800 s

# 2016 == 7 * 288, so every 2016-header chunk after the fork begins on a
# retarget boundary. blockchain.verify_chunk does not strictly need this, but
# the chainwork accounting assumes it, so assert it.
assert RETARGET_INTERVAL % POST_FORK_RETARGET_INTERVAL == 0


def is_post_fork_retarget_height(height: int) -> bool:
    """Whether the block at `height` (> ECASH_HEIGHT) starts a new target."""
    # pow.cpp: `(pindexLast->nHeight + 1) % interval != 0` -> keep previous bits.
    return height % POST_FORK_RETARGET_INTERVAL == 0


def post_fork_window_start(height: int) -> int:
    """First block of the window measured by the retarget at `height`.

    `height` must be a retarget height strictly above ECASH_HEIGHT. The last
    block of the window is always `height - 1`.
    """
    assert height > ECASH_HEIGHT and is_post_fork_retarget_height(height), height
    return max(height - POST_FORK_RETARGET_INTERVAL - 1, ECASH_HEIGHT)


def post_fork_next_target(last_target: int, first_timestamp: int, last_timestamp: int,
                          pow_limit: int) -> int:
    """The raw (not yet compact-rounded) target following a retarget window.

    Mirrors CalculateNextWorkRequired's `ecash_daa` branch. The caller rounds
    through the compact encoding, as the C++ does with GetCompact.
    """
    T = POST_FORK_TARGET_TIMESPAN
    actual = last_timestamp - first_timestamp
    actual = max(actual, T // 4)
    actual = min(actual, T * 4)
    # arith_uint256 multiply-then-divide: the product is at most
    # powLimit * (6T + 4T) < 2**224 * 2**21, far below the 256-bit wrap.
    new_target = last_target * (6 * T + actual) // (7 * T)
    return min(new_target, pow_limit)


# -- Replay protection -------------------------------------------------------

# ECX's IsFinalTx (src/consensus/tx_verify.cpp) short-circuits to "final" on
# nLockTime == LOCKTIME_THRESHOLD - 2. Bitcoin Core reads the same value as a
# block height ~500M in the future and refuses to relay or mine it, so a tx
# carrying it is valid on ECX and permanently non-final on Bitcoin.
#
# MAINNET USES "- 2". Betanet used LOCKTIME_THRESHOLD - 1 (499999999). A
# transaction carrying the old value is NOT final on mainnet -- it is just a
# transaction locked until block 499999999 -- so it would sit unconfirmed
# forever on both chains. assert_replay_protected() below refuses it.
#
# Serialization is unchanged and there is no sighash change, so any Bitcoin
# wallet, library or hardware signer can produce one. Note this is one below
# bitcoin.NLOCKTIME_BLOCKHEIGHT_MAX, so the Qt locktime editor can still
# represent it as a "block height".
#
# interpreter.cpp's CheckLockTime is also taught to skip this value, so a CLTV
# script in a tx carrying it is not compared against a bogus height. No wallet
# impact; noted so it is not rediscovered.
LOCKTIME_THRESHOLD = 500_000_000     # Bitcoin's height/timestamp boundary
LOCKTIME = LOCKTIME_THRESHOLD - 2    # 499999998

# Protection is only armed if nLockTime is actually enforced, which requires at
# least one input with nSequence != 0xffffffff. Electrum's default is
# 0xfffffffd, which is fine; wallet.py asserts it rather than assuming it.
SEQUENCE_FINAL = 0xffffffff


# -- Identity ----------------------------------------------------------------

# For the record: ECX mainnet's P2P network magic is 0xeca5dcb7 and its P2P
# port 8533 (betanet was 0xeca5b104). Electrum never speaks the P2P protocol --
# it talks to an Electrum server, which does -- so neither value appears in
# this codebase beyond this comment. The server's own identity is checked via
# the genesis hash (useless here, shared with Bitcoin) and, decisively, by
# FORK_BITS at the fork block and the checkpoints.

# Must NOT be 'bitcoin'. ECX addresses are indistinguishable from BTC addresses,
# so registering the bitcoin: handler would let this wallet answer a BTC invoice
# with an ECX payment -- funds lost, payee sees nothing.
URI_SCHEME = 'ecx'

# User-visible application name. Decided: "Electrum eCash" -- qualified rather
# than plain "Electrum", so it never reads as upstream's client.
# The Python package stays `electrum` internally: renaming it would touch 1352
# import lines for no user benefit.
APP_NAME = "Electrum eCash"

# Our release number on top of the upstream base in version.py. The displayed
# version is e.g. "4.8.3-ecx3": the upstream half tells a user or auditor exactly
# which Electrum release this is built from, which matters because that is the
# code that has been reviewed by everyone else.
#
# version.ELECTRUM_VERSION itself must stay bare "X.Y.Z" -- plugin.py feeds it to
# StrictVersion, which rejects any suffix.
#
# BUMP THIS WHENEVER THE CHAIN PARAMETERS ABOVE CHANGE, not only for feature
# releases. ecx1 was an alphanet build, ecx2 betanet, ecx3 the first mainnet
# build. Two binaries reporting the same version while syncing different chains
# is precisely the confusion this fork exists to prevent -- and since ECX
# addresses are indistinguishable from Bitcoin's, a user cannot tell which chain
# they are on by looking.
RELEASE = 3

SUMMARY = "eCash (ECX) Wallet"
DESCRIPTION = ("A lightweight eCash (ECX) wallet, forked from Electrum. Startup is "
               "instant because it works with servers that handle the heavy indexing.")


def version_string(upstream_version: str) -> str:
    """Display version, e.g. 4.8.3-ecx3."""
    return f"{upstream_version}-ecx{RELEASE}"

# Read by base_crash_reporter.py to detect a forked codebase and refuse to send
# crash reports to upstream's crashhub. Upstream provides this hook for forks.
GIT_REPO_URL = "https://github.com/ecash-com/electrum-ecash"
GIT_REPO_ISSUES_URL = "https://github.com/ecash-com/electrum-ecash/issues"
RELEASE_NOTES_URL = ("https://raw.githubusercontent.com/ecash-com/electrum-ecash"
                     "/refs/heads/master/RELEASE-NOTES")

# Help-menu destinations. Upstream's point at electrum.org / docs.electrum.org,
# which are Bitcoin Electrum's -- including its download page.
WEBSITE_URL = "https://ecash.com"
DOCS_URL = "https://github.com/ecash-com/electrum-ecash"

# Update checks: DISABLED until we host a signed version feed of our own.
#
# Upstream's checker fetches https://electrum.org/version, verifies the reply
# against the Electrum maintainers' signing keys, and links to
# https://electrum.org/#download. Left enabled, this wallet would offer its
# users a *Bitcoin Electrum* download as an "update" -- and because ECX and BTC
# addresses are identical, someone who took it could open their wallet file in
# Bitcoin Electrum and spend real BTC believing it was ECX.
#
# To enable later: host a `version` file, sign it with keys we control, and set
# all three of these. The GUI stays silent while UPDATE_CHECK_URL is None.
UPDATE_CHECK_URL = None
UPDATE_DOWNLOAD_URL = None
UPDATE_SIGNING_KEYS = ()

# Data directory. Under our "mainnet IS ECX" model, BitcoinMainnet.datadir_subdir()
# returns None (top level), so without this an ECX build would read and write
# ~/.electrum/ -- the same wallets and blockchain_headers as the user's real
# Bitcoin Electrum, corrupting both.
DATADIR_POSIX = ".electrum-ecash"
DATADIR_WINDOWS = "Electrum eCash"


# -- Denomination ------------------------------------------------------------

# ECX inherits Bitcoin's divisibility exactly: 8 decimals, 1e8 base units.
# Only the names change. Showing "mBTC" for an ECX balance is the same class of
# error as linking a Bitcoin block explorer -- it names the wrong chain.
TICKER = 'ECX'
# The smallest unit is the "szat" (after Sztorc), not the satoshi.
SMALLEST_UNIT = 'szat'
BASE_UNITS = {TICKER: 8, 'm' + TICKER: 5, 'bits': 2, SMALLEST_UNIT: 0}
BASE_UNITS_LIST = [TICKER, 'm' + TICKER, 'bits', SMALLEST_UNIT]


# -- Servers & explorers -----------------------------------------------------

# From https://drivechain.dev/config, network "ecash" (explorer_*_template).
BLOCK_EXPLORERS = {
    'explorer.ecash.ninja': ('https://explorer.ecash.ninja/',
                             {'tx': 'tx/', 'addr': 'address/'}),
}

# Which of the above is selected out of the box.
#
# Upstream's default is 'Blockstream.info', which is not one of ours, and
# util.block_explorer() falls back to *the default* when the configured name is
# missing -- so with upstream's value every fresh install resolves to no
# explorer at all and "View on block explorer" silently does nothing. Same for
# anyone whose config still names a pre-launch (alphanet/betanet) host. Derived from the dict
# rather than spelled out, so a rename cannot reintroduce the dangling default.
BLOCK_EXPLORER_DEFAULT = next(iter(BLOCK_EXPLORERS))


class NotReplayProtectedException(Exception):
    """Raised when a transaction would be broadcast without replay protection."""


def assert_replay_protected(tx) -> None:
    """Refuse to broadcast a transaction that could replay onto Bitcoin.

    Two conditions, both required, per ECX's IsFinalTx:
      - nLockTime == LOCKTIME, the magic 'final on ECX, never final on BTC' value
      - at least one input with nSequence != 0xffffffff, or nLockTime is ignored
        entirely and the transaction is replayable despite carrying the marker

    Electrum always satisfies both (see wallet.get_locktime_for_new_transaction,
    and nsequence defaults of 0xfffffffe / 0xfffffffd), so this never fires in
    normal use. It exists because the failure it guards against is silent and
    irreversible: the transaction confirms on ECX, someone rebroadcasts it on
    Bitcoin, and the user's BTC moves too.
    """
    if tx.locktime != LOCKTIME:
        raise NotReplayProtectedException(
            f"refusing to broadcast: nLockTime is {tx.locktime}, expected {LOCKTIME}. "
            f"This transaction could be replayed onto Bitcoin and move real BTC.")
    if all(txin.nsequence == SEQUENCE_FINAL for txin in tx.inputs()):
        raise NotReplayProtectedException(
            f"refusing to broadcast: every input has nSequence == 0x{SEQUENCE_FINAL:08x}, "
            f"so nLockTime is not enforced and the replay protection is inert. "
            f"This transaction could be replayed onto Bitcoin and move real BTC.")
