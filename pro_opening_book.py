"""
职业开局库适配层

数据来源: xiangqi-pikafish-web / gui-web/book_tree.json (由 Eleeye BOOK.DAT 转换)
规模: 51,101 个局面, 最深 23 手, 权重来自职业比赛对局统计

坐标约定:
  UCI  a0 = 红方左下角, 列 a-i (0-8), 行 0-9
  引擎 board[row][col], row 0 = 红方底线, col 0 = 红方左侧
  两者一一对应: UCI "b2e2" -> 引擎 (2,1)->(2,4) 红炮平中
"""

import json
import os
import random


class ProOpeningBook:
    DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'data', 'book_tree.json')

    def __init__(self, path=None):
        self.path = path or self.DEFAULT_PATH
        self.book = {}
        self.loaded = False
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            print(f"[pro_book] 开局库文件不存在: {self.path}")
            return
        try:
            with open(self.path, encoding='utf-8') as f:
                self.book = json.load(f)
            self.loaded = bool(self.book)
            if self.loaded:
                print(f"[pro_book] 已加载 {len(self.book)} 个局面")
        except Exception as exc:
            print(f"[pro_book] 加载失败: {exc}")
            self.book = {}
            self.loaded = False

    @staticmethod
    def engine_to_uci(move):
        """(sr,sc,er,ec) -> 'b2e2'"""
        sr, sc, er, ec = move
        return f"{chr(ord('a') + sc)}{sr}{chr(ord('a') + ec)}{er}"

    @staticmethod
    def uci_to_engine(uci):
        """'b2e2' -> (2,1,2,4)"""
        return (int(uci[1]), ord(uci[0].lower()) - ord('a'),
                int(uci[3]), ord(uci[2].lower()) - ord('a'))

    def _key(self, move_history):
        # 引擎 move_history 元素为 (sr, sc, er, ec, captured), 只取前 4 位
        return ' '.join(self.engine_to_uci(m[:4]) for m in move_history)

    def get_candidates(self, move_history):
        """返回当前局面的库着法 [(engine_move, uci, weight), ...], 按权重降序"""
        if not self.loaded:
            return []
        raw = self.book.get(self._key(move_history))
        if not raw:
            return []
        out = []
        for uci, weight in raw.items():
            try:
                out.append((self.uci_to_engine(uci), uci, int(weight)))
            except (ValueError, IndexError):
                continue
        out.sort(key=lambda x: x[2], reverse=True)
        return out

    def pick_book_move(self, move_history, legal_moves=None):
        """
        按权重随机选一个库着法。
        legal_moves 传入时只从合法着法中选 (防止库外着法/坐标错位污染)。
        返回 (move, info_str) 或 (None, None)
        """
        candidates = self.get_candidates(move_history)
        if not candidates:
            return None, None
        if legal_moves is not None:
            legal = set(legal_moves)
            candidates = [c for c in candidates if c[0] in legal]
            if not candidates:
                return None, None

        total = sum(c[2] for c in candidates)
        if total <= 0:
            move, uci, weight = candidates[0]
            return move, f"{uci}(w={weight})"
        r = random.randint(1, total)
        acc = 0
        for move, uci, weight in candidates:
            acc += weight
            if r <= acc:
                return move, f"{uci}(w={weight})"
        move, uci, weight = candidates[-1]
        return move, f"{uci}(w={weight})"

    def get_stats(self):
        positions = len(self.book)
        variations = sum(len(v) for v in self.book.values())
        max_ply = max((len(k.split()) for k in self.book), default=0)
        return {
            'positions': positions,
            'variations': variations,
            'max_ply': max_ply,
            'loaded': self.loaded,
            'path': self.path,
        }


if __name__ == '__main__':
    book = ProOpeningBook()
    print(book.get_stats())
    for hist in ([], [(2, 7, 5, 7)], [(2, 7, 5, 7), (9, 7, 7, 6)]):
        print(hist, '->', book.get_candidates(hist)[:6])
