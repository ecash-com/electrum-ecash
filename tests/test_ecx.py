# ECX: tests for the fork's own code. Upstream's test files are never edited.
import os
import tempfile
from pathlib import Path
from unittest import mock

from electrum import constants, ecx
from electrum.blockchain import (Blockchain, BlockchainManager, MissingHeader,
                                 MAX_TARGET, CHUNK_SIZE, _CHAINWORK_CACHE)

from . import ElectrumTestCase

FORK = ecx.ECASH_HEIGHT
P = ecx.POST_FORK_RETARGET_INTERVAL
T = ecx.POST_FORK_TARGET_TIMESPAN
FORK_TARGET = Blockchain.bits_to_target(ecx.FORK_BITS)


def _hdr(bits: int, timestamp: int) -> dict:
    return {'bits': bits, 'timestamp': timestamp}


class TestParameters(ElectrumTestCase):

    def test_mainnet_parameters(self):
        # from ecash-com/bitcoin master, src/kernel/chainparams.cpp
        self.assertEqual(973728, ecx.ECASH_HEIGHT)
        self.assertEqual(0x1901a6e1, ecx.FORK_BITS)
        self.assertEqual(483, ecx.FORK_CHUNK)
        self.assertEqual(482, ecx.FORK_TARGET_OVERRIDE_CHUNK)
        # src/consensus/tx_verify.cpp: `tx.nLockTime == LOCKTIME_THRESHOLD - 2`
        self.assertEqual(499999998, ecx.LOCKTIME)
        # fork height sits on both retarget grids
        self.assertEqual(0, FORK % CHUNK_SIZE)
        self.assertEqual(0, FORK % P)
        self.assertEqual(288, P)
        self.assertEqual(172800, T)

    def test_fork_target_roundtrips_through_compact(self):
        self.assertEqual(ecx.FORK_BITS, Blockchain.target_to_bits(FORK_TARGET))
        # difficulty 2.6e9, as chainparams.cpp's comment says
        self.assertAlmostEqual(2.6e9, MAX_TARGET / FORK_TARGET, delta=0.05e9)


class TestReplayProtection(ElectrumTestCase):

    class _Tx:
        def __init__(self, locktime, nsequences):
            self.locktime = locktime
            self._ins = [mock.Mock(nsequence=n) for n in nsequences]

        def inputs(self):
            return self._ins

    def test_wallet_locktime_is_the_magic_value(self):
        from electrum.wallet import get_locktime_for_new_transaction
        self.assertEqual(ecx.LOCKTIME, get_locktime_for_new_transaction(None))

    def test_accepts_protected_tx(self):
        ecx.assert_replay_protected(self._Tx(ecx.LOCKTIME, [0xfffffffd]))
        ecx.assert_replay_protected(self._Tx(ecx.LOCKTIME, [0xffffffff, 0xfffffffe]))

    def test_rejects_wrong_locktime(self):
        for lt in (0, 499999999, 500000000, ecx.LOCKTIME - 1):
            with self.assertRaises(ecx.NotReplayProtectedException):
                ecx.assert_replay_protected(self._Tx(lt, [0xfffffffd]))

    def test_rejects_all_inputs_final(self):
        with self.assertRaises(ecx.NotReplayProtectedException):
            ecx.assert_replay_protected(self._Tx(ecx.LOCKTIME, [0xffffffff, 0xffffffff]))


class TestPostForkDAAArithmetic(ElectrumTestCase):
    """ecx.post_fork_next_target against pow.cpp's CalculateNextWorkRequired."""

    def test_window_start(self):
        # first window is clamped at the fork and spans 288 blocks ...
        self.assertEqual(FORK, ecx.post_fork_window_start(FORK + P))
        # ... every later one spans 289, sharing a block with the previous window
        self.assertEqual(FORK + P - 1, ecx.post_fork_window_start(FORK + 2 * P))
        self.assertEqual(FORK + 2 * P - 1, ecx.post_fork_window_start(FORK + 3 * P))
        self.assertEqual(FORK + 99 * P - 1, ecx.post_fork_window_start(FORK + 100 * P))

    def test_retarget_heights(self):
        self.assertTrue(ecx.is_post_fork_retarget_height(FORK + P))
        self.assertTrue(ecx.is_post_fork_retarget_height(FORK + CHUNK_SIZE))
        for h in (FORK + 1, FORK + P - 1, FORK + P + 1, FORK + 2016 - 1):
            self.assertFalse(ecx.is_post_fork_retarget_height(h), h)

    def test_on_schedule_keeps_target(self):
        self.assertEqual(FORK_TARGET, ecx.post_fork_next_target(FORK_TARGET, 1000, 1000 + T, MAX_TARGET))

    def test_dampening_is_six_to_one(self):
        # blocks took twice as long: Bitcoin would double the target, ECX moves 1/7 of the way
        new = ecx.post_fork_next_target(FORK_TARGET, 0, 2 * T, MAX_TARGET)
        self.assertEqual(FORK_TARGET * 8 // 7, new)
        # blocks came twice as fast
        new = ecx.post_fork_next_target(FORK_TARGET, 0, T // 2, MAX_TARGET)
        self.assertEqual(FORK_TARGET * 13 // 14, new)

    def test_clamps(self):
        # actual < T/4 is clamped to T/4 -> factor (6T + T/4) / 7T = 25/28
        self.assertEqual(FORK_TARGET * 25 // 28, ecx.post_fork_next_target(FORK_TARGET, 0, 1, MAX_TARGET))
        self.assertEqual(FORK_TARGET * 25 // 28, ecx.post_fork_next_target(FORK_TARGET, 0, T // 4, MAX_TARGET))
        # negative timespans (timestamps going backwards) clamp the same way
        self.assertEqual(FORK_TARGET * 25 // 28, ecx.post_fork_next_target(FORK_TARGET, 1000, 0, MAX_TARGET))
        # actual > 4T is clamped to 4T -> factor 10/7
        self.assertEqual(FORK_TARGET * 10 // 7, ecx.post_fork_next_target(FORK_TARGET, 0, 4 * T, MAX_TARGET))
        self.assertEqual(FORK_TARGET * 10 // 7, ecx.post_fork_next_target(FORK_TARGET, 0, 10 ** 9, MAX_TARGET))

    def test_pow_limit_cap(self):
        self.assertEqual(MAX_TARGET, ecx.post_fork_next_target(MAX_TARGET, 0, 4 * T, MAX_TARGET))
        self.assertEqual(MAX_TARGET, ecx.post_fork_next_target(MAX_TARGET * 9 // 10, 0, 4 * T, MAX_TARGET))

    def test_no_uint256_overflow(self):
        # arith_uint256 wraps at 2**256; our ints do not, so the intermediate product
        # must stay below it for every reachable input
        self.assertLess(MAX_TARGET * (6 * T + 4 * T), 2 ** 256)


class TestPostForkTargetForHeight(ElectrumTestCase):
    """Blockchain.get_target_for_height with an injected header lookup."""

    def setUp(self):
        super().setUp()
        self.config_dir = self.electrum_path
        self.bc_mgr = BlockchainManager(headers_dir=Path(self.config_dir))
        self.chain = self.bc_mgr.get_best_chain()

    def _lookup(self, headers: dict):
        return lambda h: headers.get(h)

    def test_pre_fork_uses_bitcoin_chunk_target(self):
        # genesis chunk comes from the checkpoints
        self.assertEqual(MAX_TARGET, self.chain.get_target_for_height(0))
        self.assertEqual(self.chain.get_target(0), self.chain.get_target_for_height(CHUNK_SIZE))

    def test_fork_block_carries_fork_bits_regardless_of_headers(self):
        self.assertEqual(FORK_TARGET, self.chain.get_target_for_height(FORK, self._lookup({})))

    def test_between_retargets_keeps_previous_bits(self):
        bits = 0x1901a000
        headers = {FORK + 4: _hdr(bits, 1)}
        self.assertEqual(Blockchain.bits_to_target(bits),
                         self.chain.get_target_for_height(FORK + 5, self._lookup(headers)))
        # the retarget period right after the fork
        headers = {FORK: _hdr(ecx.FORK_BITS, 1)}
        self.assertEqual(FORK_TARGET, self.chain.get_target_for_height(FORK + 1, self._lookup(headers)))

    def test_first_retarget_window_is_288_blocks_from_fork(self):
        t0 = 1_800_000_000
        headers = {FORK: _hdr(ecx.FORK_BITS, t0),
                   FORK + P - 1: _hdr(ecx.FORK_BITS, t0 + T)}
        # exactly on schedule -> unchanged
        self.assertEqual(FORK_TARGET, self.chain.get_target_for_height(FORK + P, self._lookup(headers)))
        # twice as slow -> 8/7, rounded through compact bits
        headers[FORK + P - 1] = _hdr(ecx.FORK_BITS, t0 + 2 * T)
        expected = Blockchain.bits_to_target(Blockchain.target_to_bits(FORK_TARGET * 8 // 7))
        self.assertEqual(expected, self.chain.get_target_for_height(FORK + P, self._lookup(headers)))

    def test_second_retarget_window_is_289_blocks(self):
        t0 = 1_800_000_000
        bits = ecx.FORK_BITS
        headers = {
            FORK + P - 1: _hdr(bits, t0),            # shared with the previous window
            FORK + P: _hdr(bits, t0 + 600),          # NOT the window start
            FORK + 2 * P - 1: _hdr(bits, t0 + T),
        }
        self.assertEqual(FORK_TARGET, self.chain.get_target_for_height(FORK + 2 * P, self._lookup(headers)))
        # if the window wrongly started at FORK+P the timespan would be T-600 -> a different target
        wrong = Blockchain.bits_to_target(Blockchain.target_to_bits(
            ecx.post_fork_next_target(FORK_TARGET, t0 + 600, t0 + T, MAX_TARGET)))
        self.assertNotEqual(FORK_TARGET, wrong)

    def test_uses_last_blocks_bits_not_forks(self):
        bits = 0x1901f000
        t0 = 100
        headers = {FORK + P - 1: _hdr(bits, t0), FORK + 2 * P - 1: _hdr(bits, t0 + T)}
        self.assertEqual(Blockchain.bits_to_target(bits),
                         self.chain.get_target_for_height(FORK + 2 * P, self._lookup(headers)))

    def test_missing_headers_raise(self):
        with self.assertRaises(MissingHeader):
            self.chain.get_target_for_height(FORK + 1, self._lookup({}))
        with self.assertRaises(MissingHeader):
            # last block present, window start missing
            self.chain.get_target_for_height(FORK + P, self._lookup({FORK + P - 1: _hdr(ecx.FORK_BITS, 5)}))

    def test_get_target_refuses_post_fork_chunks(self):
        self.assertEqual(FORK_TARGET, self.chain.get_target(ecx.FORK_TARGET_OVERRIDE_CHUNK))
        with self.assertRaises(ValueError):
            self.chain.get_target(ecx.FORK_CHUNK)


class TestPostForkChainwork(ElectrumTestCase):

    def setUp(self):
        super().setUp()
        self.bc_mgr = BlockchainManager(headers_dir=Path(self.electrum_path))
        self.chain = self.bc_mgr.get_best_chain()
        self._saved_cache = dict(_CHAINWORK_CACHE)
        _CHAINWORK_CACHE.clear()
        _CHAINWORK_CACHE["00" * 32] = 0

    def tearDown(self):
        _CHAINWORK_CACHE.clear()
        _CHAINWORK_CACHE.update(self._saved_cache)
        super().tearDown()

    def test_sums_work_per_288_block_period(self):
        bits_a, bits_b = 0x1901a6e1, 0x1901a000
        work = lambda b: Blockchain._work_for_target(Blockchain.bits_to_target(b))
        # period 0 (fork .. fork+287) at bits_a, period 1 at bits_b, 3 blocks of period 2 at bits_b
        def read_header(h):
            if h < FORK:
                return None
            return _hdr(bits_a if h < FORK + P else bits_b, 0)
        PRE = 12345
        with mock.patch.object(self.chain, 'read_header', side_effect=read_header), \
             mock.patch.object(self.chain, 'get_hash', side_effect=lambda h: f"{h:064x}"), \
             mock.patch.object(self.chain, '_get_chainwork_bitcoin', return_value=PRE) as pre:
            self.assertEqual(PRE + 1 * work(bits_a), self.chain.get_chainwork(FORK))
            self.assertEqual(PRE + P * work(bits_a), self.chain.get_chainwork(FORK + P - 1))
            self.assertEqual(PRE + P * work(bits_a) + work(bits_b), self.chain.get_chainwork(FORK + P))
            self.assertEqual(PRE + P * work(bits_a) + P * work(bits_b) + 3 * work(bits_b),
                             self.chain.get_chainwork(FORK + 2 * P + 2))
            # the pre-fork total is only ever asked for at the last shared block
            for call in pre.call_args_list:
                self.assertEqual((FORK - 1,), call.args)
        # complete periods were cached by hash
        self.assertIn(f"{FORK + 2 * P - 1:064x}", _CHAINWORK_CACHE)
        self.assertNotIn(f"{FORK + 2 * P + 2:064x}", _CHAINWORK_CACHE)
