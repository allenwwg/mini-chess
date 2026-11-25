#!/usr/bin/env python3
"""
mini_chess(UCI) vs Pikafish 对弈驱动

用两个 UCI 引擎子进程下棋，本脚本做裁判（合法性/终局判定）并记分。
双方着法均走 ICCS 格式（a0a1），与皮卡鱼一致。

用法:
    # 对 Pikafish（先下载 pikafish.exe，权重放在同目录）
    python tools/match_vs_pikafish.py --engine2 "d:/pikafish/pikafish.exe" --games 10

    # 自测（引擎对引擎，验证驱动本身工作）
    python tools/match_vs_pikafish.py --self --games 2 --movetime 300

    # 指定思考时间/线程
    python tools/match_vs_pikafish.py --engine2 "d:/pikafish/pikafish.exe" \
        --movetime 1000 --threads 2 --games 20 --out data/match_results.json

结果: 逐局输出 + 总比分（--out 可保存 JSON 明细）。
"""

import argparse
import json
import os
import queue
import shlex
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import mini_chess as mc  # noqa: E402


def make_arbiter():
    """裁判只需走法生成/终局判定，禁用书与残局库避免启动子进程/联网。"""
    mc.OPENING_BOOK_AVAILABLE = False
    mc.PRO_BOOK_AVAILABLE = False
    mc.EGTB_AVAILABLE = False
    g = mc.ChineseChess()
    return g


def iccs_to_move(ics):
    """ICCS "b0c2" -> 内部 (row, col, row, col)"""
    s = ics.strip().lower()
    if len(s) != 4 or not s[0].isalpha():
        return None
    try:
        return (int(s[1]), ord(s[0]) - ord('a'),
                int(s[3]), ord(s[2]) - ord('a'))
    except (ValueError, IndexError):
        return None


class UciEngine:
    """UCI 引擎子进程封装（行读取走独立线程 + 队列，支持超时）"""

    def __init__(self, name, cmd, cwd=None, err_path=None, options=None):
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.options = options or []  # 启动时下发的 setoption
        self.lines = queue.Queue()
        self.err_path = err_path
        self._start()

    def _start(self):
        stderr = open(self.err_path, 'a', encoding='utf-8', errors='replace') \
            if self.err_path else subprocess.DEVNULL
        self.proc = subprocess.Popen(
            self.cmd, cwd=self.cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=stderr, text=True, bufsize=1,
        )
        # 每个 pump 线程绑定各自的 proc/queue：restart 后旧线程即使未退出，
        # 也只写旧 queue，不会把旧进程的残留行串进新会话。
        threading.Thread(target=self._pump, args=(self.proc, self.lines), daemon=True).start()
        self.send('uci')
        self.read_until('uciok', timeout=30)
        for name, value in self.options:
            self.setoption(name, value)
        self.send('isready')
        self.read_until('readyok', timeout=30)

    def restart(self):
        """崩溃/超时后重启引擎，保证长批次对弈不中断。"""
        try:
            self.proc.kill()
            self.proc.wait(timeout=3)
        except Exception:
            pass
        self.lines = queue.Queue()
        self._start()

    @staticmethod
    def _pump(proc, q):
        try:
            for line in proc.stdout:
                q.put(line.rstrip('\n'))
        except Exception:
            pass

    def send(self, cmd):
        self.proc.stdin.write(cmd + '\n')
        self.proc.stdin.flush()

    def read_until(self, keyword, timeout=60):
        """读到含 keyword 的行为止，返回该行；超时抛 TimeoutError。"""
        deadline = time.time() + timeout
        while True:
            remain = deadline - time.time()
            if remain <= 0:
                raise TimeoutError(f'{self.name}: 等待 {keyword!r} 超时')
            try:
                line = self.lines.get(timeout=remain)
            except queue.Empty:
                raise TimeoutError(f'{self.name}: 等待 {keyword!r} 超时')
            if keyword in line:
                return line

    def new_game(self):
        self.send('ucinewgame')
        self.send('isready')
        self.read_until('readyok', timeout=30)

    def setoption(self, name, value):
        self.send(f'setoption name {name} value {value}')

    def think(self, moves, movetime_ms=None, wtime_ms=None, btime_ms=None):
        """发送局面并取 bestmove（ICCS 字符串）。"""
        pos = 'position startpos'
        if moves:
            pos += ' moves ' + ' '.join(moves)
        self.send(pos)
        if movetime_ms:
            self.send(f'go movetime {int(movetime_ms)}')
        else:
            self.send(f'go wtime {int(wtime_ms)} btime {int(btime_ms)}')
        # 超时阈值随 movetime 自适应：正常一步应在 movetime+少量开销内返回。
        # 下限 10s（容忍偶发调度卡顿），上限 30s；过长会把单次卡顿拖成整局 60s+。
        budget = (movetime_ms or 10000) / 1000
        timeout = min(30, max(10, budget * 3 + 5))
        line = self.read_until('bestmove', timeout=timeout)
        parts = line.split()
        return parts[1] if len(parts) > 1 else '0000'

    def quit(self):
        try:
            self.send('quit')
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


# 非棋力结果：这类局不代表真实强弱，必须重赛而非计分
ABNORMAL_PREFIXES = ('timeout', 'engine_crash', 'illegal')


def is_abnormal(reason):
    """是否是需要重赛的异常局（对手/本方进程卡顿、崩溃或非法着法）。"""
    return any(reason.startswith(p) for p in ABNORMAL_PREFIXES)


def adjudicate_ply_limit(g):
    """超过回合上限时按子力裁定。"""
    red = black = 0
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


def play_game(engines, movetime_ms, max_plies):
    """一局棋。engines = {'red': UciEngine, 'black': UciEngine}。
    返回 (winner, reason, moves)。"""
    g = make_arbiter()
    moves = []
    while True:
        w = g.winner
        if w is not None:
            reason = 'checkmate' if g.is_checkmate('red') or g.is_checkmate('black') else \
                     'long_check' if g.get_long_check_loser() else 'draw_rule'
            return w, reason, moves

        if len(moves) >= max_plies:
            return adjudicate_ply_limit(g), 'ply_limit', moves

        side = g.current_player
        eng = engines[side]
        try:
            mv = eng.think(moves, movetime_ms=movetime_ms)
        except TimeoutError:
            return ('black' if side == 'red' else 'red'), 'timeout', moves
        except OSError as exc:
            # 引擎进程崩溃（stdin/stdout 失效），判引擎方负，下一局由 restart 恢复
            return ('black' if side == 'red' else 'red'), f'engine_crash({exc})', moves

        internal = iccs_to_move(mv)
        legal = g.get_all_legal_moves()
        if internal is None or internal not in legal:
            return ('black' if side == 'red' else 'red'), f'illegal({mv})', moves

        g.make_move(*internal)
        moves.append(mv)


def main():
    ap = argparse.ArgumentParser(description='mini_chess vs Pikafish 对弈驱动')
    ap.add_argument('--engine1', default=None,
                    help='本方引擎命令 (默认 python uci_interface.py)')
    ap.add_argument('--engine2', default=None,
                    help='对手引擎命令，如 "d:/pikafish/pikafish.exe"')
    ap.add_argument('--self', dest='self_play', action='store_true',
                    help='自测模式：两侧都用本方引擎')
    ap.add_argument('--games', type=int, default=10, help='总局数（自动分先）')
    ap.add_argument('--movetime', type=int, default=1000, help='每步思考毫秒')
    ap.add_argument('--threads', type=int, default=1, help='对手引擎线程数')
    ap.add_argument('--hash', type=int, default=64, help='对手引擎 Hash(MB)')
    ap.add_argument('--max-plies', type=int, default=300, help='单局最大半回合数')
    ap.add_argument('--max-retries', type=int, default=3,
                    help='异常局（timeout/崩溃/非法着法）最多重赛次数，超过则作废不计分')
    ap.add_argument('--out', default=None, help='结果 JSON 输出路径')
    args = ap.parse_args()

    if args.engine1:
        e1_cmd = shlex.split(args.engine1, posix=(os.name != 'nt'))
    else:
        e1_cmd = [sys.executable, os.path.join(ROOT, 'uci_interface.py')]
    if args.self_play:
        e2_cmd = e1_cmd
    else:
        if not args.engine2:
            ap.error('需要 --engine2 或 --self')
        e2_cmd = shlex.split(args.engine2, posix=(os.name != 'nt'))

    print(f'本方: {" ".join(e1_cmd)}')
    print(f'对手: {" ".join(e2_cmd)}')
    print(f'{args.games} 局 | 每步 {args.movetime}ms | 上限 {args.max_plies} 半回合\n')

    err_dir = os.path.join(ROOT, 'data')
    e1_opts = []
    e2_opts = [] if args.self_play else [('Threads', args.threads), ('Hash', args.hash)]
    e1 = UciEngine('mini_chess', e1_cmd, cwd=ROOT,
                   err_path=os.path.join(err_dir, 'mini_chess_stderr.log'),
                   options=e1_opts)
    e2 = UciEngine('pikafish' if not args.self_play else 'mini_chess(B)', e2_cmd, cwd=ROOT,
                   err_path=os.path.join(err_dir, 'pikafish_stderr.log'),
                   options=e2_opts)

    results = []
    voided = []  # 重赛耗尽仍异常的局，不计入战绩
    score = {'mini_chess': 0, 'pikafish': 0, 'draw': 0}
    games_played = 0  # 有效局计数，用于分配先手（作废局不占先手顺序）
    try:
        for i in range(args.games):
            # 每局交换先手：偶数局 e1 执红（按有效局计，作废局不推进先手）
            e1_red = (games_played % 2 == 0)
            engines = {'red': e1, 'black': e2} if e1_red else {'red': e2, 'black': e1}

            winner = reason = None
            moves = []
            dt = 0.0
            for attempt in range(args.max_retries + 1):
                # 每次尝试都重启引擎：异常局多半伴随进程卡顿/状态污染，必须干净重来。
                # 首个尝试的首局用构造时已启动的进程；其余一律重启。
                if not (i == 0 and attempt == 0):
                    e1.restart()
                    e2.restart()
                e1.new_game()
                e2.new_game()
                t0 = time.time()
                winner, reason, moves = play_game(engines, args.movetime, args.max_plies)
                dt = time.time() - t0
                if not is_abnormal(reason):
                    break
                tag = '红' if e1_red else '黑'
                if attempt < args.max_retries:
                    print(f'第{i + 1:2d}局 本方执{tag}: 异常({reason}, {len(moves)}步, {dt:.0f}s) '
                          f'→ 重赛 {attempt + 1}/{args.max_retries}')
                else:
                    print(f'第{i + 1:2d}局 本方执{tag}: 异常重赛{args.max_retries}次仍失败 '
                          f'({reason}) → 作废不计分')

            if is_abnormal(reason):
                voided.append({'game': i + 1, 'e1_color': 'red' if e1_red else 'black',
                               'reason': reason, 'retries': args.max_retries})
                continue  # 作废局不推进 games_played、不计入 results

            games_played += 1
            if winner == 'draw':
                outcome = 'draw'
                score['draw'] += 1
            elif (winner == 'red') == e1_red:
                outcome = 'mini_chess'
                score['mini_chess'] += 1
            else:
                outcome = 'pikafish' if not args.self_play else 'mini_chess(B)'
                score['pikafish'] += 1

            tag = '红' if e1_red else '黑'
            # outcome 在 self 模式下负局是 'mini_chess(B)'，统一按"胜/和/负"显示
            res_str = {'draw': '和', 'mini_chess': '胜'}.get(outcome, '负')
            print(f'第{i + 1:2d}局 本方执{tag}: {res_str}  ({reason}, {len(moves)}步, {dt:.0f}s)')
            results.append({
                'game': i + 1, 'e1_color': 'red' if e1_red else 'black',
                'winner': winner, 'outcome': outcome, 'reason': reason,
                'plies': len(moves), 'moves': moves, 'seconds': round(dt, 1),
            })
    finally:
        e1.quit()
        e2.quit()

    n = len(results)
    opp_name = 'mini_chess(B)' if args.self_play else 'pikafish'
    print(f"\n总比分({n}有效局, {len(voided)}作废局): 本方 {score['mini_chess']} 胜 / "
          f"{score['draw']} 和 / {opp_name} {score['pikafish']} 负")
    if n:
        pts = score['mini_chess'] + 0.5 * score['draw']
        print(f'本方得分率: {pts / n * 100:.1f}%')

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump({'config': vars(args), 'score': score, 'voided': voided, 'games': results},
                      f, ensure_ascii=False, indent=2)
        print(f'明细已保存: {args.out}')


if __name__ == '__main__':
    main()
