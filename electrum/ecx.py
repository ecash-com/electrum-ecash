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
type 0'), so a BTC address IS an ECX address. Only three consensus rules differ,
and only the first two are visible to a wallet:

  1. Replay protection via a magic nLockTime  -> LOCKTIME below
  2. A difficulty reset at the fork block     -> ECASH_HEIGHT below
  3. Reassigned Satoshi-era coins (provenance only, no wallet impact)
"""

# -- Fork activation ---------------------------------------------------------

# `consensus.EcashHeight` in ecash-com/bitcoin, src/kernel/chainparams.cpp.
# Launch is phased and alpha/beta coins are destroyed and reissued at full
# launch, so this changes per phase:
#     alpha 963648 (2026-08-23) | beta 967680 (2026-09-20) | full 973728 (2026-10-31)
#
# CURRENT PHASE: beta. Tracking the `betanet` branch of ecash-com/bitcoin.
#
# Each phase is a DIFFERENT chain, forked from Bitcoin at a different height --
# not a continuation of the previous one. Between alpha's fork and beta's, the
# alpha chain has its own blocks while the beta chain still has Bitcoin's. So a
# phase switch is never just this constant: FORK_BITS below and the pinned
# hashes in chains/mainnet/checkpoints.json must move with it, or the client
# refuses to sync the new chain. See contrib/ecx/make-checkpoints.py.
ECASH_HEIGHT = 967680

# Bitcoin's difficulty retarget interval. Same as blockchain.CHUNK_SIZE, but
# redeclared so this module stays import-free.
RETARGET_INTERVAL = 2016

# All three launch heights are exact multiples of 2016, i.e. retarget
# boundaries. Assert it rather than trust it: if a future phase picks a
# non-boundary height, the reset straddles a chunk and get_target() needs more
# than the one-line override in blockchain.py.
assert ECASH_HEIGHT % RETARGET_INTERVAL == 0, \
    f"ECASH_HEIGHT {ECASH_HEIGHT} is not a retarget boundary"

# The chunk whose headers use the reset target.
FORK_CHUNK = ECASH_HEIGHT // RETARGET_INTERVAL

# blockchain.verify_chunk(index) validates against get_target(index - 1), so the
# override belongs on the chunk *before* the fork chunk.
FORK_TARGET_OVERRIDE_CHUNK = FORK_CHUNK - 1

# `consensus.EcashForkBits` -- the compact target the fork block must carry.
#
# CHANGED IN BETA, and it is not a value you can derive: alphanet reset to
# powLimit (`bnNew = bnPowLimit`, i.e. 0x1d00ffff == blockchain.MAX_TARGET),
# betanet resets to a fixed difficulty of 1e9 (`bnNew.SetCompact(EcashForkBits)`
# in src/pow.cpp). Read it off chainparams.cpp for the phase's branch; do not
# assume it is still powLimit next time.
#
# betanet's validation.cpp enforces this as a consensus rule in its own right
# ("bad-diffbits-ecash-da"), so the fork block carries exactly these bits.
#
# This is the fork's PRIMARY chain-identity guard, and the reason it works is
# that blockchain.verify_header compares bits for EXACT equality rather than as
# a proof-of-work threshold. Real Bitcoin's header at height 967680 carries
# ~0x1702355e, so it fails against our expected 0x19044b7e and a Bitcoin server
# is rejected. Nothing else can do this job: ECX shares Bitcoin's genesis hash,
# so Electrum's usual genesis check (interface.py) passes against a BTC server.
FORK_BITS = 0x19044b7e

# Sanity: a compact target's mantissa must not have its sign bit set, or
# SetCompact reads it as negative and the round-trip through target_to_bits that
# verify_header relies on would not be exact.
assert not (FORK_BITS & 0x00800000), f"FORK_BITS {FORK_BITS:#010x} has the sign bit set"


# -- Replay protection -------------------------------------------------------

# ECX's IsFinalTx (src/consensus/tx_verify.cpp) short-circuits to "final" on
# nLockTime == LOCKTIME_THRESHOLD - 1. Bitcoin Core reads the same value as a
# block height ~500M in the future and refuses to relay or mine it, so a tx
# carrying it is valid on ECX and permanently non-final on Bitcoin.
#
# Serialization is unchanged and there is no sighash change, so any Bitcoin
# wallet, library or hardware signer can produce one.
#
# Equals bitcoin.NLOCKTIME_BLOCKHEIGHT_MAX -- both derive from LOCKTIME_THRESHOLD.
LOCKTIME = 499_999_999

# Protection is only armed if nLockTime is actually enforced, which requires at
# least one input with nSequence != 0xffffffff. Electrum's default is
# 0xfffffffd, which is fine; wallet.py asserts it rather than assuming it.
SEQUENCE_FINAL = 0xffffffff


# -- Identity ----------------------------------------------------------------

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
# version is e.g. "4.8.1-ecx1": the upstream half tells a user or auditor exactly
# which Electrum release this is built from, which matters because that is the
# code that has been reviewed by everyone else.
#
# version.ELECTRUM_VERSION itself must stay bare "X.Y.Z" -- plugin.py feeds it to
# StrictVersion, which rejects any suffix.
#
# BUMP THIS WHENEVER THE CHAIN PARAMETERS ABOVE CHANGE, not only for feature
# releases. ecx1 was an alphanet build; ecx2 is betanet. Two binaries reporting
# the same version while syncing different chains is precisely the confusion
# this fork exists to prevent -- and since ECX addresses are indistinguishable
# from Bitcoin's, a user cannot tell which chain they are on by looking.
RELEASE = 2

SUMMARY = "eCash (ECX) Wallet"
DESCRIPTION = ("A lightweight eCash (ECX) wallet, forked from Electrum. Startup is "
               "instant because it works with servers that handle the heavy indexing.")


def version_string(upstream_version: str) -> str:
    """Display version, e.g. 4.8.1-ecx1."""
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

BLOCK_EXPLORERS = {
    'explorer.beta.ecash.ninja': ('https://explorer.beta.ecash.ninja/',
                                  {'tx': 'tx/', 'addr': 'address/'}),
}

# Which of the above is selected out of the box.
#
# Upstream's default is 'Blockstream.info', which is not one of ours, and
# util.block_explorer() falls back to *the default* when the configured name is
# missing -- so with upstream's value every fresh install resolves to no
# explorer at all and "View on block explorer" silently does nothing. Same for
# anyone whose config still names a previous phase's host. Derived from the dict
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
