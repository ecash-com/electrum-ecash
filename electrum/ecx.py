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
# launch, so THIS IS THE ONE LINE THAT CHANGES PER PHASE:
#     alpha 963648 (2026-08-23) | beta 967680 (2026-09-20) | full 973728 (2026-10-31)
ECASH_HEIGHT = 963648

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

# Read by base_crash_reporter.py to detect a forked codebase and refuse to send
# crash reports to upstream's crashhub. Upstream provides this hook for forks.
GIT_REPO_URL = "https://github.com/ecash-com/electrum-ecash"
GIT_REPO_ISSUES_URL = "https://github.com/ecash-com/electrum-ecash/issues"

# Data directory. Under our "mainnet IS ECX" model, BitcoinMainnet.datadir_subdir()
# returns None (top level), so without this an ECX build would read and write
# ~/.electrum/ -- the same wallets and blockchain_headers as the user's real
# Bitcoin Electrum, corrupting both.
DATADIR_POSIX = ".electrum-ecash"
DATADIR_WINDOWS = "Electrum-eCash"


# -- Servers & explorers -----------------------------------------------------

BLOCK_EXPLORERS = {
    'explorer.alpha.ecash.ninja': ('https://explorer.alpha.ecash.ninja/',
                                   {'tx': 'tx/', 'addr': 'address/'}),
}
