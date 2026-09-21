#!/usr/bin/env python3
"""Regenerate electrum/chains/mainnet/checkpoints.json from a synced header chain.

    .venv/bin/python contrib/ecx/make-checkpoints.py [--margin N] [--dry-run]

Checkpoints pin real post-fork block hashes, which is what distinguishes this
chain from any other that also reset difficulty at ECASH_HEIGHT.

Note the PRIMARY chain-identity guard is actually C1, the difficulty-reset patch:
verify_header compares bits EXACTLY (`if bits != header['bits']`), not as a PoW
threshold, so Bitcoin's real header at the fork height is rejected against our
expected ecx.FORK_BITS. Electrum's genesis-hash check cannot help us -- ECX
inherits Bitcoin's genesis.

Checkpoints are therefore defence in depth plus a startup optimisation, not the
sole guard. They still matter: only a pinned hash can separate two chains that
reset difficulty at the SAME height with the SAME bits.

RUN THIS AT EVERY PHASE SWITCH, together with the ECASH_HEIGHT and FORK_BITS
changes. FORK_BITS is not derivable -- alphanet reset to powLimit (0x1d00ffff),
betanet resets to difficulty 1e9 (0x19044b7e). Read it off chainparams.cpp.

Alpha, beta and full are three DIFFERENT chains, each forked from Bitcoin at a
different height. Between alpha's fork (963648) and beta's (967680) the alpha
chain has its own blocks while the beta chain still has Bitcoin's. So alpha
checkpoints past chunk 478 make a beta build reject the beta chain outright --
the client simply refuses to sync.

That cuts both ways, and it is why a phase switch is a TWO-PASS job: the stale
checkpoints must be truncated back to the last chunk the two phases share before
the daemon can sync the new chain at all. Do that first:

    ./make-checkpoints.py --truncate-for-sync 963648   # the PREVIOUS fork height

Note the shared prefix ends one entry earlier than you would guess, and getting
this wrong costs an afternoon. `checkpoints[i]` is a PAIR: the hash of the last
block in chunk i, and the target used by chunk i+1. At the previous phase's fork
chunk F, entry F-1 therefore holds that phase's reset target even though its
hash is still shared history. Keeping it makes the client demand the old phase's
difficulty of the new chain's first post-shared chunk, and the sync dies with
"unexpected bad header". So the safe prefix is F-1 entries, not F.

Requires a synced daemon:  .venv/bin/python ./run_electrum daemon -d
"""
import argparse, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from electrum import constants, ecx                     # noqa: E402
from electrum.blockchain import (Blockchain, CHUNK_SIZE,  # noqa: E402
                                 deserialize_header, HEADER_SIZE)
from electrum.simple_config import SimpleConfig         # noqa: E402
from electrum.util import user_dir                      # noqa: E402

OUT = ROOT / "electrum" / "chains" / "mainnet" / "checkpoints.json"
FORK_TARGET = Blockchain.bits_to_target(ecx.FORK_BITS)


def die(msg):
    sys.exit(f"\nREFUSING: {msg}\n")


def truncate_for_sync(prev_fork_height: int, dry_run: bool):
    """Pass 1 of a phase switch: cut the file back to what the two phases share.

    Entry F-1 (F = the previous phase's fork chunk) carries that phase's reset
    TARGET alongside a shared HASH, so the shared prefix is F-1 entries. See the
    module docstring.
    """
    if prev_fork_height % CHUNK_SIZE:
        die(f"{prev_fork_height:,} is not a retarget boundary, so it is not a fork "
            f"height. Pass the previous phase's ECASH_HEIGHT.")
    if prev_fork_height >= ecx.ECASH_HEIGHT:
        die(f"{prev_fork_height:,} is not BELOW the current ECASH_HEIGHT "
            f"({ecx.ECASH_HEIGHT:,}). Phases only move forward; pass the phase you "
            f"are leaving, not the one you are going to.")

    prev_chunk = prev_fork_height // CHUNK_SIZE
    keep = prev_chunk - 1
    cp = json.loads(OUT.read_text())
    print(f"previous fork : {prev_fork_height:,} (chunk {prev_chunk})")
    print(f"current fork  : {ecx.ECASH_HEIGHT:,} (chunk {ecx.FORK_CHUNK})")
    print(f"file          : {len(cp)} entries")
    if len(cp) <= keep:
        print(f"\nalready at or below {keep} entries -- nothing to truncate.")
        return
    print(f"keeping       : {keep} entries (through height {keep*CHUNK_SIZE-1:,})")
    print(f"dropping      : {len(cp)-keep}, from entry {keep}")
    print(f"                entry {keep} holds the previous phase's reset target "
          f"(0x{Blockchain.target_to_bits(cp[keep][1]):08x}) even though its hash is "
          f"shared history -- which is why the cut is at {prev_chunk}-1, not {prev_chunk}.")
    if dry_run:
        print("\n(dry run -- nothing written)")
        return
    OUT.write_text(json.dumps(cp[:keep], indent=4) + "\n")
    print(f"\nwrote {OUT} ({keep} entries)")
    print("Now delete blockchain_headers, sync the new chain, and re-run without "
          "--truncate-for-sync.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", type=int, default=10,
                    help="chunks to leave unpinned below the tip (default 10). "
                         "Post-fork difficulty starts at minimum, so recent blocks "
                         "are cheap to reorg; do not pin right up to the tip.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--truncate-for-sync", type=int, metavar="PREV_FORK_HEIGHT",
                    help="pass 1: drop checkpoints left over from the PREVIOUS phase "
                         "so the daemon can sync the new chain at all, then exit. "
                         "Takes that phase's ECASH_HEIGHT (e.g. 963648 for alpha).")
    ap.add_argument("--headers", default=None, help="path to blockchain_headers")
    args = ap.parse_args()

    if args.truncate_for_sync is not None:
        return truncate_for_sync(args.truncate_for_sync, args.dry_run)

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
    if at_fork != ecx.FORK_BITS:
        die(f"block {fork:,} has bits 0x{at_fork:08x}, not 0x{ecx.FORK_BITS:08x}. "
            f"This chain did NOT reset difficulty at ECASH_HEIGHT, so it is not the "
            f"chain ecx.py describes -- most likely you are synced to Bitcoin, or to a "
            f"different ECX phase. Check ECASH_HEIGHT, FORK_BITS, and which server "
            f"you are on.")
    if before == ecx.FORK_BITS:
        die(f"block {fork-1:,} ALREADY carries the reset bits, so the fork is not here. "
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
            f"the fork chunk {fork_chunk}, so the file would carry no post-fork hash "
            f"and no identity guard. Use --margin {max(0, n_chunks - fork_chunk - 1)} "
            f"or less, or sync further.")

    print(f"\nchunks avail : {n_chunks} (to height {n_chunks*CHUNK_SIZE-1:,})")
    print(f"margin       : {args.margin} chunks unpinned (~{args.margin*CHUNK_SIZE:,} blocks)")
    print(f"writing      : {keep} entries, covering to height {keep*CHUNK_SIZE-1:,}")
    n_post = keep - fork_chunk
    print(f"               {n_post} post-fork -> the identity guard"
          + ("  (THIN -- regenerate once betanet has more depth)" if n_post < 3 else ""))

    cp = []
    for i in range(keep):
        cp.append([bc.get_hash((i + 1) * CHUNK_SIZE - 1), bc.get_target(i)])

    # --- validate before writing ---
    old = json.loads(OUT.read_text())
    diverge = next((i for i in range(min(len(old), len(cp))) if old[i] != cp[i]), None)
    if diverge is not None and diverge < fork_chunk:
        # Below our own fork the chain is still Bitcoin's, so an entry that moved
        # is either a stale previous-phase file or a genuine problem. Only the
        # former is acceptable, and only when said out loud.
        if old[diverge][0] != cp[diverge][0]:
            what = (f"hash {old[diverge][0][:20]}... -> {cp[diverge][0][:20]}...")
        else:
            what = (f"target 0x{Blockchain.target_to_bits(old[diverge][1]):08x} -> "
                    f"0x{Blockchain.target_to_bits(cp[diverge][1]):08x} (hash unchanged)")
        die(f"entry {diverge} changed ({what}) and is below the fork chunk "
            f"{fork_chunk}, where history is still shared with Bitcoin.\n"
            f"  Most likely the file still holds the PREVIOUS phase's checkpoints. "
            f"Run --truncate-for-sync <that phase's ECASH_HEIGHT> first. Note the "
            f"generator reads the file it is about to replace -- get_hash() and "
            f"get_target() both consult it -- so a stale file silently poisons the "
            f"output as well as blocking the sync.\n"
            f"  Otherwise something is genuinely wrong. Not writing.")
    else:
        print(f"\nvalidated    : {min(len(old), fork_chunk)} pre-fork entries unchanged")

    if cp[fork_chunk - 1][1] != FORK_TARGET:
        die(f"entry {fork_chunk-1} target is 0x{cp[fork_chunk-1][1]:x}, not the fork "
            f"target 0x{FORK_TARGET:x} (bits 0x{ecx.FORK_BITS:08x}). The difficulty-reset "
            f"patch (C1) must be applied BEFORE generating checkpoints, or Bitcoin's "
            f"target gets baked in permanently.")
    print(f"               entry {fork_chunk-1} target == FORK_BITS "
          f"0x{ecx.FORK_BITS:08x} (C1 applied)")

    if args.dry_run:
        print("\n(dry run -- nothing written)")
        return
    OUT.write_text(json.dumps(cp, indent=4) + "\n")
    print(f"\nwrote {OUT} ({len(cp)} entries, {OUT.stat().st_size:,} bytes)")
    print("Remember: regenerate at every phase switch, with the ECASH_HEIGHT change.")


if __name__ == "__main__":
    main()
