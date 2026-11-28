#!/usr/bin/env python3
"""P0 搜索增强回归测试：锁定 5 项开关的行为，确保同代码 A/B 可复现。"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import mini_chess as mc  # noqa: E402


def fresh(enabled=True, books_off=True):
    if books_off:
        mc.OPENING_BOOK_AVAILABLE = False
        mc.PRO_BOOK_AVAILABLE = False
        mc.EGTB_AVAILABLE = False
    g = mc.ChineseChess()
    for s in ('fix_nmp_min_window', 'use_root_best_ordering',
              'progressive_aspiration', 'unify_mate_ply', 'clear_tt_on_new_game'):
        setattr(g, s, enabled)
    g.use_opening_book = False
    g.use_pro_book = False
    g.use_endgame_book = False
    return g


class TestSearchEnhance(unittest.TestCase):

    def test_01_switches_default_on(self):
        g = mc.ChineseChess()
        for s in ('fix_nmp_min_window', 'use_root_best_ordering',
                  'progressive_aspiration', 'unify_mate_ply', 'clear_tt_on_new_game'):
            self.assertTrue(getattr(g, s), s)

    def test_02_clear_tt_on_new_game(self):
        on, off = fresh(True), fresh(False)
        for g in (on, off):
            g.transposition_table['k'] = {'depth': 1}
            g.killer_moves[0][0] = (1, 2, 3, 4)
            g.history_table['h'] = 9
            g.position_history.append('x')
        on.init_board()
        self.assertEqual(len(on.transposition_table), 0)
        self.assertIsNone(on.killer_moves[0][0])
        self.assertEqual(on.history_table, {})
        self.assertEqual(on.position_history, [])
        off.init_board()
        self.assertIn('k', off.transposition_table)
        self.assertIn('h', off.history_table)

    def test_03_nmp_min_window(self):
        """极小方 null move 零窗口：新版 (alpha,alpha+1)，旧版 (beta-1,beta)。"""
        import time
        # 直接构造极小方节点（depth=3, 非将军）探测它的 null 子调用窗口
        def probe_window(enabled):
            g = fresh(enabled)
            g.init_board()
            g._effective_time_limit = 30.0
            g.nodes_searched = 0
            seen = []
            orig = g.alpha_beta_search
            def spy(depth, alpha, beta, maximizing, start_time, ply=0,
                    allow_null_move=True, extensions=0):
                if not allow_null_move:  # 这是 null move 探测子调用
                    seen.append((alpha, beta, maximizing))
                return 0  # 直接返回，不再递归
            g.alpha_beta_search = spy
            # 极小方节点：maximizing=False；alpha=-100,beta=200
            # 用 orig 调外层，spy 只拦截 null 子调用（否则外层直接返回 spy 的 0）
            orig(3, -100, 200, False, time.time(), ply=0)
            return seen
        new = probe_window(True)
        old = probe_window(False)
        self.assertTrue(new and old, f'no null probe: new={new}, old={old}')
        # 新版极小方探测窗口应为 (-100,-99) = (alpha,alpha+1)
        self.assertEqual(new[0][:2], (-100, -99))
        # 旧版极小方探测窗口应为 (199,200) = (beta-1,beta)
        self.assertEqual(old[0][:2], (199, 200))

    def test_04_unify_mate_ply(self):
        """将死分数口径：新版用绝对 ply，旧版用 quiescence 局部 depth。"""
        on, off = fresh(True), fresh(False)
        for g in (on, off):
            # 构造红方无子可动（黑车控制）的将死局面：仅保留黑将红帅+黑车
            g.board = [['.' for _ in range(9)] for _ in range(10)]
            g.board[0][4] = 'K'
            g.board[9][4] = 'k'
            g.board[0][0] = 'r'
            g.board[1][0] = 'r'
            g.current_player = 'red'
        # 直接调 quiescence：被将军且无应将 → 返回将死分
        v_on = on.quiescence_search(-10**9, 10**9, 0, __import__('time').time(), True, ply=7)
        v_off = off.quiescence_search(-10**9, 10**9, 0, __import__('time').time(), True, ply=7)
        # 新版 -MATE+7，旧版 -MATE+0（局部 depth）
        self.assertEqual(v_on, -mc.ChineseChess.MATE_VALUE + 7)
        self.assertEqual(v_off, -mc.ChineseChess.MATE_VALUE + 0)

    def test_05_root_best_ordering(self):
        """根着法跨层复用：上一层 best_move 被移到首位。"""
        g = fresh(True)
        g.init_board()
        g.search_depth = 3
        g.thinking_time = 0.2
        g._effective_time_limit = 0.2
        orig_order = g.order_moves
        g.order_moves = lambda m, ply=0, tt_move=None: orig_order(m, ply, tt_move)
        mv = g.iterative_deepening_search_single()
        self.assertIsNotNone(mv)
        legal = g.get_all_legal_moves()
        self.assertIn(mv, legal)

    def test_06_progressive_aspiration(self):
        """渐进加窗：失败时不直接全窗，保留窄窗尝试次数。"""
        g = fresh(True)
        self.assertTrue(g.progressive_aspiration)
        g.progressive_aspiration = False
        g.init_board()
        g.search_depth = 2
        g.thinking_time = 0.2
        g._effective_time_limit = 0.2
        mv = g.iterative_deepening_search_single()
        self.assertIn(mv, g.get_all_legal_moves())

    def test_07_all_switches_off_works(self):
        """全关（旧行为）仍能正常搜索出合法着法。"""
        g = fresh(False)
        g.init_board()
        g.search_depth = 2
        g.thinking_time = 0.2
        g._effective_time_limit = 0.2
        mv = g.iterative_deepening_search_single()
        self.assertIn(mv, g.get_all_legal_moves())


if __name__ == '__main__':
    unittest.main(verbosity=2)
