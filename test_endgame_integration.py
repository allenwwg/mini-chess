#!/usr/bin/env python3
"""残局库接入测试"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except (ValueError, OSError):
        pass

from endgame_book import EndgameBook, board_to_fen
from mini_chess import ChineseChess

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'egtb_cache.json')


def run(name, fn):
    try:
        fn()
        print(f'[PASS] {name}')
        return True
    except Exception as exc:
        print(f'[FAIL] {name}: {exc}')
        import traceback
        traceback.print_exc()
        return False


def setup_rook_endgame(g):
    """黑将 d8 + 红车 e2 + 红帅 e0, 红先"""
    g.board = [['.' for _ in range(9)] for _ in range(10)]
    g.board[9][3] = 'k'
    g.board[2][4] = 'R'
    g.board[0][4] = 'K'
    g.current_player = 'red'


def test_fen_conversion():
    g = ChineseChess()
    fen = board_to_fen(g.board, 'red')
    assert fen.startswith('rnbakabnr/'), fen  # 引擎 H/h 马 -> FEN N/n
    assert fen.endswith(' w'), fen
    g.current_player = 'black'
    assert board_to_fen(g.board, 'black').endswith(' b')


def test_fen_reversed_rows():
    """黑方底线在最前: 初始局面 FEN 首段应含小写 (黑方), 末段含大写 (红方)"""
    g = ChineseChess()
    parts = board_to_fen(g.board, 'red').split()[0].split('/')
    assert 'k' in parts[0] and 'K' not in parts[0], parts[0]
    assert 'K' in parts[-1] and 'k' not in parts[-1], parts[-1]


def test_local_backend():
    """本地 Felicity 后端 (离线): 用独立缓存确保走本地而非旧缓存"""
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'data', 'egtb_cache_local_test.json')
    if os.path.exists(cache):
        os.remove(cache)
    eb = EndgameBook(cache_path=cache, timeout=2)
    if not eb.local_ok:
        print('  [SKIP] 本地探测程序未编译 (运行 build_egtb.bat)')
        return
    g = ChineseChess()
    setup_rook_endgame(g)
    uci, src = eb._query(board_to_fen(g.board, 'red'))
    assert src == 'local', f'expected local, got {src}'
    assert uci == 'e2d2', uci
    assert eb.uci_to_engine(uci) in g.get_all_legal_moves()
    print(f'  local move={uci} source={src}')


def test_cdb_query():
    """残局库查询车杀将残局 (本地 Felicity 优先, 返回最优杀着 e2d2)"""
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'data', 'egtb_cache_query_test.json')
    if os.path.exists(cache):
        os.remove(cache)
    eb = EndgameBook(cache_path=cache, timeout=3)
    g = ChineseChess()
    setup_rook_endgame(g)
    fen = board_to_fen(g.board, g.current_player)
    uci, src = eb._query(fen)
    assert uci in ('e2d2', 'e2e8'), (uci, src)  # 本地 e2d2 / 云库 e2e8 均为杀着
    print(f'  egtb move={uci} source={src}')


def test_probe_legal():
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'data', 'egtb_cache_probe_test.json')
    if os.path.exists(cache):
        os.remove(cache)
    eb = EndgameBook(cache_path=cache, timeout=3)
    g = ChineseChess()
    setup_rook_endgame(g)
    move, src = eb.probe(g.board, 'red', g.get_all_legal_moves())
    assert move in ((2, 4, 2, 3), (2, 4, 8, 4)), (move, src)
    assert move in g.get_all_legal_moves()


def test_engine_uses_egtb():
    """引擎在残局阶段应返回残局库走法 (禁用开局库避免空历史命中开局)"""
    g = ChineseChess()
    g.use_pro_book = False
    g.use_opening_book = False
    setup_rook_endgame(g)
    assert g.count_material() <= g.egtb_piece_limit
    move = g.iterative_deepening_search()
    assert move in ((2, 4, 2, 3), (2, 4, 8, 4)), move


def test_material_threshold():
    g = ChineseChess()  # 初始满子, 远超阈值
    assert g.count_material() > g.egtb_piece_limit
    setup_rook_endgame(g)
    assert g.count_material() == 1  # 仅车 (将帅不计)


def test_cache_persistence():
    eb = EndgameBook(cache_path=CACHE)
    g = ChineseChess()
    setup_rook_endgame(g)
    fen = board_to_fen(g.board, 'red')
    eb._query(fen)
    eb.save_cache()
    assert fen in eb.cache
    eb2 = EndgameBook(cache_path=CACHE)
    assert fen in eb2.cache
    print(f'  cache entries: {len(eb2.cache)}')


def test_disabled_probe():
    eb = EndgameBook(enabled=False)
    g = ChineseChess()
    setup_rook_endgame(g)
    assert eb.probe(g.board, 'red') == (None, None)


if __name__ == '__main__':
    tests = [
        ('FEN conversion', test_fen_conversion),
        ('FEN reversed rows', test_fen_reversed_rows),
        ('local Felicity backend', test_local_backend),
        ('CDB real query', test_cdb_query),
        ('probe returns legal move', test_probe_legal),
        ('engine uses EGTB', test_engine_uses_egtb),
        ('material threshold', test_material_threshold),
        ('cache persistence', test_cache_persistence),
        ('disabled probe', test_disabled_probe),
    ]
    results = [(n, run(n, fn)) for n, fn in tests]
    passed = sum(ok for _, ok in results)
    print(f'\nTotal: {passed}/{len(results)} passed')
    sys.exit(0 if passed == len(results) else 1)
