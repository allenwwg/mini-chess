#!/usr/bin/env python3
"""隔离 A/B：同一份 mini_chess，只切 P0 搜索增强开关，进程内自对弈。

用法:
    python tools/ab_search_enhance.py --games 40 --movetime 200 --out data/ab_search.json

NEW = 五个开关全开（当前默认）；OLD = 五个开关全关（旧行为）。
两侧用同一个 ChineseChess 类，仅开关不同，走子/裁判逻辑共用，做单变量对照。
"""
import argparse
import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import mini_chess as mc  # noqa: E402

SWITCHES = ['fix_nmp_min_window', 'use_root_best_ordering', 'progressive_aspiration',
            'unify_mate_ply', 'clear_tt_on_new_game']


def make_engine(enabled):
    # 裁判/引擎共用走法生成；禁用书库避免启动子进程/联网，纯比搜索
    mc.OPENING_BOOK_AVAILABLE = False
    mc.PRO_BOOK_AVAILABLE = False
    mc.EGTB_AVAILABLE = False
    g = mc.ChineseChess()
    for s in SWITCHES:
        setattr(g, s, enabled)
    g.use_opening_book = False
    g.use_pro_book = False
    g.use_endgame_book = False
    g.init_board()
    return g


def iccs_to_move(s):
    s = s.strip().lower()
    if len(s) != 4 or not s[0].isalpha():
        return None
    try:
        return (int(s[1]), ord(s[0]) - ord('a'), int(s[3]), ord(s[2]) - ord('a'))
    except (ValueError, IndexError):
        return None


def move_to_iccs(m):
    return f"{chr(ord('a') + m[1])}{m[0]}{chr(ord('a') + m[3])}{m[2]}"


def adjudicate(g):
    red = black = 0.0
    vals = {'K': 0, 'A': 2, 'B': 2, 'H': 4, 'C': 4.5, 'R': 9, 'P': 1}
    for row in g.board:
        for p in row:
            if p == '.':
                continue
            v = vals.get(p.upper(), 0)
            if p.isupper():
                red += v
            else:
                black += v
    if red > black + 1:
        return 'red'
    if black > red + 1:
        return 'black'
    return 'draw'


def play_one(engines, movetime_ms, max_plies, seed=0, opening_plies=0):
    """engines = {'red': engine, 'black': engine}。

    seed/opening_plies: 用固定种子随机走若干开局步，让不同局落到多样中局，
    避免确定性引擎在禁开局库时每局重复同一盘棋（统计力不足）。
    """
    arb = make_engine(False)
    moves = []
    dur = movetime_ms / 1000.0
    rng = random.Random(seed)
    for _ in range(opening_plies):
        legal = arb.get_all_legal_moves()
        if not legal:
            break
        arb.make_move(*rng.choice(legal))
        moves.append(move_to_iccs(arb.last_move))
    while True:
        w = arb.winner
        if w is not None:
            if w == 'draw':
                reason = 'draw60' if arb.is_draw_by_60_moves() else 'repetition'
            else:
                reason = 'checkmate' if (arb.is_checkmate('red') or arb.is_checkmate('black')) \
                    else 'long_check'
            return w, reason, moves
        if len(moves) >= max_plies:
            return adjudicate(arb), 'ply_limit', moves
        side = arb.current_player
        eng = engines[side]
        eng.thinking_time = dur
        legal = arb.get_all_legal_moves()
        if not legal:
            return ('black' if side == 'red' else 'red'), 'no_moves', moves
        # 把裁判局面同步到该侧引擎（保留引擎自己的开关）。
        # 真实 UCI 每步 position 都 reset_engine()，故此处同步局面后清历史/缓存，
        # 模拟"新搜索"而非让 position_history 跨步累积导致重复和棋误判。
        eng.board = [row[:] for row in arb.board]
        eng.current_player = side
        eng.move_history = []
        eng.position_history = []
        eng.check_history = []
        eng.stop_requested = False
        if getattr(eng, 'clear_tt_on_new_game', False):
            eng.transposition_table.clear()
            eng.killer_moves = [[None, None] for _ in range(eng.max_ply)]
            eng.history_table = {}
        mv = eng.iterative_deepening_search()
        if mv is None or mv not in legal:
            return ('black' if side == 'red' else 'red'), f'illegal({mv})', moves
        arb.make_move(*mv)
        moves.append(move_to_iccs(mv))
        # 同步引擎走子历史，供 TT/key 一致性
        eng.move_history.append((mv[0], mv[1], mv[2], mv[3], '.'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--games', type=int, default=40)
    ap.add_argument('--movetime', type=int, default=200)
    ap.add_argument('--max-plies', type=int, default=160)
    ap.add_argument('--opening-plies', type=int, default=8,
                    help='每局开局随机步数（0=纯确定性，建议>=6保证局面多样）')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--out', default='data/ab_search.json')
    args = ap.parse_args()

    new_w = old_w = draws = 0
    results = []
    t0 = time.time()
    for i in range(args.games):
        # 偶数局 NEW 执红，奇数局 OLD 执红
        new_red = (i % 2 == 0)
        engines = ({'red': make_engine(True), 'black': make_engine(False)} if new_red
                   else {'red': make_engine(False), 'black': make_engine(True)})
        # seed 用局号派生但同局 NEW/OLD 共享（两种先手各用不同开局，整体更均衡）
        seed = args.seed + i * 101
        winner, reason, moves = play_one(engines, args.movetime, args.max_plies,
                                         seed=seed, opening_plies=args.opening_plies)
        new_side = 'red' if new_red else 'black'
        if winner == 'draw':
            outcome = 'draw'
            draws += 1
        elif winner == new_side:
            outcome = 'NEW'
            new_w += 1
        else:
            outcome = 'OLD'
            old_w += 1
        print(f'第{i+1:2d}局 NEW执{"红" if new_red else "黑"}: {outcome} ({reason}, {len(moves)}步)', flush=True)
        results.append({'game': i + 1, 'new_red': new_red, 'outcome': outcome,
                        'reason': reason, 'plies': len(moves)})

    n = len(results)
    pts = new_w + 0.5 * draws
    print(f'\nA/B结果({n}局): NEW {new_w} 胜 / {draws} 和 / OLD {old_w} 胜')
    print(f'NEW得分率: {pts / n * 100:.1f}%  用时 {time.time() - t0:.0f}s')
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump({'config': vars(args), 'switches': SWITCHES,
                   'score': {'NEW': new_w, 'OLD': old_w, 'draw': draws},
                   'games': results}, f, ensure_ascii=False, indent=2)
    print('明细:', args.out)


if __name__ == '__main__':
    main()
