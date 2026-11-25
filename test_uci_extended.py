#!/usr/bin/env python3
"""
UCI 接口扩展测试：覆盖协议格式与 go/stop 中断。

用法: python test_uci_extended.py
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from uci_interface import UCIInterface  # noqa: E402


class UciProc:
    """UCI 子进程封装"""

    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, 'uci_interface.py'], cwd=HERE,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def send(self, cmd):
        self.proc.stdin.write(cmd + '\n')
        self.proc.stdin.flush()

    def read_until(self, kw, timeout=30):
        lines = []
        end = time.time() + timeout
        while time.time() < end:
            line = self.proc.stdout.readline().strip()
            if line:
                lines.append(line)
                if kw in line:
                    return lines
        raise TimeoutError(f'wait {kw!r} timeout; got {lines}')

    def quit(self):
        try:
            self.send('quit')
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


def test_move_conversion():
    """ICCS 与内部坐标往返 + 旧数字格式兼容"""
    u = UCIInterface()
    cases = [
        ((0, 0, 1, 0), 'a0a1'),
        ((3, 2, 6, 2), 'c3c6'),
        ((9, 8, 7, 8), 'i9i7'),
    ]
    for internal, iccs in cases:
        assert u.move_to_uci(internal) == iccs, (internal, iccs)
        assert u.uci_to_move(iccs) == internal, (iccs, internal)
    # 旧格式 "0102" = (0,1)->(0,2)
    assert u.uci_to_move('0102') == (0, 1, 0, 2)
    assert u.uci_to_move('zz99') is None
    print('PASS move conversion (ICCS roundtrip + legacy)')
    return True


def test_fen_loading():
    """FEN 设局面：马 N/n -> H/h，行反转，走子方正确"""
    u = UCIInterface()
    fen = 'rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w'
    assert u._load_fen(fen) is True
    assert u.engine.board[0][0] == 'R'  # 红车在 row0
    assert u.engine.board[0][1] == 'H'  # FEN N -> 引擎 H
    assert u.engine.board[9][1] == 'h'  # FEN n -> 引擎 h
    assert u.engine.current_player == 'red'

    fen2 = '4k4/9/9/9/9/9/9/9/9/4K4 b'
    assert u._load_fen(fen2) is True
    assert u.engine.board[0][4] == 'K'
    assert u.engine.board[9][4] == 'k'
    assert u.engine.current_player == 'black'
    assert u._load_fen('bad fen') is False
    print('PASS FEN loading (row flip, N->H, side to move)')
    return True


def test_illegal_moves_skipped():
    """position 命令中的非法着法被忽略，不破坏棋盘"""
    p = UciProc()
    try:
        p.send('uci')
        p.read_until('uciok', 5)
        # a0a1 非法（车被马挡），之后跟合法着法 b0c2（马）
        p.send('position startpos moves a0a1 b0c2')
        p.send('go depth 1')
        lines = p.read_until('bestmove', 20)
        best = [l for l in lines if l.startswith('bestmove')][0].split()[1]
        assert len(best) == 4 and 'a' <= best[0] <= 'i', best
        print('PASS illegal moves skipped')
        return True
    finally:
        p.quit()


def test_stop_interrupt():
    """go infinite + stop 能在超时前返回 bestmove"""
    p = UciProc()
    try:
        p.send('uci')
        p.read_until('uciok', 5)
        p.send('setoption name UseBook value false')  # 关开局库，走真搜索
        p.send('position startpos')
        # depth 50 远超引擎自然完成能力（默认上限 6），确保 stop 前搜索仍在跑
        p.send('go depth 50')
        time.sleep(0.5)
        t0 = time.time()
        p.send('stop')
        lines = p.read_until('bestmove', timeout=10)
        dt = time.time() - t0
        best = [l for l in lines if l.startswith('bestmove')][0]
        assert best.split()[1] != '0000', best
        assert dt < 8, f'stop too slow: {dt:.1f}s'
        print(f'PASS stop interrupt ({dt:.2f}s)')
        return True
    finally:
        p.quit()


def test_position_then_search_iccs():
    """position moves 后的局面正确（ICCS 着法被应用）"""
    p = UciProc()
    try:
        p.send('uci')
        p.read_until('uciok', 5)
        p.send('position startpos moves b0c2')  # 红马 b0->c2
        p.send('go movetime 200')
        lines = p.read_until('bestmove', 20)
        best = [l for l in lines if l.startswith('bestmove')][0].split()[1]
        assert len(best) == 4 and best[0].isalpha(), best
        print('PASS position+search with ICCS moves')
        return True
    finally:
        p.quit()


def main():
    tests = [
        test_move_conversion,
        test_fen_loading,
        test_illegal_moves_skipped,
        test_stop_interrupt,
        test_position_then_search_iccs,
    ]
    failed = 0
    for t in tests:
        try:
            if not t():
                failed += 1
        except Exception as e:
            print(f'FAIL {t.__name__}: {e}')
            failed += 1
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
