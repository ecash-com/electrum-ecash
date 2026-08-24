#!/usr/bin/env python3
"""Regenerate electrum/chains/mainnet/checkpoints.json from a synced header chain.

    .venv/bin/python contrib/ecx/make-checkpoints.py [--margin N] [--dry-run]

Checkpoints pin real post-fork block hashes, which is what distinguishes this
chain from any other that also reset difficulty at ECASH_HEIGHT.

Note the PRIMARY chain-identity guard is actually C1, the difficulty-reset patch:
verify_header compares bits EXACTLY (`if bits != header['bits']`), not as a PoW
threshold, so Bitcoin's real header at the fork height (bits 0x17023cc1) is
rejected against our expected 0x1d00ffff. Verified against a live Bitcoin server.
Electrum's genesis-hash check cannot help us -- ECX inherits Bitcoin's genesis.

Checkpoints are therefore defence in depth plus a startup optimisation, not the
sole guard. They still matter: only a pinned hash can separate two chains that
reset difficulty at the SAME height.

RUN THIS AT EVERY PHASE SWITCH, together with the ECASH_HEIGHT change.

Alpha, beta and full are three DIFFERENT chains, each forked from Bitcoin at a
different height. Between alpha's fork (963648) and beta's (967680) the alpha
chain has its own blocks while the beta chain still has Bitcoin's. So alpha
checkpoints past chunk 478 make a beta build reject the beta chain outright --
the client simply refuses to sync. The safety check below is what stops you
shipping that.

Requires a synced daemon:  .venv/bin/python ./run_electrum daemon -d
"""
import argparse, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from electrum import constants, ecx                     # noqa: E402
from electrum.blockchain import (Blockchain, MAX_TARGET, CHUNK_SIZE,  # noqa: E402
                                 deserialize_header, HEADER_SIZE)
from electrum.simple_config import SimpleConfig         # noqa: E402
from electrum.util import user_dir                      # noqa: E402

OUT = ROOT / "electrum" / "chains" / "mainnet" / "checkpoints.json"
MIN_DIFFICULTY_BITS = 0x1d00ffff   # what ECX's powLimit renders as


def die(msg):
    sys.exit(f"\nREFUSING: {msg}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", type=int, default=10,
                    help="chunks to leave unpinned below the tip (default 10). "
                         "Post-fork difficulty starts at minimum, so recent blocks "
                         "are cheap to reorg; do not pin right up to the tip.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--headers", default=None, help="path to blockchain_headers")
    args = ap.parse_args()

    hdr_path = Path(args.headers or (Path(user_dir()) / "blockchain_headers"))
    if not hdr_path.is_file():
        die(f"no header file at {hdr_path}. Sync first: ./run_electrum daemon -d")

    n_headers = hdr_path.stat().st_size // HEADER_SIZE
    tip = n_headers - 1
    fork, fork_chunk = ecx.ECASH_HEIGHT, ecx.FORK_CHUNK
    print(f"headers      : {hdr_path}")
    print(f"tip          : {tip:,}")
    print(f"ECASH_HEIGHT : {fork:,}  (chunk {fork_chunk})")

    def read(h):
        with open(hdr_path, "rb") as f:
            f.seek(h * HEADER_SIZE)
            return deserialize_header(f.read(HEADER_SIZE), h)

    # --- SAFETY: is this header chain actually the chain ecx.py describes? ---
    if tip < fork:
        die(f"synced to {tip:,}, which is below the fork at {fork:,}. "
            f"Nothing past the fork to pin, so no identity guard. Wait for the fork.")

    at_fork = read(fork)["bits"]
    before = read(fork - 1)["bits"]
    print(f"bits @ {fork-1:,} : 0x{before:08x}")
    print(f"bits @ {fork:,} : 0x{at_fork:08x}")
    if at_fork != MIN_DIFFICULTY_BITS:
        die(f"block {fork:,} has bits 0x{at_fork:08x}, not 0x{MIN_DIFFICULTY_BITS:08x}. "
            f"This chain did NOT reset difficulty at ECASH_HEIGHT, so it is not the "
            f"chain ecx.py describes -- most likely you are synced to Bitcoin, or to a "
            f"different ECX phase. Check ECASH_HEIGHT and which server you are on.")
    if before == MIN_DIFFICULTY_BITS:
        die(f"block {fork-1:,} is ALSO at minimum difficulty, so the fork is not here. "
            f"You are probably synced to an earlier-phase chain.")
    print("  -> difficulty resets exactly at ECASH_HEIGHT. Chain identity confirmed.")

    # --- generate ---
    config = SimpleConfig({"electrum_path": str(hdr_path.parent)})
    bc = Blockchain(config=config, forkpoint=0, parent=None,
                    forkpoint_hash=constants.net.GENESIS, prev_hash=None)

    n_chunks = (tip + 1) // CHUNK_SIZE
    keep = max(0, n_chunks - args.margin)
    if keep <= fork_chunk:
        die(f"margin {args.margin} leaves only {keep} chunks, which does not reach past "
            f"the fork chunk {fork_chunk}. Lower --margin or sync further.")

    print(f"\nchunks avail : {n_chunks} (to height {n_chunks*CHUNK_SIZE-1:,})")
    print(f"margin       : {args.margin} chunks unpinned (~{args.margin*CHUNK_SIZE:,} blocks)")
    print(f"writing      : {keep} entries, covering to height {keep*CHUNK_SIZE-1:,}")
    print(f"               {keep - fork_chunk} of them are post-fork -> the identity guard")

    cp = []
    for i in range(keep):
        cp.append([bc.get_hash((i + 1) * CHUNK_SIZE - 1), bc.get_target(i)])

    # --- validate before writing ---
    old = json.loads(OUT.read_text())
    for i in range(min(len(old), fork_chunk)):
        if old[i] != cp[i]:
            die(f"pre-fork entry {i} changed ({old[i][0][:16]}... -> {cp[i][0][:16]}...). "
                f"Pre-fork history is shared with Bitcoin and must be identical. "
                f"Something is wrong -- not writing.")
    print(f"\nvalidated    : {min(len(old), fork_chunk)} pre-fork entries unchanged")
    if cp[fork_chunk - 1][1] != MAX_TARGET:
        die(f"entry {fork_chunk-1} target is not MAX_TARGET. The difficulty-reset patch "
            f"(C1) must be applied BEFORE generating checkpoints, or Bitcoin's target "
            f"gets baked in permanently.")
    print(f"               entry {fork_chunk-1} target == MAX_TARGET (C1 applied)")

    if args.dry_run:
        print("\n(dry run -- nothing written)")
        return
    OUT.write_text(json.dumps(cp, indent=4) + "\n")
    print(f"\nwrote {OUT} ({len(cp)} entries, {OUT.stat().st_size:,} bytes)")
    print("Remember: regenerate at every phase switch, with the ECASH_HEIGHT change.")


if __name__ == "__main__":
    main()
