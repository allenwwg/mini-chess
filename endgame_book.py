"""
残局库适配器：本地 Felicity Egtb (离线) + 中国象棋云库 CDB (在线回退)

优先用本地编译的 Felicity 探测程序 (egtb_build/egtb_probe.exe + data/egtb/*.znb,
108 个单攻击方残局, DTM)，完全离线；本地不可用时回退 CDB 云库 querybest+endgame=1。
仅在子力简化到阈值以下时调用，带本地缓存，任何失败都优雅降级为 None。

坐标：UCI 与 Pikafish 一致 (a0 = 红方左下角)，与 pro_opening_book 相同。
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except (ValueError, OSError):
        pass

HOSTS = [
    'https://www.searqu.com/chessdb.php',
    'https://www.chessdb.cn/chessdb.php',
]

# 本地探测子进程模块级单例 (所有 EndgameBook 共享, 避免 new_game 时重复加载 5MB)
_LOCAL_PROC = None
_LOCAL_OK = None  # None=未尝试, True=可用, False=不可用


def board_to_fen(board, current_player):
    """把引擎 10x9 board 转成中国象棋 FEN。
    引擎 board[0] = 红方底线, 标准 FEN 第一段 = 黑方底线, 故需反转行序。
    引擎马用 H/h, 标准 FEN 用 N/n, 需转换。
    """
    rows = []
    for row in reversed(board):
        s = ''
        empty = 0
        for p in row:
            if p == '.':
                empty += 1
            else:
                if empty:
                    s += str(empty)
                    empty = 0
                s += 'N' if p == 'H' else ('n' if p == 'h' else p)
        if empty:
            s += str(empty)
        rows.append(s)
    return '/'.join(rows) + (' w' if current_player == 'red' else ' b')


class EndgameBook:
    def __init__(self, cache_path=None, timeout=2.0, enabled=True, use_local=True):
        self.timeout = timeout
        self.enabled = enabled
        self.use_local = use_local
        self.cache_path = cache_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'data', 'egtb_cache.json')
        self.cache = {}
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self._unsaved = 0
        self._load_cache()
        if self.use_local and self.enabled:
            self._start_local()

    def _load_cache(self):
        try:
            if os.path.exists(self.cache_path):
                with open(self.cache_path, encoding='utf-8') as f:
                    self.cache = json.load(f)
        except Exception:
            self.cache = {}

    def save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False)
            self._unsaved = 0
        except Exception:
            pass

    def _start_local(self):
        """启动模块级共享的本地 Felicity 探测子进程 (只启动一次)"""
        global _LOCAL_PROC, _LOCAL_OK
        if _LOCAL_PROC is not None or _LOCAL_OK is False:
            return
        base = os.path.dirname(os.path.abspath(__file__))
        exe = os.path.join(base, 'egtb_build', 'egtb_probe.exe')
        data = os.path.join(base, 'data', 'egtb')
        if not os.path.exists(exe) or not os.path.isdir(data):
            _LOCAL_OK = False
            return
        try:
            _LOCAL_PROC = subprocess.Popen(
                [exe, data], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1)
            _LOCAL_OK = True
            print('[egtb] 本地 Felicity 残局库已加载 (108 文件, 离线)')
        except Exception as exc:
            print(f'[egtb] 本地残局库启动失败: {exc}')
            _LOCAL_OK = False

    @property
    def local_ok(self):
        return _LOCAL_OK

    @staticmethod
    def _pos_to_engine(pos):
        """Felicity pos = row_fen*9+col, FEN 第一段=黑底线 => 引擎 row = 9-row_fen"""
        row_fen, col = divmod(pos, 9)
        return (9 - row_fen, col)

    @staticmethod
    def _engine_to_uci(move):
        sr, sc, er, ec = move
        return f"{chr(ord('a') + sc)}{sr}{chr(ord('a') + ec)}{er}"

    def _query_local(self, fen):
        """本地探测: 返回 UCI 字符串或 None"""
        global _LOCAL_OK
        proc = _LOCAL_PROC
        if proc is None or proc.poll() is not None:
            _LOCAL_OK = False
            return None
        try:
            proc.stdin.write(fen + '\n')
            proc.stdin.flush()
            line = proc.stdout.readline().strip()
            if not line or line == 'NONE':
                return None
            parts = line.split(',')
            if len(parts) != 2:
                print(f'[egtb] 本地探测返回异常: {line!r}')
                return None
            a, b = parts
            (sr, sc), (er, ec) = (self._pos_to_engine(int(a)),
                                  self._pos_to_engine(int(b)))
            return self._engine_to_uci((sr, sc, er, ec))
        except Exception as exc:
            print(f'[egtb] 本地探测失败, 回退云库: {type(exc).__name__}: {exc}')
            _LOCAL_OK = False
            return None

    @staticmethod
    def close():
        """关闭共享探测进程 (通常无需手动调用, 程序退出自动回收)"""
        global _LOCAL_PROC
        if _LOCAL_PROC:
            try:
                _LOCAL_PROC.stdin.close()
                _LOCAL_PROC.terminate()
            except Exception:
                pass
            _LOCAL_PROC = None

    @staticmethod
    def uci_to_engine(uci):
        return (int(uci[1]), ord(uci[0].lower()) - ord('a'),
                int(uci[3]), ord(uci[2].lower()) - ord('a'))

    def _query(self, fen, metric='dtm'):
        """返回 (uci_move, source) 或 (None, None)。本地优先, 云库回退。"""
        if fen in self.cache:
            cached = self.cache[fen]
            return (cached, 'cache') if cached else (None, None)

        # 1) 本地 Felicity (离线, 首选)
        if self.use_local and self.local_ok:
            uci = self._query_local(fen)
            if uci:
                self.cache[fen] = uci
                self._unsaved += 1
                if self._unsaved >= 5:
                    self.save_cache()
                return uci, 'local'

        # 2) CDB 云库回退
        params = urllib.parse.urlencode({
            'action': 'querybest', 'board': fen,
            'endgame': 1, 'egtbmetric': metric, 'learn': 0,
        })
        last_err = None
        for host in HOSTS:
            try:
                req = urllib.request.Request(host + '?' + params,
                                             headers={'User-Agent': 'Mozilla/5.0'})
                r = urllib.request.urlopen(req, timeout=self.timeout)
                text = r.read().decode('utf-8', 'replace').strip('\x00 \r\n\t')
                move = None
                for part in text.split('|'):
                    if part.startswith('egtb:'):
                        move = part[5:].strip()
                        break
                if move:
                    self.cache[fen] = move
                    self._unsaved += 1
                    if self._unsaved >= 5:
                        self.save_cache()
                    return move, host.split('/')[2]
                # 该残局不在库中: 缓存 None, 下次不再联网
                self.cache[fen] = None
                self._unsaved += 1
                if self._unsaved >= 5:
                    self.save_cache()
                return None, None
            except Exception as exc:
                last_err = exc
                continue
        self.errors += 1
        if last_err:
            print(f'[egtb] 查询失败: {type(last_err).__name__}')
        return None, None

    def probe(self, board, current_player, legal_moves=None):
        """
        查询残局库走法。返回 (move, source) 或 (None, None)。
        move 保证是合法着法 (若提供 legal_moves)。
        """
        if not self.enabled:
            return None, None
        fen = board_to_fen(board, current_player)
        uci, source = self._query(fen)
        if not uci:
            self.misses += 1
            return None, None
        try:
            move = self.uci_to_engine(uci)
        except (ValueError, IndexError):
            self.misses += 1
            return None, None
        if legal_moves is not None and move not in legal_moves:
            self.misses += 1
            return None, None
        self.hits += 1
        return move, source

    def get_stats(self):
        return {
            'enabled': self.enabled,
            'local_backend': self.local_ok,
            'cached': len(self.cache),
            'hits': self.hits,
            'misses': self.misses,
            'errors': self.errors,
        }


if __name__ == '__main__':
    from mini_chess import ChineseChess

    eb = EndgameBook()
    g = ChineseChess()
    # 经典残局：黑将 d8 + 红车 e2 + 红帅 e0，FEN 与手工验证一致
    g.board = [['.' for _ in range(9)] for _ in range(10)]
    g.board[9][3] = 'k'
    g.board[2][4] = 'R'
    g.board[0][4] = 'K'
    g.current_player = 'red'
    fen = board_to_fen(g.board, 'red')
    print('FEN:', fen)
    print('CDB query:', eb._query(fen))
    src = eb.probe(g.board, 'red', g.get_all_legal_moves())
    print('probe:', src)
    print('stats:', eb.get_stats())
