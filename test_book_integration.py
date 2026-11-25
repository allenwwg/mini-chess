#!/usr/bin/env python3
"""职业开局库接入测试（不依赖 Flask/服务器）"""
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except (ValueError, OSError):
        pass

from pro_opening_book import ProOpeningBook
from mini_chess import ChineseChess


def run(name, fn):
    try:
        fn()
        print(f"[PASS] {name}")
        return True
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        import traceback
        traceback.print_exc()
        return False


def test_stats():
    s = ProOpeningBook().get_stats()
    assert s['loaded'], 'book not loaded'
    assert s['positions'] >= 51000, s
    assert s['max_ply'] >= 20, s
    print(f"  positions={s['positions']} variations={s['variations']} max_ply={s['max_ply']}")


def test_coord_roundtrip():
    b = ProOpeningBook()
    for m in [(2, 1, 2, 4), (0, 1, 2, 2), (9, 7, 7, 6), (3, 2, 4, 2)]:
        assert b.uci_to_engine(b.engine_to_uci(m)) == m, (m, b.engine_to_uci(m))
    assert b.engine_to_uci((2, 1, 2, 4)) == 'b2e2'


def test_start_candidates():
    c = ProOpeningBook().get_candidates([])
    ucis = {x[1] for x in c}
    assert {'b2e2', 'h2e2', 'c3c4', 'g3g4'} <= ucis, ucis
    assert c[0][2] >= 1400, c[0]


def test_history_5tuple():
    """引擎 move_history 是 (sr,sc,er,ec,captured) 5 元组"""
    b = ProOpeningBook()
    hist = [(2, 7, 2, 4, '.')]
    c = b.get_candidates(hist)
    assert c, '5-tuple history did not match book'
    assert any(x[1] in ('h9g7', 'g6g5', 'b7c7', 'c9e7') for x in c), c[:6]
    print('  black replies:', [x[1] for x in c[:5]])


def test_engine_first_move():
    g = ChineseChess()
    assert g.use_pro_book and g.pro_book.loaded
    m = g.iterative_deepening_search()
    assert m in g.get_all_legal_moves(), f'illegal book move {m}'
    uci = g.pro_book.engine_to_uci(m)
    ucis = {x[1] for x in g.pro_book.get_candidates([])}
    assert uci in ucis, f'{uci} not in book'
    print('  first move:', uci)


def test_engine_opening_line():
    g = ChineseChess()
    line = []
    for i in range(10):
        legal = g.get_all_legal_moves()
        m = g.iterative_deepening_search()
        assert m in legal, f'ply {i}: illegal {m}'
        line.append(g.pro_book.engine_to_uci(m))
        g.make_move(*m, track_check=False)
    print('  line:', ' '.join(line))
    assert len(line) == 10


def test_randomness():
    b = ProOpeningBook()
    picks = {b.pick_book_move([])[0] for _ in range(80)}
    assert len(picks) >= 4, picks
    print('  distinct first moves:', len(picks))


def test_book_disabled_fallback():
    """关闭职业库后仍可用手写库走子"""
    g = ChineseChess()
    g.use_pro_book = False
    m = g.iterative_deepening_search()
    assert m in g.get_all_legal_moves()


if __name__ == '__main__':
    tests = [
        ('stats', test_stats),
        ('coord roundtrip', test_coord_roundtrip),
        ('start candidates', test_start_candidates),
        ('5-tuple history', test_history_5tuple),
        ('engine first move', test_engine_first_move),
        ('engine 10-ply line', test_engine_opening_line),
        ('weighted randomness', test_randomness),
        ('fallback when disabled', test_book_disabled_fallback),
    ]
    results = [(n, run(n, fn)) for n, fn in tests]
    passed = sum(ok for _, ok in results)
    print(f"\nTotal: {passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)
