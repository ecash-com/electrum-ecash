#!/usr/bin/env python3
"""Regenerate electrum/chains/mainnet/checkpoints.json from a synced header chain.

    .venv/bin/python contrib/ecx/make-checkpoints.py [--min-depth N] [--dry-run] [--headers PATH]

A checkpoint is a pair (hash of the last block of chunk i, target of chunk
i+1). Electrum uses them to skip header validation below the pinned region and
to refuse any chain that disagrees with a pinned hash.

PINS STOP AT THE FORK. ECX's post-fork difficulty algorithm retargets every 288
blocks, so a post-fork chunk has no single target and cannot be expressed in
this format; blockchain.get_checkpoints() stops at ecx.FORK_CHUNK entries. The
last possible entry (index FORK_CHUNK - 1) pins the last shared Bitcoin block
(ECASH_HEIGHT - 1) together with the fork block's fixed reset target
(ecx.FORK_BITS), and everything from the fork block on is downloaded and
verified header by header, which is cheap: the post-fork chain is small.

Chain identity is therefore NOT provided by checkpoints but by the fork block
itself: blockchain.verify_header compares bits for EXACT equality, so a Bitcoin
server's header at ECASH_HEIGHT fails against ecx.FORK_BITS and the server is
dropped. Electrum's genesis-hash check cannot help -- ECX inherits Bitcoin's
genesis. Checkpoints here are a startup optimisation plus a pin of shared
history, and nothing more.

Before the fork block exists the generator can pin at most FORK_CHUNK - 1
entries (through chunk FORK_CHUNK - 2); run it again once the fork block is
mined and a day or so deep to add the final entry.

Requires a synced daemon (or --headers pointing at its blockchain_headers):
    .venv/bin/python ./run_electrum daemon -d
"""
import argparse, json, shutil, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from electrum import ecx                                             # noqa: E402
from electrum.blockchain import (BlockchainManager, Blockchain,      # noqa: E402
                                 CHUNK_SIZE, deserialize_header, HEADER_SIZE)
from electrum.util import user_dir                                   # noqa: E402

OUT = ROOT / "electrum" / "chains" / "mainnet" / "checkpoints.json"
FORK_TARGET = Blockchain.bits_to_target(ecx.FORK_BITS)
MAX_ENTRIES = ecx.FORK_CHUNK          # see module docstring


def die(msg):
    sys.exit(f"\nREFUSING: {msg}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-depth", type=int, default=144,
                    help="do not pin a chunk whose last block is fewer than this many "
                         "blocks below the tip (default 144, one day). Pre-fork blocks are "
                         "Bitcoin history and effectively final well before that; the "
                         "fork block itself is on a fresh low-difficulty chain, so give "
                         "the final entry a day.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--headers", default=None, help="path to blockchain_headers")
    args = ap.parse_args()

    src = Path(args.headers or (Path(user_dir()) / "blockchain_headers"))
    if not src.is_file():
        die(f"no header file at {src}. Sync first: ./run_electrum daemon -d")

    # Work on a copy: BlockchainManager is the live client's loader and may
    # *repair* (truncate or delete) a header file it considers inconsistent
    # with the shipped checkpoints. Never let it touch the daemon's file.
    tmp = Path(tempfile.mkdtemp(prefix="ecx-cp-"))
    hdr_path = tmp / "blockchain_headers"
    shutil.copyfile(src, hdr_path)

    n_headers = hdr_path.stat().st_size // HEADER_SIZE
    tip = n_headers - 1
    fork = ecx.ECASH_HEIGHT
    print(f"headers      : {src}")
    print(f"tip          : {tip:,}")
    print(f"ECASH_HEIGHT : {fork:,}  (chunk {ecx.FORK_CHUNK}; max {MAX_ENTRIES} entries)")

    def read(h):
        with open(hdr_path, "rb") as f:
            f.seek(h * HEADER_SIZE)
            return deserialize_header(f.read(HEADER_SIZE), h)

    # --- is this the chain ecx.py describes? Only checkable once the fork block exists.
    if tip >= fork:
        at_fork, before = read(fork)["bits"], read(fork - 1)["bits"]
        print(f"bits @ {fork-1:,} : 0x{before:08x}")
        print(f"bits @ {fork:,} : 0x{at_fork:08x}")
        if at_fork != ecx.FORK_BITS:
            die(f"block {fork:,} has bits 0x{at_fork:08x}, not 0x{ecx.FORK_BITS:08x}. This "
                f"chain did NOT reset difficulty at ECASH_HEIGHT, so it is not the chain "
                f"ecx.py describes -- most likely you are synced to Bitcoin or to a "
                f"pre-launch ECX network.")
        if before == ecx.FORK_BITS:
            die(f"block {fork-1:,} ALREADY carries the reset bits; the fork is not here.")
        print("  -> difficulty resets exactly at ECASH_HEIGHT. Chain identity confirmed.")
    else:
        print(f"  -> tip is below the fork: this is shared Bitcoin history, identical on "
              f"every chain. Pinning it is safe; the final entry must wait for block {fork:,}.")

    bc_mgr = BlockchainManager(headers_dir=tmp)
    bc = bc_mgr.get_best_chain()
    if bc.height() != tip:
        die(f"loader kept {bc.height():,} of {tip:,} headers: the file disagrees with the "
            f"checkpoints already shipped. Resync from scratch before generating.")

    n_chunks = (tip - args.min_depth + 1) // CHUNK_SIZE   # chunks whose last block is deep enough
    keep = min(max(n_chunks, 0), MAX_ENTRIES)
    print(f"\ndeep chunks  : {n_chunks} (last block >= {args.min_depth} below tip)")
    print(f"writing      : {keep} entries, covering to height {keep*CHUNK_SIZE-1:,}"
          + ("  (COMPLETE: reaches the fork)" if keep == MAX_ENTRIES else
             f"  ({MAX_ENTRIES-keep} short of the fork; rerun later)"))

    cp = [[bc.get_hash((i + 1) * CHUNK_SIZE - 1), bc.get_target(i)] for i in range(keep)]

    # --- validate before writing
    old = json.loads(OUT.read_text())
    if len(cp) < len(old):
        die(f"would shrink the file from {len(old)} to {len(cp)} entries. Checkpoints only "
            f"grow; if the old entries are from a pre-launch network, delete them by hand "
            f"and say so in the commit.")
    for i, (a, b) in enumerate(zip(old, cp)):
        if a != b:
            what = (f"hash {a[0][:20]}... -> {b[0][:20]}..." if a[0] != b[0] else
                    f"target 0x{Blockchain.target_to_bits(a[1]):08x} -> "
                    f"0x{Blockchain.target_to_bits(b[1]):08x} (hash unchanged)")
            die(f"entry {i} changed ({what}). Every entry is pre-fork Bitcoin history and "
                f"must never move. Either this header file is not Bitcoin/ECX, or the "
                f"shipped file is wrong. Not writing.")
    print(f"validated    : {len(old)} existing entries unchanged")
    if keep == MAX_ENTRIES and cp[-1][1] != FORK_TARGET:
        die(f"final entry's target is not FORK_BITS 0x{ecx.FORK_BITS:08x}: the difficulty-"
            f"reset code in blockchain.get_target is not in effect.")
    if keep == MAX_ENTRIES:
        print(f"               final entry pins block {fork-1:,} with the reset target "
              f"0x{ecx.FORK_BITS:08x}")

    if args.dry_run:
        print("\n(dry run -- nothing written)")
    else:
        OUT.write_text(json.dumps(cp, indent=4) + "\n")
        print(f"\nwrote {OUT} ({len(cp)} entries, {OUT.stat().st_size:,} bytes)")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
