#!/usr/bin/env python3
"""
UCI (Universal Chess Interface) Protocol Implementation
For Chinese Chess Engine

着法格式：ICCS（如 a0a1、b0c2），与皮卡鱼(Pikafish)等主流象棋 UCI 引擎一致；
输入同时兼容旧的纯数字格式（如 "0102" = (0,1)->(0,2)）。

坐标约定（与 endgame_book / pro_opening_book 相同）：
  文件 file = a+i 对应 col 0..8；行 rank = 0..9 对应 row 0..9。
  a0 = 红方左下角（引擎 board[0][0]）。

支持命令：
  uci / isready / ucinewgame / setoption(忽略) /
  position [startpos | fen <FEN>] [moves <m1> <m2> ...] /
  go [movetime MS | depth N | wtime W btime B [winc I binc I] | infinite] /
  stop / quit / debug on|off

go 在后台线程执行；搜索完成（或收到 stop）后输出 bestmove。
输出经协议通道输出，引擎内部的诊断 print 被屏蔽，不污染协议流。

Usage:
    python uci_interface.py

The GUI will send commands via stdin and receive responses via stdout.
"""

import os
import re
import sys
import threading
import contextlib
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mini_chess import ChineseChess

# ICCS 着法: 文件(a-i) + 行(0-9) x 2
_ICCS_RE = re.compile(r'^[a-i][0-9][a-i][0-9]$')
# 旧纯数字格式: 行列各 1 位数字 x 4
_LEGACY_RE = re.compile(r'^[0-9]{4}$')


@contextlib.contextmanager
def _quiet_stdout():
    """把引擎的诊断 print 重定向到空洞（协议输出走 _out，不经过 sys.stdout）。"""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


class UCIInterface:
    """UCI Protocol handler for Chinese Chess Engine"""

    def __init__(self):
        self.engine = None
        self.debug = False
        self._real_stdout = sys.stdout  # 协议通道（不受 redirect_stdout 影响）
        self._search_thread = None
        self.use_book = True  # setoption 设置，reset_engine 时必须保留
        self.reset_engine()

    # ---------- 协议输出 ----------
    def _out(self, line):
        self._real_stdout.write(line + '\n')
        self._real_stdout.flush()

    def reset_engine(self):
        """Create new engine instance（先停掉在跑的搜索）"""
        self._stop_search()
        with _quiet_stdout():
            self.engine = ChineseChess()
            self.engine.init_board()
            # 保留 setoption 的设置（GUI 标准顺序：setoption -> position）
            self.engine.use_pro_book = self.use_book
            self.engine.use_opening_book = self.use_book
            self.engine.use_endgame_book = self.use_book

    # ---------- 着法格式 ----------
    def move_to_uci(self, move):
        """内部 (row, col, row, col) -> ICCS "a0a1"（与 Pikafish 一致）"""
        if not move:
            return '0000'
        sr, sc, er, ec = move
        return f"{chr(ord('a') + sc)}{sr}{chr(ord('a') + ec)}{er}"

    def uci_to_move(self, uci_move):
        """ICCS "a0a1" 或旧数字 "0102" -> 内部 (row, col, row, col)；非法返回 None"""
        s = (uci_move or '').strip().lower()
        if _ICCS_RE.match(s):
            return (int(s[1]), ord(s[0]) - ord('a'),
                    int(s[3]), ord(s[2]) - ord('a'))
        if _LEGACY_RE.match(s):
            return (int(s[0]), int(s[1]), int(s[2]), int(s[3]))
        return None

    # ---------- FEN ----------
    def _load_fen(self, fen):
        """解析中国象棋 FEN（board_to_fen 的逆操作）。成功返回 True。"""
        parts = fen.split()
        if not parts:
            return False
        ranks = parts[0].split('/')
        if len(ranks) != 10:
            return False
        board = [['.' for _ in range(9)] for _ in range(10)]
        for i, rank_str in enumerate(ranks):
            row = 9 - i  # FEN 第一段 = 黑方底线 = 引擎 row 9
            col = 0
            for ch in rank_str:
                if ch.isdigit():
                    col += int(ch)
                else:
                    if col > 8:
                        return False
                    # FEN 用 N/n 表示马，引擎用 H/h
                    board[row][col] = 'H' if ch == 'N' else ('h' if ch == 'n' else ch)
                    col += 1
            if col != 9:
                return False
        self.engine.board = board
        if len(parts) > 1:
            self.engine.current_player = 'red' if parts[1] in ('w', 'r') else 'black'
        return True

    # ---------- 命令处理 ----------
    def handle_uci(self):
        self._out('id name Chinese Chess Engine v2.1')
        self._out('id author AI Assistant')
        self._out('option name UseBook type check default true')
        self._out('uciok')

    def handle_isready(self):
        self._out('readyok')

    def handle_ucinewgame(self):
        self.reset_engine()

    def handle_setoption(self, tokens):
        """setoption name <Name> value <Value>；支持 UseBook，其余忽略。"""
        try:
            if 'name' not in tokens:
                return
            ni = tokens.index('name') + 1
            vi = tokens.index('value') if 'value' in tokens else len(tokens)
            name = ' '.join(tokens[ni:vi]).strip().lower()
            value = ' '.join(tokens[vi + 1:]).strip().lower() if vi < len(tokens) else ''
            if name == 'usebook':
                self.use_book = value in ('true', '1', 'yes', 'on')
                self.engine.use_pro_book = self.use_book
                self.engine.use_opening_book = self.use_book
                self.engine.use_endgame_book = self.use_book
        except Exception as e:
            if self.debug:
                self._out(f'# Error in setoption: {e}')

    def handle_position(self, tokens):
        """position [startpos | fen <FEN>] [moves <m1> ...]"""
        try:
            if 'startpos' in tokens:
                self.reset_engine()
            elif 'fen' in tokens:
                fi = tokens.index('fen')
                # FEN 由空格分隔的多段组成，直到遇到 'moves' 或结尾
                fen_parts = []
                i = fi + 1
                while i < len(tokens) and tokens[i] != 'moves':
                    fen_parts.append(tokens[i])
                    i += 1
                self.reset_engine()
                if not self._load_fen(' '.join(fen_parts)):
                    if self.debug:
                        self._out('# bad fen')
                    return
            else:
                return

            if 'moves' in tokens:
                for uci_move in tokens[tokens.index('moves') + 1:]:
                    move = self.uci_to_move(uci_move)
                    if move is None:
                        if self.debug:
                            self._out(f'# invalid move format: {uci_move}')
                        continue
                    legal = self.engine.get_all_legal_moves()
                    if move in legal:
                        self.engine.make_move(*move)
                    elif self.debug:
                        self._out(f'# illegal move: {uci_move}')

        except Exception as e:
            if self.debug:
                self._out(f'# Error in position: {e}')

    def handle_go(self, tokens):
        """go 参数解析 + 后台线程执行搜索。"""
        # 若上一个搜索还在跑，先停掉（UCI 规范下 GUI 应先发 stop，这里防御处理）
        self._stop_search()

        movetime = depth = None
        wtime = btime = winc = binc = None
        infinite = False

        i = 1
        while i < len(tokens):
            t = tokens[i]
            if t == 'movetime' and i + 1 < len(tokens):
                movetime = int(tokens[i + 1]) / 1000.0
                i += 2
            elif t == 'depth' and i + 1 < len(tokens):
                depth = int(tokens[i + 1])
                i += 2
            elif t == 'wtime' and i + 1 < len(tokens):
                wtime = int(tokens[i + 1]) / 1000.0
                i += 2
            elif t == 'btime' and i + 1 < len(tokens):
                btime = int(tokens[i + 1]) / 1000.0
                i += 2
            elif t == 'winc' and i + 1 < len(tokens):
                winc = int(tokens[i + 1]) / 1000.0
                i += 2
            elif t == 'binc' and i + 1 < len(tokens):
                binc = int(tokens[i + 1]) / 1000.0
                i += 2
            elif t == 'infinite':
                infinite = True
                i += 1
            else:
                i += 1

        if movetime:
            self.engine.thinking_time = movetime
        elif wtime is not None and btime is not None:
            remaining = wtime if self.engine.current_player == 'red' else btime
            inc = (winc or 0.0) if self.engine.current_player == 'red' else (binc or 0.0)
            allocated = (remaining / 40.0) + inc * 0.5
            self.engine.thinking_time = max(0.2, min(allocated, 30.0))
        elif infinite:
            self.engine.thinking_time = 3600.0
        # 否则沿用引擎默认 thinking_time

        if depth:
            self.engine.search_depth = depth

        # 发起新搜索前清除 stop 标志（引擎内部不重置，避免与 stop 竞争）
        self.engine.stop_requested = False
        self._search_thread = threading.Thread(target=self._search_worker, daemon=True)
        self._search_thread.start()

    def _search_worker(self):
        """后台搜索线程：完成后输出 bestmove。"""
        best_move = None
        try:
            with _quiet_stdout():
                best_move = self.engine.iterative_deepening_search()
        except Exception as e:
            if self.debug:
                self._out(f'# Error in search: {e}')
            best_move = None
        self._out(f'bestmove {self.move_to_uci(best_move)}')

    def handle_stop(self):
        """stop：中断当前搜索并（由工作线程）输出 bestmove。"""
        self.engine.stop_requested = True
        self._stop_search()

    def _stop_search(self):
        """等待搜索线程结束（bestmove 由工作线程输出）。"""
        t = self._search_thread
        if t is not None and t.is_alive():
            t.join(timeout=10)
        self._search_thread = None

    def handle_quit(self):
        self.handle_stop()
        raise SystemExit(0)

    def main_loop(self):
        while True:
            try:
                line = input().strip()
            except EOFError:
                break
            except KeyboardInterrupt:
                break

            if not line:
                continue

            tokens = line.split()
            cmd = tokens[0].lower()

            try:
                if cmd == 'uci':
                    self.handle_uci()
                elif cmd == 'isready':
                    self.handle_isready()
                elif cmd == 'ucinewgame':
                    self.handle_ucinewgame()
                elif cmd == 'setoption':
                    self.handle_setoption(tokens)
                elif cmd == 'position':
                    self.handle_position(tokens)
                elif cmd == 'go':
                    self.handle_go(tokens)
                elif cmd == 'stop':
                    self.handle_stop()
                elif cmd == 'quit':
                    self.handle_quit()
                elif cmd == 'debug':
                    if len(tokens) > 1:
                        self.debug = (tokens[1].lower() == 'on')
                # ponder/ponderhit/register 等一律忽略
            except SystemExit:
                break
            except Exception as e:
                if self.debug:
                    self._out(f'# Error in main loop: {e}')


def main():
    uci = UCIInterface()
    uci.main_loop()


if __name__ == '__main__':
    main()
