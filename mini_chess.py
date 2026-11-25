import time
import random
import pickle
import sys
import re
import unicodedata
from collections import defaultdict
import threading
from copy import deepcopy

# Windows 控制台默认 GBK：✓/✗/emoji 会抛 UnicodeEncodeError 中断对局。
# 保留控制台原有编码（中文仍可正常显示），仅把不可编码字符替换为 ?。
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except (ValueError, OSError):
        pass

# Import opening book
try:
    from opening_book import OpeningBook
    OPENING_BOOK_AVAILABLE = True
except ImportError:
    OPENING_BOOK_AVAILABLE = False
    print("Warning: opening_book.py not found. Opening book disabled.")

# 职业开局库 (51,101 局面, 源自 Eleeye BOOK.DAT)
try:
    from pro_opening_book import ProOpeningBook
    PRO_BOOK_AVAILABLE = True
except ImportError:
    PRO_BOOK_AVAILABLE = False
    print("Warning: pro_opening_book.py not found. Pro opening book disabled.")

# 残局库 (CDB 云库, searqu.com; 带本地缓存与超时降级)
try:
    from endgame_book import EndgameBook
    EGTB_AVAILABLE = True
except ImportError:
    EGTB_AVAILABLE = False
    print("Warning: endgame_book.py not found. Endgame book disabled.")

# 位置价值表是纯静态数据，模块级缓存一次即可
_POSITION_TABLES_CACHE = None


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def display_width(text):
    """终端实际列宽：ANSI 序列算 0 列，全角/宽字符算 2 列，其余算 1 列。"""
    text = _ANSI_RE.sub('', text)
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ('F', 'W') else 1
    return width


def pad_cell(text, width=3):
    """把单元格补齐到固定显示宽度（居中），保证中英文棋子列对齐。"""
    gap = width - display_width(text)
    if gap <= 0:
        return text
    left = gap // 2
    return ' ' * left + text + ' ' * (gap - left)


class ChineseChess:
    # 将死分数量级需远大于子力总和(初始约 3200*2=6400), 且 quiescence 同源
    MATE_VALUE = 100000

    def __init__(self):
        # 棋盘表示 (10行×9列)
        self.board = [['.' for _ in range(9)] for _ in range(10)]
        self.current_player = 'red'  # 'red' 或 'black'
        self.move_history = []
        self.last_move = None  # 记录最后一次移动，用于高亮显示

        # AI设置
        self.ai_enabled = True
        # search_depth 作为迭代加深的"上限", 由时间预算决定实际深度。
        # 原值为 3: 搜完 3 层即停, 5 秒预算只用 65%, 白白浪费 => 提到 6。
        self.search_depth = 6
        self.thinking_time = 5.0
        self.use_cache = True

        # 将死分数开关: True=将死返回 ±(MATE-ply) 且合并到走法检查(省两次全量生成)。
        # False=旧行为(将死返回普通评估分), 供 A/B 对照。
        self.use_mate_score = True

        # 时间预算开关: True=用满用户设定时间(仅按复杂度小幅调节)。
        # False=旧行为(开局x0.7、前10手x0.5 双重削减, 5秒只剩1.75秒), 供 A/B 对照。
        self.use_full_time_budget = True

        # TT flag 修复开关: True=用函数入口的原始窗口判定 EXACT/LOWER/UPPER。
        # False=旧行为(用循环中被更新过的 alpha/beta 判定, 会把精确值误标为上界), 供 A/B。
        self.use_tt_flag_fix = True

        # 中心控制评估开关: True=按"攻击控制"计分(有信息量), False=旧"占据"式(中局恒0)。
        self.use_control_eval = True

        # 显示设置
        self.display_mode = 'chinese'  # 'chinese' 或 'english'

        # 性能统计（供 UI 展示：思考时间/速度/深度）
        self.nodes_searched = 0
        self.search_start_time = 0
        self.last_search_stats = {'source': 'none', 'time': 0.0, 'nodes': 0,
                                  'depth': 0, 'nps': 0}

        # Zobrist哈希表
        self.zobrist_table = self.init_zobrist_table()
        self.transposition_table = {}
        self.search_generation = 0  # Track age of TT entries for better replacement
        self.tt_lock = threading.Lock()  # Lock for thread-safe TT access

        # 当前搜索实际生效的时间预算（由自适应时间管理设置）。
        # alpha_beta/quiescence 用它做超时检查；None 时回退到 thinking_time。
        self._effective_time_limit = None

        # UCI stop：置 True 后搜索在下一个检查点返回当前最佳着法（uci_interface 使用）
        self.stop_requested = False

        # 位置历史（用于检测重复）
        self.position_history = []

        # 长将检测：与 position_history / move_history 平行的每步记录 (走子方, 是否将军对方)
        self.check_history = []

        # 自然限着：无吃子且无兵/卒前进的连续半回合数，达到上限判和。
        # 中国象棋规程为 60 回合（=120 半回合）。撤销时需同步回退。
        self.halfmove_clock = 0
        self.halfmove_history = []
        self.natural_limit_plies = 120

        # 静态搜索剪枝开关。实测在本引擎绝对分口径下 delta pruning 反而增加
        # 约 23% 节点（剪枝改变搜索树形状、降低 TT 命中率），故默认关闭，仅留作对照。
        self.use_delta_pruning = False
        # 机动性评估开关。 mobility 项需两次全量合法走法生成（约 38% 叶子开销），
        # 但权重仅 5、分数贡献极小；默认关闭以提速，可用开关做 A/B 对照。
        self.use_mobility_eval = False
        # 威胁惩罚系数：审计发现原 0.3 且含将帅(10000)导致威胁项 std 523 压过子力 134。
        # 默认用收敛值；设 None 表示沿用旧行为(0.3, 含将帅)供 A/B。
        self.threat_hanging_scale = 0.1
        self.threat_exclude_king = True
        # king_safety 里的静态"被将军 -200"惩罚：将军应由搜索层将死/quiescence 处理，
        # 静态评估重复罚分且叶子节点多一次 is_in_check。默认关闭，开关供 A/B。
        self.use_king_check_penalty = False
        # delta pruning 参数：仅在宽窗口启用，避免 PVS/LMR 零窗口 re-search 反增节点
        self.delta_margin = 200
        self.delta_min_window = 1000

        # Killer moves: [ply][killer_index] - 存储每层的2个killer moves
        self.max_ply = 64
        self.killer_moves = [[None, None] for _ in range(self.max_ply)]

        # History heuristic: 记录走法的历史得分
        self.history_table = {}

        # Quiescence搜索深度限制
        self.max_quiescence_depth = 10

        # Opening book
        if OPENING_BOOK_AVAILABLE:
            self.opening_book = OpeningBook()
            self.use_opening_book = True
        else:
            self.opening_book = None
            self.use_opening_book = False

        # 职业开局库 (优先于手写库)
        if PRO_BOOK_AVAILABLE:
            self.pro_book = ProOpeningBook()
            self.use_pro_book = self.pro_book.loaded
        else:
            self.pro_book = None
            self.use_pro_book = False

        # 残局库 (子力 <= 阈值时查询 CDB)
        if EGTB_AVAILABLE:
            self.endgame_book = EndgameBook()
            self.use_endgame_book = True
            self.egtb_piece_limit = 12  # 不含将帅的总子力阈值
        else:
            self.endgame_book = None
            self.use_endgame_book = False
            self.egtb_piece_limit = 0

        self.init_board()

    def init_zobrist_table(self):
        """初始化Zobrist哈希表"""
        random.seed(42)  # 固定种子保证可重现
        table = {}
        pieces = ['K', 'A', 'B', 'R', 'H', 'C', 'P',
                  'k', 'a', 'b', 'r', 'h', 'c', 'p', '.']
        for piece in pieces:
            table[piece] = [[random.getrandbits(64) for _ in range(9)] for _ in range(10)]
        return table

    def get_zobrist_key(self):
        """计算当前棋盘的Zobrist哈希值（包含轮到谁走）"""
        key = 0
        for i in range(10):
            for j in range(9):
                piece = self.board[i][j]
                key ^= self.zobrist_table[piece][i][j]
        # 同一棋盘、不同走棋方是不同局面：不区分会导致 TT 键碰撞、
        # 重复局面误判。修复前 4/8 局面出现 TT 开/关结果不一致。
        if self.current_player == 'black':
            key ^= 0x9E3779B97F4A7C15
        return key

    def store_tt_entry(self, key, depth, value, best_move, flag='EXACT'):
        """
        Enhanced transposition table storage with replacement scheme (Thread-Safe)
        Only replace if: new entry is deeper OR old entry is from old search
        """
        with self.tt_lock:
            should_store = True

            if key in self.transposition_table:
                old_entry = self.transposition_table[key]
                # Keep deeper entries from recent searches (within 2 generations)
                if old_entry['depth'] > depth and old_entry.get('age', 0) >= self.search_generation - 2:
                    should_store = False

            if should_store:
                self.transposition_table[key] = {
                    'depth': depth,
                    'value': value,
                    'best_move': best_move,
                    'flag': flag,
                    'age': self.search_generation
                }

    def probe_tt(self, key, depth, alpha=None, beta=None):
        """
        Probe transposition table (Thread-Safe)
        Returns: (value, best_move) or (None, None)

        value 只在窗口内可用：EXACT 恒可用；LOWER 需 >= beta；
        UPPER 需 <= alpha。否则窄窗口搜索的边界值会被当作精确值，
        污染搜索结果（修复前 TT 开/关 4/8 局面不一致）。
        """
        with self.tt_lock:
            if key in self.transposition_table:
                entry = self.transposition_table[key]
                if entry['depth'] >= depth:
                    v = entry['value']
                    flag = entry.get('flag', 'EXACT')
                    if alpha is not None and beta is not None:
                        if flag == 'EXACT':
                            return v, entry.get('best_move')
                        if flag == 'LOWER' and v >= beta:
                            return v, entry.get('best_move')
                        if flag == 'UPPER' and v <= alpha:
                            return v, entry.get('best_move')
                        return None, entry.get('best_move')
                    return v, entry.get('best_move')
                # Even if depth is insufficient, return the best move for move ordering
                return None, entry.get('best_move')
            return None, None

    def init_board(self):
        """初始化棋盘"""
        # 红方布局 (0-3行)
        self.board[0] = ['R', 'H', 'B', 'A', 'K', 'A', 'B', 'H', 'R']
        self.board[1] = ['.', '.', '.', '.', '.', '.', '.', '.', '.']
        self.board[2] = ['.', 'C', '.', '.', '.', '.', '.', 'C', '.']
        self.board[3] = ['P', '.', 'P', '.', 'P', '.', 'P', '.', 'P']
        self.board[4] = ['.', '.', '.', '.', '.', '.', '.', '.', '.']

        # 黑方布局 (6-9行)
        self.board[5] = ['.', '.', '.', '.', '.', '.', '.', '.', '.']
        self.board[6] = ['p', '.', 'p', '.', 'p', '.', 'p', '.', 'p']
        self.board[7] = ['.', 'c', '.', '.', '.', '.', '.', 'c', '.']
        self.board[8] = ['.', '.', '.', '.', '.', '.', '.', '.', '.']
        self.board[9] = ['r', 'h', 'b', 'a', 'k', 'a', 'b', 'h', 'r']

    def display_board(self):
        """显示棋盘：中英文棋子均按固定列宽对齐，高亮用反显不改变宽度"""
        chinese_pieces = {
            'K': '帅', 'A': '仕', 'B': '相', 'R': '车', 'H': '马', 'C': '炮', 'P': '兵',
            'k': '将', 'a': '士', 'b': '象', 'r': '車', 'h': '馬', 'c': '砲', 'p': '卒',
            '.': '·'
        }
        english_pieces = {
            'K': 'K', 'A': 'A', 'B': 'B', 'R': 'R', 'H': 'H', 'C': 'C', 'P': 'P',
            'k': 'k', 'a': 'a', 'b': 'b', 'r': 'r', 'h': 'h', 'c': 'c', 'p': 'p',
            '.': '.'
        }
        piece_map = chinese_pieces if self.display_mode == 'chinese' else english_pieces

        RED = '\033[91m'
        BLACK = '\033[90m'
        HIGHLIGHT = '\033[7m'       # 反显：只改背景，不改变字符列宽
        RESET = '\033[0m'
        use_color = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

        CELL = 3
        GRID = '+' + '+'.join('─' * CELL for _ in range(9)) + '+'
        HEAD = '   ' + ''.join(pad_cell(str(j), CELL) for j in range(9))

        print(HEAD)
        print(GRID)
        for i in range(10):
            side = '黑' if i >= 5 else '红'
            side_label = '黑方' if i == 9 else ('红方' if i == 0 else '')
            row_display = []
            for j in range(9):
                piece = self.board[i][j]
                piece_char = piece_map[piece]
                color = ''
                if use_color and piece != '.':
                    color = RED if self.is_red_piece(piece) else BLACK
                is_hl = bool(self.last_move) and (
                    (i, j) == tuple(self.last_move[:2]) or (i, j) == tuple(self.last_move[2:]))
                if is_hl:
                    if use_color:
                        cell = HIGHLIGHT + piece_char + RESET
                    else:
                        cell = '*' + piece_char       # 无颜色环境用 * 标记
                else:
                    cell = color + piece_char + (RESET if color else '')
                row_display.append(pad_cell(cell, CELL))
            print(f"{i} {side}|{''.join(row_display)}| {side_label}")
            if i == 4:  # 楚河汉界
                print('   ' + '─' * (CELL * 9 + 10) + '  楚河  汉界')
        print(GRID)
        print(HEAD)
        print(f"当前回合: {'红方' if self.current_player == 'red' else '黑方'}")
        if self.last_move:
            sr, sc, er, ec = self.last_move
            name = chinese_pieces.get(self.board[er][ec], '未知')
            print(f"上一步移动: ({sr}, {sc}) -> ({er}, {ec}) [{name}]")

    def is_red_piece(self, piece):
        """判断是否为红方棋子"""
        return piece in 'KABRHCP'

    def is_black_piece(self, piece):
        """判断是否为黑方棋子"""
        return piece in 'kabrhcp'

    def count_material(self):
        """统计非将帅子力总数 (用于判断是否进入残局库范围)"""
        n = 0
        for row in self.board:
            for p in row:
                if p != '.' and p.upper() != 'K':
                    n += 1
        return n

    def get_all_legal_moves(self, player=None):
        """获取所有合法走法，包括应将处理"""
        if player is None:
            player = self.current_player

        moves = []
        for i in range(10):
            for j in range(9):
                piece = self.board[i][j]
                if (player == 'red' and piece.isupper()) or (player == 'black' and piece.islower()):
                    moves.extend(self.get_piece_moves(i, j))

        # 如果当前玩家被将军，则过滤走法，只保留解除将军的走法
        if self.is_in_check(player):
            valid_moves = []
            for move in moves:
                start_row, start_col, end_row, end_col = move
                captured_piece = self.make_move(start_row, start_col, end_row, end_col, track_check=False)
                # 检查移动后是否仍然被将军
                if not self.is_in_check(player):
                    valid_moves.append(move)
                self.undo_move(start_row, start_col, end_row, end_col, captured_piece)
            return valid_moves
        else:
            return moves

    def is_under_attack(self, row, col, player):
        """判断位置(row, col)是否被对方玩家攻击"""
        # 对方玩家
        opponent = 'black' if player == 'red' else 'red'

        # 检查将帅照面
        if player == 'red':
            # 红方帅，检查黑方将
            red_king_pos = (row, col)
            black_king_pos = None
            for i in range(10):
                for j in range(9):
                    if self.board[i][j] == 'k':
                        black_king_pos = (i, j)
                        break
            if black_king_pos and red_king_pos[1] == black_king_pos[1]:
                # 在同一列，检查中间是否有棋子
                start_row = min(red_king_pos[0], black_king_pos[0]) + 1
                end_row = max(red_king_pos[0], black_king_pos[0])
                has_piece_between = False
                for r in range(start_row, end_row):
                    if self.board[r][col] != '.':
                        has_piece_between = True
                        break
                if not has_piece_between:
                    return True
        else:
            # 黑方将，检查红方帅
            black_king_pos = (row, col)
            red_king_pos = None
            for i in range(10):
                for j in range(9):
                    if self.board[i][j] == 'K':
                        red_king_pos = (i, j)
                        break
            if red_king_pos and black_king_pos[1] == red_king_pos[1]:
                start_row = min(red_king_pos[0], black_king_pos[0]) + 1
                end_row = max(red_king_pos[0], black_king_pos[0])
                has_piece_between = False
                for r in range(start_row, end_row):
                    if self.board[r][col] != '.':
                        has_piece_between = True
                        break
                if not has_piece_between:
                    return True

        # 检查对方其他棋子
        for i in range(10):
            for j in range(9):
                piece = self.board[i][j]
                if (opponent == 'red' and piece.isupper()) or (opponent == 'black' and piece.islower()):
                    # 这是一个对方棋子，获取它的走法
                    moves = self.get_piece_moves(i, j)
                    for move in moves:
                        if move[2] == row and move[3] == col:
                            return True
        return False

    def is_defended(self, row, col, player):
        """判断位置(row, col)是否被己方棋子保护"""
        # 检查己方其他棋子是否能移动到这个位置（保护它）
        for i in range(10):
            for j in range(9):
                piece = self.board[i][j]
                if piece != '.' and ((player == 'red' and piece.isupper()) or (player == 'black' and piece.islower())):
                    # 这是己方棋子，检查它是否能移动到目标位置
                    moves = self.get_piece_moves(i, j)
                    for move in moves:
                        if move[2] == row and move[3] == col:
                            return True
        return False

    def is_in_check(self, player):
        """判断玩家player是否被将军"""
        # 找到player的将/帅位置
        king_symbol = 'K' if player == 'red' else 'k'
        king_pos = None
        for i in range(10):
            for j in range(9):
                if self.board[i][j] == king_symbol:
                    king_pos = (i, j)
                    break
            if king_pos:
                break
        if king_pos is None:
            return False  # 将/帅不在棋盘上，理论上不会发生
        return self.is_under_attack(king_pos[0], king_pos[1], player)

    def get_piece_moves(self, row, col):
        """获取单个棋子的所有合法走法"""
        piece = self.board[row][col].upper()
        moves = []

        if piece == 'K':  # 将/帅
            moves = self.get_king_moves(row, col)
        elif piece == 'A':  # 仕/士
            moves = self.get_advisor_moves(row, col)
        elif piece == 'B':  # 相/象
            moves = self.get_bishop_moves(row, col)
        elif piece == 'R':  # 车
            moves = self.get_rook_moves(row, col)
        elif piece == 'H':  # 马
            moves = self.get_knight_moves(row, col)
        elif piece == 'C':  # 炮
            moves = self.get_cannon_moves(row, col)
        elif piece == 'P':  # 兵/卒
            moves = self.get_pawn_moves(row, col)

        return moves

    def get_king_moves(self, row, col):
        """将/帅的走法"""
        moves = []
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
        piece = self.board[row][col]

        for dr, dc in directions:
            new_row, new_col = row + dr, col + dc
            if self.is_valid_move(row, col, new_row, new_col):
                # 检查将帅照面
                if not self.kings_face_each_other_after_move(row, col, new_row, new_col):
                    # 检查是否在九宫格内
                    if piece.isupper():  # 红方帅
                        if 0 <= new_row <= 2 and 3 <= new_col <= 5:
                            moves.append((row, col, new_row, new_col))
                    else:  # 黑方将
                        if 7 <= new_row <= 9 and 3 <= new_col <= 5:
                            moves.append((row, col, new_row, new_col))

        return moves

    def get_advisor_moves(self, row, col):
        """仕/士的走法"""
        moves = []
        directions = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        piece = self.board[row][col]

        for dr, dc in directions:
            new_row, new_col = row + dr, col + dc
            if self.is_valid_move(row, col, new_row, new_col):
                # 检查是否在九宫格内
                if piece.isupper():  # 红方仕
                    if 0 <= new_row <= 2 and 3 <= new_col <= 5:
                        moves.append((row, col, new_row, new_col))
                else:  # 黑方士
                    if 7 <= new_row <= 9 and 3 <= new_col <= 5:
                        moves.append((row, col, new_row, new_col))

        return moves

    def get_bishop_moves(self, row, col):
        """相/象的走法"""
        moves = []
        directions = [(-2, -2), (-2, 2), (2, -2), (2, 2)]
        piece = self.board[row][col]

        for dr, dc in directions:
            new_row, new_col = row + dr, col + dc
            if self.is_valid_move(row, col, new_row, new_col):
                # 检查象眼是否被塞
                eye_row, eye_col = row + dr // 2, col + dc // 2
                if self.board[eye_row][eye_col] != '.':
                    continue

                # 检查是否过河
                if piece.isupper():  # 红方相
                    if new_row >= 5:  # 不能过河
                        continue
                else:  # 黑方象
                    if new_row <= 4:  # 不能过河
                        continue

                moves.append((row, col, new_row, new_col))

        return moves

    def get_rook_moves(self, row, col):
        """车的走法"""
        moves = []
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]

        for dr, dc in directions:
            for step in range(1, 10):
                new_row, new_col = row + dr * step, col + dc * step
                if not (0 <= new_row < 10 and 0 <= new_col < 9):
                    break

                if not self.is_valid_move(row, col, new_row, new_col):
                    break

                moves.append((row, col, new_row, new_col))

                # 如果遇到棋子，停止这个方向
                if self.board[new_row][new_col] != '.':
                    break

        return moves

    def get_knight_moves(self, row, col):
        """马的走法"""
        moves = []
        # 马走"日"字，有8个可能方向
        knight_moves = [
            (-2, -1), (-2, 1),  # 向上走
            (-1, -2), (-1, 2),  # 向左走
            (1, -2), (1, 2),  # 向右走
            (2, -1), (2, 1)  # 向下走
        ]

        # 对应的马腿位置
        leg_positions = {
            (-2, -1): (-1, 0), (-2, 1): (-1, 0),  # 向上走的马腿在正上方
            (-1, -2): (0, -1), (-1, 2): (0, 1),  # 向左/右走的马腿在正左/右方
            (1, -2): (0, -1), (1, 2): (0, 1),  # 向左/右走的马腿在正左/右方
            (2, -1): (1, 0), (2, 1): (1, 0)  # 向下走的马腿在正下方
        }

        for dr, dc in knight_moves:
            new_row, new_col = row + dr, col + dc
            if not (0 <= new_row < 10 and 0 <= new_col < 9):
                continue

            # 检查马腿
            leg_dr, leg_dc = leg_positions[(dr, dc)]
            leg_row, leg_col = row + leg_dr, col + leg_dc

            # 马腿必须在棋盘内
            if not (0 <= leg_row < 10 and 0 <= leg_col < 9):
                continue

            # 马腿位置有棋子则不能走
            if self.board[leg_row][leg_col] != '.':
                continue

            if self.is_valid_move(row, col, new_row, new_col):
                moves.append((row, col, new_row, new_col))

        return moves


    def get_cannon_moves(self, row, col):
        """炮的走法"""
        moves = []
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]

        for dr, dc in directions:
            has_piece = False
            for step in range(1, 10):
                new_row, new_col = row + dr * step, col + dc * step
                if not (0 <= new_row < 10 and 0 <= new_col < 9):
                    break

                if not has_piece:
                    # 炮移动时，路径上不能有棋子
                    if self.board[new_row][new_col] != '.':
                        has_piece = True
                        continue  # 跳过这个棋子，继续向后看
                    else:
                        if self.is_valid_move(row, col, new_row, new_col):
                            moves.append((row, col, new_row, new_col))
                else:
                    # 炮吃子时，必须跳过一个棋子
                    if self.board[new_row][new_col] != '.':
                        if self.is_valid_move(row, col, new_row, new_col):
                            moves.append((row, col, new_row, new_col))
                        break  # 吃子后停止

        return moves

    def get_pawn_moves(self, row, col):
        """兵/卒的走法"""
        moves = []
        piece = self.board[row][col]

        if piece.isupper():  # 红方兵
            # 红兵向前走 (向下)
            directions = [(1, 0)]
            # 过河后可以左右走
            if row >= 5:
                directions.extend([(0, 1), (0, -1)])
        else:  # 黑方卒
            # 黑卒向前走 (向上)
            directions = [(-1, 0)]
            # 过河后可以左右走
            if row <= 4:
                directions.extend([(0, 1), (0, -1)])

        for dr, dc in directions:
            new_row, new_col = row + dr, col + dc
            if self.is_valid_move(row, col, new_row, new_col):
                moves.append((row, col, new_row, new_col))

        return moves

    def is_valid_move(self, start_row, start_col, end_row, end_col):
        """验证走法是否基本合法"""
        # 检查是否在棋盘内
        if not (0 <= end_row < 10 and 0 <= end_col < 9):
            return False

        start_piece = self.board[start_row][start_col]
        end_piece = self.board[end_row][end_col]

        # 不能吃自己的棋子
        if (start_piece.isupper() and end_piece.isupper()) or \
                (start_piece.islower() and end_piece.islower()):
            return False

        return True

    def kings_face_each_other_after_move(self, start_row, start_col, end_row, end_col):
        """检查移动后是否将帅照面"""
        # 临时执行移动
        temp_piece = self.board[end_row][end_col]
        self.board[end_row][end_col] = self.board[start_row][start_col]
        self.board[start_row][start_col] = '.'

        # 查找将帅位置
        king_red_pos = None
        king_black_pos = None

        for i in range(10):
            for j in range(9):
                if self.board[i][j] == 'K':
                    king_red_pos = (i, j)
                elif self.board[i][j] == 'k':
                    king_black_pos = (i, j)

        result = False
        if king_red_pos and king_black_pos and king_red_pos[1] == king_black_pos[1]:
            # 在同一列，检查中间是否有棋子
            col = king_red_pos[1]
            start_row_idx = min(king_red_pos[0], king_black_pos[0]) + 1
            end_row_idx = max(king_red_pos[0], king_black_pos[0])
            has_piece_between = False
            for row in range(start_row_idx, end_row_idx):
                if self.board[row][col] != '.':
                    has_piece_between = True
                    break
            result = not has_piece_between

        # 恢复棋盘
        self.board[start_row][start_col] = self.board[end_row][end_col]
        self.board[end_row][end_col] = temp_piece

        return result

    def alpha_beta_search(self, depth, alpha, beta, maximizing_player, start_time, ply=0, allow_null_move=True, extensions=0):
        """Alpha-Beta搜索算法（带Quiescence搜索、Null move pruning、PVS和检查延伸）"""
        self.nodes_searched += 1

        # 保存入口窗口, 供 TT flag 判定 (循环中的 alpha/beta 会被更新, 不能用于判定)
        alpha_orig, beta_orig = alpha, beta

        # 最大延伸深度限制（防止无限延伸）
        max_extensions = 16

        # 时间检查（遵守自适应时间预算；stop_requested 供 UCI stop 中断）
        limit = self._effective_time_limit or self.thinking_time
        if self.stop_requested or time.time() - start_time > limit:
            return self.evaluate_board()

        # 检查置换表
        zobrist_key = self.get_zobrist_key()
        tt_value, tt_move = self.probe_tt(zobrist_key, depth, alpha, beta)
        if self.use_cache and tt_value is not None:
            return tt_value

        # 检查重复局面（和棋）
        if self.position_history.count(zobrist_key) >= 2:
            return 0  # 重复局面判和

        # 叶子节点 - 使用quiescence搜索（沿用当前节点的极大/极小方）
        if depth == 0:
            return self.quiescence_search(alpha, beta, 0, start_time, maximizing_player)

        # Null Move Pruning - 在非PV节点且不在将军状态下尝试
        # 只在深度足够且允许null move时使用
        if allow_null_move and depth >= 3 and not self.is_in_check(self.current_player):
            # 执行null move（切换玩家但不移动棋子）
            self.current_player = 'black' if self.current_player == 'red' else 'red'

            # 使用减少的深度搜索（R=2）
            # 注意：本引擎用绝对分数（红正黑负），不能用 negamax 的 -score/-beta。
            # maximizing_player 随"轮到谁"取反，窗口保持不变。
            R = 2
            null_score = self.alpha_beta_search(
                depth - R - 1,
                beta - 1,
                beta,  # 零窗口，检验能否>=beta
                not maximizing_player,
                start_time,
                ply + 1,
                allow_null_move=False,  # 不允许连续null move
                extensions=extensions  # 传递当前延伸深度
            )

            # 撤销null move
            self.current_player = 'black' if self.current_player == 'red' else 'red'

            # 绝对分数下，极大方用 >=beta，极小方用 <=alpha 对称处理
            if maximizing_player and null_score >= beta:
                return beta
            elif not maximizing_player and null_score <= alpha:
                return alpha

        # 无合法走法 = 当前走子方被将死/困毙 (中国象棋困毙亦判负)。
        # 只需一次走法生成: 旧实现先 is_checkmate('red')+('black') 各生成一次,
        # 再 get_all_legal_moves() 又生成一次, 每节点 3 次全量生成, 是最大浪费。
        moves = self.get_all_legal_moves()
        if not moves:
            if self.use_mate_score:
                # ±(MATE-ply): 近的杀棋分数更高, 引擎才会主动找最快将死
                mated_by_red = (self.current_player == 'red')
                return (-self.MATE_VALUE + ply) if mated_by_red else (self.MATE_VALUE - ply)
            return self.evaluate_board()

        # 走法排序（传递ply用于killer moves，传递tt_move优先考虑）
        moves = self.order_moves(moves, ply, tt_move)

        if maximizing_player:
            max_eval = float('-inf')
            first_move = True
            best_move_this_node = None

            for i, move in enumerate(moves):
                start_row, start_col, end_row, end_col = move
                captured_piece = self.make_move(start_row, start_col, end_row, end_col, track_check=False)

                # Check Extension: 检查这步棋是否将军对方
                opponent = 'black'
                gives_check = self.is_in_check(opponent)

                # 确定搜索深度（考虑将军延伸）
                if gives_check and extensions < max_extensions:
                    base_depth = depth  # 将军延伸：不减少深度
                    use_extension = True
                    new_extensions = extensions + 1
                else:
                    base_depth = depth - 1  # 正常深度
                    use_extension = False
                    new_extensions = extensions

                # Late Move Reductions (不在延伸时使用)
                use_lmr = (
                    not use_extension and  # 延伸时不使用LMR
                    i >= 4
                    and depth >= 3
                    and captured_piece == '.'
                    and not self.is_in_check(self.current_player)
                )

                # Principal Variation Search (PVS) + LMR + Check Extensions
                if first_move:
                    eval_score = self.alpha_beta_search(base_depth, alpha, beta, False, start_time, ply + 1, True, new_extensions)
                    first_move = False
                else:
                    if use_lmr:
                        R = 1 if depth < 6 else 2
                        eval_score = self.alpha_beta_search(base_depth - R, alpha, alpha + 1, False, start_time, ply + 1, True, new_extensions)
                        if alpha < eval_score < beta:
                            eval_score = self.alpha_beta_search(base_depth, alpha, alpha + 1, False, start_time, ply + 1, True, new_extensions)
                        if alpha < eval_score < beta:
                            eval_score = self.alpha_beta_search(base_depth, alpha, beta, False, start_time, ply + 1, True, new_extensions)
                    else:
                        eval_score = self.alpha_beta_search(base_depth, alpha, alpha + 1, False, start_time, ply + 1, True, new_extensions)
                        if alpha < eval_score < beta:
                            eval_score = self.alpha_beta_search(base_depth, alpha, beta, False, start_time, ply + 1, True, new_extensions)

                self.undo_move(start_row, start_col, end_row, end_col, captured_piece)

                if eval_score > max_eval:
                    max_eval = eval_score
                    best_move_this_node = move

                if eval_score > alpha:
                    alpha = eval_score
                    self.update_history(move, depth)

                if beta <= alpha:
                    self.update_killer_moves(move, ply)
                    break

            if self.use_cache and best_move_this_node:
                a0, b0 = (alpha_orig, beta_orig) if self.use_tt_flag_fix else (alpha, beta)
                flag = 'LOWER' if max_eval >= b0 else ('UPPER' if max_eval <= a0 else 'EXACT')
                self.store_tt_entry(zobrist_key, depth, max_eval, best_move_this_node, flag)
            return max_eval
        else:
            min_eval = float('inf')
            first_move = True
            best_move_this_node = None

            for i, move in enumerate(moves):
                start_row, start_col, end_row, end_col = move
                captured_piece = self.make_move(start_row, start_col, end_row, end_col, track_check=False)

                # Check Extension: 检查这步棋是否将军对方
                opponent = 'red'
                gives_check = self.is_in_check(opponent)

                # 确定搜索深度（考虑将军延伸）
                if gives_check and extensions < max_extensions:
                    base_depth = depth  # 将军延伸：不减少深度
                    use_extension = True
                    new_extensions = extensions + 1
                else:
                    base_depth = depth - 1  # 正常深度
                    use_extension = False
                    new_extensions = extensions

                # Late Move Reductions (不在延伸时使用)
                use_lmr = (
                    not use_extension and  # 延伸时不使用LMR
                    i >= 4
                    and depth >= 3
                    and captured_piece == '.'
                    and not self.is_in_check(self.current_player)
                )

                # Principal Variation Search (PVS) + LMR + Check Extensions
                if first_move:
                    eval_score = self.alpha_beta_search(base_depth, alpha, beta, True, start_time, ply + 1, True, new_extensions)
                    first_move = False
                else:
                    if use_lmr:
                        R = 1 if depth < 6 else 2
                        eval_score = self.alpha_beta_search(base_depth - R, beta - 1, beta, True, start_time, ply + 1, True, new_extensions)
                        if alpha < eval_score < beta:
                            eval_score = self.alpha_beta_search(base_depth, beta - 1, beta, True, start_time, ply + 1, True, new_extensions)
                        if alpha < eval_score < beta:
                            eval_score = self.alpha_beta_search(base_depth, alpha, beta, True, start_time, ply + 1, True, new_extensions)
                    else:
                        eval_score = self.alpha_beta_search(base_depth, beta - 1, beta, True, start_time, ply + 1, True, new_extensions)
                        if alpha < eval_score < beta:
                            eval_score = self.alpha_beta_search(base_depth, alpha, beta, True, start_time, ply + 1, True, new_extensions)

                self.undo_move(start_row, start_col, end_row, end_col, captured_piece)

                if eval_score < min_eval:
                    min_eval = eval_score
                    best_move_this_node = move

                if eval_score < beta:
                    beta = eval_score
                    self.update_history(move, depth)

                if beta <= alpha:
                    self.update_killer_moves(move, ply)
                    break

            if self.use_cache and best_move_this_node:
                a0, b0 = (alpha_orig, beta_orig) if self.use_tt_flag_fix else (alpha, beta)
                flag = 'UPPER' if min_eval <= a0 else ('LOWER' if min_eval >= b0 else 'EXACT')
                self.store_tt_entry(zobrist_key, depth, min_eval, best_move_this_node, flag)
            return min_eval

    def get_adaptive_thinking_time(self):
        """智能时间管理 - 根据局面复杂度调整思考时间"""
        base_time = self.thinking_time

        # 1. 统计棋盘上的棋子数量（判断游戏阶段）
        piece_count = sum(1 for row in self.board for piece in row if piece != '.')

        # 2. 统计合法走法数量（判断局面复杂度）
        legal_moves = len(self.get_all_legal_moves())

        # 3. 初始化时间倍数
        time_multiplier = 1.0

        # 4. 根据游戏阶段调整
        if piece_count > 20:
            # 开局阶段 - 减少思考时间（有开局库支持）
            time_multiplier *= 0.7
        elif piece_count > 10:
            # 中局阶段 - 增加思考时间（最复杂）
            time_multiplier *= 1.3
        else:
            # 残局阶段 - 正常时间
            time_multiplier *= 1.0

        # 5. 根据走法数量调整（局面复杂度）
        if legal_moves > 45:
            # 走法很多，局面复杂
            time_multiplier *= 1.3
        elif legal_moves > 35:
            # 走法较多
            time_multiplier *= 1.1
        elif legal_moves < 20:
            # 走法较少，局面简单
            time_multiplier *= 0.8
        elif legal_moves < 10:
            # 走法很少
            time_multiplier *= 0.6

        # 6. 如果被将军，增加思考时间（关键局面）
        if self.is_in_check(self.current_player):
            time_multiplier *= 1.5

        # 7. 如果在开局库范围内，大幅减少时间
        if len(self.move_history) < 10:
            time_multiplier *= 0.5

        # 8. 应用倍数并设置上下界
        if self.use_full_time_budget:
            # 职业开局库覆盖前 24 手, 开局阶段多数根本不搜索;
            # 旧逻辑的"开局减时"和"前10手减半"恰好砸在脱库后最需要思考的中局。
            # 改为以用户设定时间为准, 只按复杂度在 [0.8, 1.5] 倍内微调。
            adjusted_time = base_time
            if legal_moves > 45:
                adjusted_time *= 1.2
            elif legal_moves < 12:
                adjusted_time *= 0.8
            if self.is_in_check(self.current_player):
                adjusted_time *= 1.25
            min_time = base_time * 0.8
            max_time = base_time * 1.5
        else:
            adjusted_time = base_time * time_multiplier
            min_time = base_time * 0.3
            max_time = base_time * 2.0

        final_time = max(min_time, min(adjusted_time, max_time))

        return final_time

    def iterative_deepening_search(self):
        """迭代加深搜索（开局库 + 智能时间管理）。多进程路径已移除（实测更慢且结果不一致）。

        注意：stop_requested 不在此重置（会与 UCI 的 go/stop 竞争），
        由调用方（uci_interface / 服务端）在发起搜索前自行清除。
        """

        try:
            # 1) 职业开局库优先 (51,101 局面, 最深 23 手; 只取合法着法)
            if self.use_pro_book and self.pro_book and len(self.move_history) < 24:
                legal = self.get_all_legal_moves()
                move, info = self.pro_book.pick_book_move(self.move_history, legal)
                if move:
                    self.last_search_stats = {'source': 'pro_book', 'time': 0.0, 'nodes': 0,
                                              'depth': 0, 'nps': 0, 'info': info}
                    print(f"[pro_book] 使用职业开局库: {info}")
                    return move

            # 2) 手写开局库兜底 (仅前 10 手)
            if self.use_opening_book and self.opening_book and len(self.move_history) < 10:
                book_move = self.opening_book.get_book_move_by_moves(self.move_history)
                if book_move:
                    self.last_search_stats = {'source': 'opening_book', 'time': 0.0, 'nodes': 0,
                                              'depth': 0, 'nps': 0, 'info': str(book_move)}
                    print(f"📚 使用开局库走法: {book_move}")
                    return book_move

            # 3) 残局库 (子力 <= 阈值时查询 CDB, 带缓存/超时降级)
            if self.use_endgame_book and self.endgame_book and \
                    self.count_material() <= self.egtb_piece_limit:
                eg_move, src = self.endgame_book.probe(
                    self.board, self.current_player, self.get_all_legal_moves())
                if eg_move:
                    self.last_search_stats = {'source': 'egtb:' + str(src), 'time': 0.0,
                                              'nodes': 0, 'depth': 0, 'nps': 0, 'info': str(eg_move)}
                    print(f"[egtb] 使用残局库走法: {eg_move} (源: {src})")
                    return eg_move

            return self.iterative_deepening_search_single()
        finally:
            # 无论是否超时，都必须清掉本次搜索的有效时间预算，
            # 避免污染下一次搜索（尤其是直接调用 alpha_beta 的诊断路径）。
            self._effective_time_limit = None

    def iterative_deepening_search_single(self):
        """单线程迭代加深搜索（带开局库支持、智能时间管理和Aspiration Windows）"""

        # Increment search generation for TT aging
        self.search_generation += 1

        # Adaptive time management - adjust thinking time based on position
        adaptive_time = self.get_adaptive_thinking_time()
        # 让内部节点也遵守同样的预算（原来只有根节点检查自适应时间，
        # alpha_beta/quiescence 仍用固定 thinking_time，导致预算被突破）
        self._effective_time_limit = adaptive_time

        self.nodes_searched = 0
        start_time = time.time()

        # 清空killer moves和history table
        self.killer_moves = [[None, None] for _ in range(self.max_ply)]
        # 保留部分history信息，但衰减
        for key in self.history_table:
            self.history_table[key] //= 8

        moves = self.get_all_legal_moves()
        if not moves:
            self._effective_time_limit = None
            return None

        best_move = None
        best_value = float('-inf') if self.current_player == 'red' else float('inf')

        # 走法排序
        moves = self.order_moves(moves, 0)

        for depth in range(1, self.search_depth + 1):
            # Aspiration Windows: Use narrow window around previous best score
            if depth == 1:
                # First iteration: full window
                aspiration_alpha = float('-inf')
                aspiration_beta = float('inf')
                use_aspiration = False
            else:
                # Use aspiration window around previous best value
                window = 50  # About half a pawn in our scale
                if self.current_player == 'red':
                    aspiration_alpha = best_value - window
                    aspiration_beta = best_value + window
                else:
                    aspiration_alpha = best_value - window
                    aspiration_beta = best_value + window
                use_aspiration = True

            # Search with aspiration window (may need to re-search)
            search_failed = False
            for attempt in range(2):  # Max 2 attempts (aspiration, then full)
                current_best_move = None
                current_best_value = float('-inf') if self.current_player == 'red' else float('inf')

                for move in moves:
                    start_row, start_col, end_row, end_col = move
                    captured_piece = self.make_move(start_row, start_col, end_row, end_col, track_check=False)

                    eval_score = self.alpha_beta_search(
                        depth - 1,
                        aspiration_alpha,
                        aspiration_beta,
                        self.current_player == 'red',
                        start_time,
                        ply=1,
                        allow_null_move=True,
                        extensions=0
                    )

                    self.undo_move(start_row, start_col, end_row, end_col, captured_piece)

                    # 时间检查 - 使用自适应时间（stop_requested 供 UCI stop 中断）
                    if self.stop_requested or time.time() - start_time > adaptive_time:
                        self._effective_time_limit = None
                        return best_move or moves[0]

                    if (self.current_player == 'red' and eval_score > current_best_value) or \
                            (self.current_player == 'black' and eval_score < current_best_value):
                        current_best_value = eval_score
                        current_best_move = move

                # Check if aspiration window failed
                if use_aspiration and attempt == 0:
                    # Check if we need to re-search with full window
                    if (self.current_player == 'red' and
                        (current_best_value <= aspiration_alpha or current_best_value >= aspiration_beta)):
                        # Aspiration window failed for red, re-search with full window
                        aspiration_alpha = float('-inf')
                        aspiration_beta = float('inf')
                        search_failed = True
                        continue
                    elif (self.current_player == 'black' and
                          (current_best_value <= aspiration_alpha or current_best_value >= aspiration_beta)):
                        # Aspiration window failed for black, re-search with full window
                        aspiration_alpha = float('-inf')
                        aspiration_beta = float('inf')
                        search_failed = True
                        continue

                # Success or final attempt
                break

            if current_best_move:
                best_move = current_best_move
                best_value = current_best_value

            # 时间检查 - 使用自适应时间（stop_requested 供 UCI stop 中断）
            if self.stop_requested or time.time() - start_time > adaptive_time:
                break

        search_time = time.time() - start_time
        nps = int(self.nodes_searched / search_time) if search_time > 0 else 0
        self.last_search_stats = {'source': 'search', 'time': round(search_time, 2),
                                  'nodes': self.nodes_searched, 'depth': depth,
                                  'nps': nps, 'score': best_value}
        print(f"AI思考时间: {search_time:.2f}秒")
        print(f"搜索深度: {depth}, 搜索节点: {self.nodes_searched}")
        print(f"评估分数: {best_value}")

        self._effective_time_limit = None
        return best_move

    def order_moves(self, moves, ply=0, tt_move=None):
        """走法排序：使用TT move、MVV-LVA、Killer moves和History heuristic"""
        scored_moves = []
        piece_values = self.get_piece_values()

        for move in moves:
            score = 0

            # TT move (transposition table) gets highest priority
            if tt_move and move == tt_move:
                score = 1000000  # Extremely high score to ensure it's tried first
            else:
                start_row, start_col, end_row, end_col = move
                start_piece = self.board[start_row][start_col]
                target_piece = self.board[end_row][end_col]

                # 1. 吃子走法优先 - MVV-LVA (Most Valuable Victim - Least Valuable Attacker)
                if target_piece != '.':
                    victim_value = piece_values.get(target_piece.upper(), 0)
                    attacker_value = piece_values.get(start_piece.upper(), 0)
                    # 优先吃价值高的棋子，用价值低的棋子吃
                    score += 10000 + victim_value - attacker_value / 100

                # 2. Killer moves - 非吃子但导致剪枝的走法
                else:
                    if ply < self.max_ply:
                        if move == self.killer_moves[ply][0]:
                            score += 9000  # 第一个killer move
                        elif move == self.killer_moves[ply][1]:
                            score += 8000  # 第二个killer move

                    # 3. History heuristic - 历史上表现好的走法
                    move_key = (start_row, start_col, end_row, end_col)
                    if move_key in self.history_table:
                        score += self.history_table[move_key]

            scored_moves.append((score, move))

        # 按分数降序排序
        scored_moves.sort(key=lambda x: x[0], reverse=True)
        return [move for _, move in scored_moves]

    def update_killer_moves(self, move, ply):
        """更新killer moves表"""
        if ply >= self.max_ply:
            return

        # 如果这个走法不是吃子且不在killer moves中
        target_piece = self.board[move[2]][move[3]]
        if target_piece == '.':
            # 如果不是第一个killer move，则更新
            if move != self.killer_moves[ply][0]:
                # 将第一个killer move移到第二个位置
                self.killer_moves[ply][1] = self.killer_moves[ply][0]
                # 将新的走法设为第一个killer move
                self.killer_moves[ply][0] = move

    def update_history(self, move, depth):
        """更新history heuristic表"""
        move_key = (move[0], move[1], move[2], move[3])
        if move_key not in self.history_table:
            self.history_table[move_key] = 0
        # 深度越大，权重越高
        self.history_table[move_key] += depth * depth

    def get_capture_moves(self):
        """获取所有吃子走法（用于quiescence搜索）"""
        moves = []
        player = self.current_player

        for i in range(10):
            for j in range(9):
                piece = self.board[i][j]
                if (player == 'red' and piece.isupper()) or (player == 'black' and piece.islower()):
                    piece_moves = self.get_piece_moves(i, j)
                    # 只保留吃子走法
                    for move in piece_moves:
                        if self.board[move[2]][move[3]] != '.':
                            moves.append(move)

        # 过滤掉导致被将军的走法
        if self.is_in_check(player):
            valid_moves = []
            for move in moves:
                start_row, start_col, end_row, end_col = move
                captured_piece = self.make_move(start_row, start_col, end_row, end_col, track_check=False)
                if not self.is_in_check(player):
                    valid_moves.append(move)
                self.undo_move(start_row, start_col, end_row, end_col, captured_piece)
            return valid_moves

        return moves

    def quiescence_search(self, alpha, beta, depth, start_time, maximizing_player=True):
        """静态搜索 - 与 alpha_beta_search 同一套绝对分数口径（红正黑负）。

        注意：evaluate_board 返回的是"红方视角"分数，因此不能再用
        negamax 的 -score/-beta/-alpha 取负写法，否则黑方节点会符号反转。
        """
        self.nodes_searched += 1

        # 时间检查（遵守自适应时间预算；stop_requested 供 UCI stop 中断）
        limit = self._effective_time_limit or self.thinking_time
        if self.stop_requested or time.time() - start_time > limit:
            return self.evaluate_board()

        # 深度限制
        if depth >= self.max_quiescence_depth:
            return self.evaluate_board()

        # 被将军时不能站着评估（局面不平静），必须搜索全部应将走法
        in_check = self.is_in_check(self.current_player)
        stand_pat = None
        if not in_check:
            stand_pat = self.evaluate_board()
            if maximizing_player:
                if stand_pat >= beta:
                    return beta
                if stand_pat > alpha:
                    alpha = stand_pat
            else:
                if stand_pat <= alpha:
                    return alpha
                if stand_pat < beta:
                    beta = stand_pat

        # 被将军时搜全部合法应将，否则只搜吃子
        capture_moves = self.get_all_legal_moves() if in_check else self.get_capture_moves()

        if not capture_moves:
            if in_check:
                # 与 alpha_beta_search 同源量级; 开关关闭时保留旧绝对值
                mv = self.MATE_VALUE if self.use_mate_score else 100000
                return (-mv + depth) if maximizing_player else (mv - depth)
            return stand_pat

        # 排序吃子走法
        capture_moves = self.order_moves(capture_moves, depth)

        # Delta pruning：非将军节点，若 stand_pat + 吃子收益 + 余量 都无法越过
        # 当前 alpha/beta，则该吃子不可能改善结果，直接跳过。绝对分口径下：
        # 极大方(红)分数越高越好，极小方(黑)分数越低越好。
        # 注意被将军时 stand_pat 为 None 且必须搜全部应将，故跳过剪枝。
        delta_margin = self.delta_margin
        wide_window = (beta - alpha) >= self.delta_min_window
        piece_values = self.get_piece_values()

        for move in capture_moves:
            start_row, start_col, end_row, end_col = move
            if (self.use_delta_pruning and wide_window and not in_check
                    and stand_pat is not None):
                victim = self.board[end_row][end_col]
                victim_value = piece_values.get(victim.upper(), 0) if victim != '.' else 0
                if maximizing_player:
                    if stand_pat + victim_value + delta_margin < alpha:
                        continue
                else:
                    if stand_pat - victim_value - delta_margin > beta:
                        continue
            captured_piece = self.make_move(start_row, start_col, end_row, end_col, track_check=False)

            # 轮到对方，maximizing 取反；alpha/beta 不取负（绝对分数口径）
            score = self.quiescence_search(
                alpha, beta, depth + 1, start_time, not maximizing_player
            )

            self.undo_move(start_row, start_col, end_row, end_col, captured_piece)

            if maximizing_player:
                if score >= beta:
                    return beta
                if score > alpha:
                    alpha = score
            else:
                if score <= alpha:
                    return alpha
                if score < beta:
                    beta = score

        return alpha if maximizing_player else beta

    def evaluate_board(self):
        """评估棋盘状态（增强版：包含子力、位置、机动性、王安全、威胁检测等）

        注意：将死判定由搜索层（alpha_beta_search / quiescence）负责，
        这里不再重复做两次全量合法走法生成 —— 那是叶子节点最大的浪费。
        """
        score = 0

        # 1. 子力价值和位置价值评估
        piece_values = self.get_piece_values()

        for i in range(10):
            for j in range(9):
                piece = self.board[i][j]
                if piece != '.':
                    value = piece_values.get(piece.upper(), 0)
                    pos_value = self.get_position_value(piece, i, j)

                    if piece.isupper():  # 红方
                        score += value + pos_value
                    else:  # 黑方
                        score -= value + pos_value

        # 2. 机动性评估 - 合法走法数量。实测该项占叶子开销约 38%、贡献仅 ~60 分，
        # 默认关闭（用开关保留以便 A/B）。开启时需两次全量合法走法生成。
        if self.use_mobility_eval:
            red_mobility = len(self.get_all_legal_moves('red'))
            black_mobility = len(self.get_all_legal_moves('black'))
            score += (red_mobility - black_mobility) * 5

        # 3. 王的安全性评估
        score += self.evaluate_king_safety('red')
        score -= self.evaluate_king_safety('black')

        # attack map 只构建一次, 供中心控制与威胁项共用 (原来 threats 内部构建一次)
        attack_maps = self._build_attack_maps()

        # 4. 控制中心和河界的评估
        score += self.evaluate_center_control(attack_maps)

        # 5. 威胁评估 - 检测悬挂棋子和受攻击的棋子
        score += self.evaluate_threats(attack_maps)

        # 6. 车的位置评估 - 开放线和半开放线
        score += self.evaluate_rook_positioning()

        # 7. 双车联通评估
        score += self.evaluate_connected_rooks()

        # 8. 通路兵评估
        score += self.evaluate_passed_pawns()

        # 9. 子力配合评估
        score += self.evaluate_piece_coordination()

        # 10. 兵型结构评估
        score += self.evaluate_pawn_structure()

        return score

    def _build_attack_maps(self):
        """一次遍历生成红黑双方的攻击格集合。

        原实现里 is_under_attack / is_defended 对每个棋子都重扫全盘并
        生成对方所有走法，复杂度 O(棋子数^2)，是最大的性能瓶颈。
        改为一次生成 attack map 后 O(1) 查询，语义保持一致。
        """
        red_attacks = set()
        black_attacks = set()
        for i in range(10):
            for j in range(9):
                piece = self.board[i][j]
                if piece == '.':
                    continue
                targets = red_attacks if piece.isupper() else black_attacks
                for mv in self.get_piece_moves(i, j):
                    targets.add((mv[2], mv[3]))

        # 将帅照面：原 is_under_attack 对王有特殊处理，这里补上
        red_king = black_king = None
        for i in range(10):
            for j in range(9):
                if self.board[i][j] == 'K':
                    red_king = (i, j)
                elif self.board[i][j] == 'k':
                    black_king = (i, j)
        if red_king and black_king and red_king[1] == black_king[1]:
            col = red_king[1]
            lo, hi = sorted((red_king[0], black_king[0]))
            if all(self.board[r][col] == '.' for r in range(lo + 1, hi)):
                red_attacks.add(black_king)
                black_attacks.add(red_king)

        return red_attacks, black_attacks

    def evaluate_threats(self, attack_maps=None):
        """评估威胁 - 悬挂棋子和受攻击的棋子（攻击地图优化版）"""
        score = 0
        piece_values = self.get_piece_values()
        if attack_maps is None:
            attack_maps = self._build_attack_maps()
        red_attacks, black_attacks = attack_maps

        hang_scale = 0.3 if self.threat_hanging_scale is None else self.threat_hanging_scale
        for i in range(10):
            for j in range(9):
                piece = self.board[i][j]
                if piece == '.':
                    continue
                player = 'red' if piece.isupper() else 'black'
                # 将帅被“将军”应由搜索层的将死判定处理，静态评估里不再罚巨额分
                if self.threat_exclude_king and piece.upper() == 'K':
                    continue
                piece_value = piece_values.get(piece.upper(), 0)

                attacked = ((i, j) in black_attacks) if player == 'red' else ((i, j) in red_attacks)
                if attacked:
                    defended = ((i, j) in red_attacks) if player == 'red' else ((i, j) in black_attacks)
                    penalty = piece_value * (0.05 if defended else hang_scale)
                    score -= penalty if player == 'red' else -penalty

        return score

    def evaluate_king_safety(self, player):
        """评估王的安全性"""
        safety_score = 0
        king_symbol = 'K' if player == 'red' else 'k'

        # 找到王的位置
        king_pos = None
        for i in range(10):
            for j in range(9):
                if self.board[i][j] == king_symbol:
                    king_pos = (i, j)
                    break
            if king_pos:
                break

        if not king_pos:
            return 0

        king_row, king_col = king_pos

        # 统计王周围的己方棋子（保护者）
        defenders = 0
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                nr, nc = king_row + dr, king_col + dc
                if 0 <= nr < 10 and 0 <= nc < 9:
                    piece = self.board[nr][nc]
                    if piece != '.':
                        if (player == 'red' and piece.isupper()) or \
                           (player == 'black' and piece.islower()):
                            defenders += 1

        safety_score += defenders * 15

        # 将帅越靠本方底线越安全。defenders*15 随将帅前移虚高(前方士象进入邻格),
        # 曾诱发引擎为加分无故"上将"暴露主帅。按离本方底线行数扣分抵消该假收益。
        # 红底线 row0, 黑底线 row9。
        advance = king_row if player == 'red' else (9 - king_row)
        safety_score -= advance * 20

        # 被将军的 -200 静态惩罚已移除：将军应由搜索层将死判定/quiescence 应将处理，
        # 静态评估重复罚分会使叶子分数在"被将/未被将"间跳变误导搜索，且多一次 is_in_check
        # 开销。开关供 A/B 对照。
        if self.use_king_check_penalty and self.is_in_check(player):
            safety_score -= 200

        return safety_score

    def evaluate_center_control(self, attack_maps=None):
        """评估中心和关键位置的控制。

        旧实现只查 row4/5 × col3/4/5 六个格子的"占据", 但中局这些格子
        占用率仅约 6%, 导致该项几乎恒为 0、不提供任何信息。
        改为统计双方"攻击到"河界中路格子的数量(控制), 复用同一份 attack map,
        不增加叶子开销。开关关闭时保留旧行为供 A/B 对照。
        """
        score = 0
        river_rows = [4, 5]
        center_cols = [3, 4, 5]

        if not self.use_control_eval:
            for row in river_rows:
                for col in center_cols:
                    piece = self.board[row][col]
                    if piece != '.':
                        score += 5 if piece.isupper() else -5
            return score

        if attack_maps is None:
            attack_maps = self._build_attack_maps()
        red_attacks, black_attacks = attack_maps

        for row in river_rows:
            for col in center_cols:
                if (row, col) in red_attacks:
                    score += 3
                if (row, col) in black_attacks:
                    score -= 3
                # 己方棋子实际占据中路再加一点, 但比值小, 避免重复位置表
                piece = self.board[row][col]
                if piece != '.':
                    score += 2 if piece.isupper() else -2

        return score

    def evaluate_rook_positioning(self):
        """评估车的位置 - 开放线和半开放线"""
        score = 0

        # 检查每一列的开放程度
        for col in range(9):
            has_red_pawn = False
            has_black_pawn = False
            red_rooks = []
            black_rooks = []

            # 检查这一列上的棋子
            for row in range(10):
                piece = self.board[row][col]
                if piece == 'P':
                    has_red_pawn = True
                elif piece == 'p':
                    has_black_pawn = True
                elif piece == 'R':
                    red_rooks.append(row)
                elif piece == 'r':
                    black_rooks.append(row)

            # 评估红方车
            for row in red_rooks:
                if not has_red_pawn and not has_black_pawn:
                    score += 25  # 开放线 (最好)
                elif not has_red_pawn:
                    score += 15  # 半开放线
                # else: 封闭线，无奖励

            # 评估黑方车
            for row in black_rooks:
                if not has_red_pawn and not has_black_pawn:
                    score -= 25  # 开放线
                elif not has_black_pawn:
                    score -= 15  # 半开放线

        return score

    def evaluate_connected_rooks(self):
        """评估双车联通"""
        score = 0

        # 找到所有车的位置
        red_rooks = []
        black_rooks = []

        for i in range(10):
            for j in range(9):
                if self.board[i][j] == 'R':
                    red_rooks.append((i, j))
                elif self.board[i][j] == 'r':
                    black_rooks.append((i, j))

        # 检查红方双车是否联通
        if len(red_rooks) == 2:
            r1, r2 = red_rooks
            # 同一行或同一列
            if r1[0] == r2[0]:  # 同一行
                # 检查之间是否有棋子
                start_col = min(r1[1], r2[1]) + 1
                end_col = max(r1[1], r2[1])
                connected = True
                for col in range(start_col, end_col):
                    if self.board[r1[0]][col] != '.':
                        connected = False
                        break
                if connected:
                    score += 30  # 双车联通奖励
            elif r1[1] == r2[1]:  # 同一列
                start_row = min(r1[0], r2[0]) + 1
                end_row = max(r1[0], r2[0])
                connected = True
                for row in range(start_row, end_row):
                    if self.board[row][r1[1]] != '.':
                        connected = False
                        break
                if connected:
                    score += 30

        # 检查黑方双车是否联通
        if len(black_rooks) == 2:
            r1, r2 = black_rooks
            if r1[0] == r2[0]:  # 同一行
                start_col = min(r1[1], r2[1]) + 1
                end_col = max(r1[1], r2[1])
                connected = True
                for col in range(start_col, end_col):
                    if self.board[r1[0]][col] != '.':
                        connected = False
                        break
                if connected:
                    score -= 30
            elif r1[1] == r2[1]:  # 同一列
                start_row = min(r1[0], r2[0]) + 1
                end_row = max(r1[0], r2[0])
                connected = True
                for row in range(start_row, end_row):
                    if self.board[row][r1[1]] != '.':
                        connected = False
                        break
                if connected:
                    score -= 30

        return score

    def evaluate_passed_pawns(self):
        """评估通路兵（过河后无阻挡的兵）"""
        score = 0

        for row in range(10):
            for col in range(9):
                piece = self.board[row][col]

                if piece == 'P':  # 红兵
                    # 检查是否过河
                    if row >= 5:
                        # 检查前方及两侧是否有黑兵阻挡
                        is_passed = True
                        for check_col in [col - 1, col, col + 1]:
                            if 0 <= check_col < 9:
                                for check_row in range(row + 1, 10):
                                    if self.board[check_row][check_col] == 'p':
                                        is_passed = False
                                        break
                            if not is_passed:
                                break

                        if is_passed:
                            # 越深入越值钱
                            bonus = 15 + (row - 5) * 5
                            score += bonus

                elif piece == 'p':  # 黑兵
                    # 检查是否过河
                    if row <= 4:
                        # 检查前方及两侧是否有红兵阻挡
                        is_passed = True
                        for check_col in [col - 1, col, col + 1]:
                            if 0 <= check_col < 9:
                                for check_row in range(0, row):
                                    if self.board[check_row][check_col] == 'P':
                                        is_passed = False
                                        break
                            if not is_passed:
                                break

                        if is_passed:
                            # 越深入越值钱
                            bonus = 15 + (4 - row) * 5
                            score -= bonus

        return score

    def evaluate_piece_coordination(self):
        """评估子力配合"""
        score = 0

        # 找到马和炮的位置
        red_horses = []
        red_cannons = []
        black_horses = []
        black_cannons = []

        for i in range(10):
            for j in range(9):
                piece = self.board[i][j]
                if piece == 'H':
                    red_horses.append((i, j))
                elif piece == 'C':
                    red_cannons.append((i, j))
                elif piece == 'h':
                    black_horses.append((i, j))
                elif piece == 'c':
                    black_cannons.append((i, j))

        # 马炮配合：马和炮距离较近时有奖励
        for horse in red_horses:
            for cannon in red_cannons:
                distance = abs(horse[0] - cannon[0]) + abs(horse[1] - cannon[1])
                if distance <= 3:  # 马和炮比较近
                    score += 10

        for horse in black_horses:
            for cannon in black_cannons:
                distance = abs(horse[0] - cannon[0]) + abs(horse[1] - cannon[1])
                if distance <= 3:
                    score -= 10

        return score

    def evaluate_pawn_structure(self):
        """评估兵型结构"""
        score = 0

        # 检查叠兵（同一列上有多个己方兵）
        for col in range(9):
            red_pawns = 0
            black_pawns = 0

            for row in range(10):
                if self.board[row][col] == 'P':
                    red_pawns += 1
                elif self.board[row][col] == 'p':
                    black_pawns += 1

            # 叠兵惩罚
            if red_pawns >= 2:
                score -= 15 * (red_pawns - 1)
            if black_pawns >= 2:
                score += 15 * (black_pawns - 1)

        # 检查孤兵（两侧没有己方兵）
        for row in range(10):
            for col in range(9):
                piece = self.board[row][col]

                if piece == 'P':  # 红兵
                    has_neighbor = False
                    for check_col in [col - 1, col + 1]:
                        if 0 <= check_col < 9:
                            for check_row in range(10):
                                if self.board[check_row][check_col] == 'P':
                                    has_neighbor = True
                                    break
                        if has_neighbor:
                            break

                    if not has_neighbor:
                        score -= 8  # 孤兵惩罚

                elif piece == 'p':  # 黑兵
                    has_neighbor = False
                    for check_col in [col - 1, col + 1]:
                        if 0 <= check_col < 9:
                            for check_row in range(10):
                                if self.board[check_row][check_col] == 'p':
                                    has_neighbor = True
                                    break
                        if has_neighbor:
                            break

                    if not has_neighbor:
                        score += 8

        return score

    def get_piece_values(self):
        """棋子价值表"""
        return {
            'K': 10000, 'k': 10000,  # 将/帅
            'R': 500, 'r': 500,  # 车
            'H': 300, 'h': 300,  # 马
            'C': 300, 'c': 300,  # 砲/炮
            'B': 200, 'b': 200,  # 相/象
            'A': 200, 'a': 200,  # 仕/士
            'P': 100, 'p': 100  # 兵/卒
        }

    def get_position_value(self, piece, row, col):
        """获取棋子的位置价值"""
        position_tables = self.get_position_tables()
        piece_type = piece.upper()

        if piece_type in position_tables:
            table = position_tables[piece_type]
            if piece.isupper():  # 红方
                return table[row][col]
            else:  # 黑方
                # 黑方位置表是红方的垂直镜像（不镜像列，因为棋盘左右对称）
                return table[9 - row][col]

        return 0

    def get_position_tables(self):
        """返回所有棋子的位置价值表（模块级缓存，避免每次重建）"""
        global _POSITION_TABLES_CACHE
        if _POSITION_TABLES_CACHE is None:
            _POSITION_TABLES_CACHE = {
                'P': self.get_pawn_position_table(),
                'H': self.get_knight_position_table(),
                'C': self.get_cannon_position_table(),
                'R': self.get_rook_position_table(),
                'A': self.get_advisor_position_table(),
                'B': self.get_bishop_position_table(),
                'K': self.get_king_position_table()
            }
        return _POSITION_TABLES_CACHE

    def get_pawn_position_table(self):
        """兵/卒的位置价值表（改进版）"""
        # 红兵位置价值 - 鼓励过河和推进，但要更渐进
        return [
            [0, 0, 0, 0, 0, 0, 0, 0, 0],  # 起始行（不应该在这里）
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [5, 0, 5, 0, 8, 0, 5, 0, 5],   # 起始位置，中兵稍好
            [8, 0, 10, 0, 15, 0, 10, 0, 8],  # 过河前一步
            [12, 0, 15, 0, 20, 0, 15, 0, 12],  # 刚过河（重要）
            [15, 5, 18, 10, 25, 10, 18, 5, 15],  # 过河后，侧翼兵也有价值
            [18, 10, 22, 15, 28, 15, 22, 10, 18],  # 深入敌阵
            [20, 12, 25, 18, 30, 18, 25, 12, 20],  # 非常威胁
            [22, 15, 28, 20, 35, 20, 28, 15, 22]   # 九宫前，极度危险
        ]

    def get_knight_position_table(self):
        """马的位置价值表（改进版）"""
        # 马在中心和河界区域价值更高，边路较差
        return [
            [-20, -10, -5, -5, -5, -5, -5, -10, -20],  # 底线，马脚受限
            [-10, 0, 5, 8, 8, 8, 5, 0, -10],
            [-5, 5, 10, 12, 12, 12, 10, 5, -5],
            [-5, 8, 12, 15, 15, 15, 12, 8, -5],  # 河界前，很好的位置
            [-5, 10, 15, 18, 18, 18, 15, 10, -5],  # 河界，最佳位置
            [-5, 10, 15, 18, 18, 18, 15, 10, -5],  # 河界，最佳位置
            [-5, 8, 12, 15, 15, 15, 12, 8, -5],
            [-5, 5, 8, 10, 10, 10, 8, 5, -5],
            [-10, 0, 5, 5, 5, 5, 5, 0, -10],
            [-20, -10, -5, -5, -5, -5, -5, -10, -20]
        ]

    def get_cannon_position_table(self):
        """炮的位置价值表（改进版）"""
        # 炮在河界和对方阵地价值更高，中路炮更有威胁
        return [
            [0, 0, 2, 3, 3, 3, 2, 0, 0],    # 底线，不太理想
            [0, 2, 5, 6, 6, 6, 5, 2, 0],    # 第二线，稍好
            [2, 5, 8, 10, 10, 10, 8, 5, 2],   # 炮二平五位置
            [5, 8, 10, 12, 12, 12, 10, 8, 5],  # 接近河界
            [8, 10, 12, 15, 15, 15, 12, 10, 8],  # 河界，巡河炮位置
            [8, 10, 12, 15, 15, 15, 12, 10, 8],  # 过河，很好的位置
            [5, 8, 10, 12, 12, 12, 10, 8, 5],   # 敌阵，威胁性强
            [3, 5, 8, 10, 10, 10, 8, 5, 3],    # 深入敌阵
            [0, 3, 5, 6, 6, 6, 5, 3, 0],      # 接近底线
            [0, 0, 3, 5, 5, 5, 3, 0, 0]       # 敌方底线
        ]

    def get_rook_position_table(self):
        """车的位置价值表（改进版）"""
        # 车在敌方阵地和第七线价值最高
        return [
            [0, 0, 2, 3, 3, 3, 2, 0, 0],      # 底线
            [3, 5, 6, 8, 8, 8, 6, 5, 3],      # 第二线，较活跃
            [3, 5, 6, 8, 8, 8, 6, 5, 3],
            [5, 6, 8, 10, 10, 10, 8, 6, 5],
            [5, 8, 10, 12, 12, 12, 10, 8, 5],   # 河界
            [8, 10, 12, 15, 15, 15, 12, 10, 8],  # 过河
            [10, 12, 15, 18, 18, 18, 15, 12, 10], # 敌阵
            [15, 18, 20, 22, 22, 22, 20, 18, 15], # 第七线，非常强
            [15, 18, 20, 22, 22, 22, 20, 18, 15], # 接近底线
            [10, 12, 15, 18, 18, 18, 15, 12, 10]  # 敌方底线
        ]

    def get_advisor_position_table(self):
        """仕/士的位置价值表 (红方视角: 九宫在 row 0-2)"""
        # 士在九宫中心价值更高
        return [
            [0, 0, 0, 10, 0, 10, 0, 0, 0],
            [0, 0, 0, 0, 15, 0, 0, 0, 0],
            [0, 0, 0, 10, 0, 10, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0]
        ]

    def get_bishop_position_table(self):
        """相/象的位置价值表 (红方视角: 己方阵地 row 0-4)"""
        # 象在己方阵地价值稳定
        return [
            [0, 0, 5, 0, 0, 0, 5, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [5, 0, 0, 0, 10, 0, 0, 0, 5],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 5, 0, 0, 0, 5, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0]
        ]

    def get_king_position_table(self):
        """将/帅的位置价值表 (红方视角: 九宫在 row 0-2)。

        将帅越靠底线越安全: row0(本方底线)>row1>row2。
        切勿让 row1 高于 row0, 否则引擎会为加分无故'上将'暴露主帅。
        """
        return [
            [0, 0, 0, 10, 15, 10, 0, 0, 0],
            [0, 0, 0, 5, 10, 5, 0, 0, 0],
            [0, 0, 0, 0, 5, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0]
        ]

    def make_move(self, start_row, start_col, end_row, end_col, track_check=True):
        """执行走法。track_check=False 时将军信息记 None（搜索热路径跳过 is_in_check 提速）。"""
        # 记录走法前的zobrist key用于重复检测
        zobrist_key = self.get_zobrist_key()
        self.position_history.append(zobrist_key)

        mover = self.current_player  # 走子方（切换前）
        moving_piece = self.board[start_row][start_col]
        captured_piece = self.board[end_row][end_col]
        self.board[end_row][end_col] = self.board[start_row][start_col]
        self.board[start_row][start_col] = '.'

        # 自然限着计数：吃子或兵/卒前进会重置，否则累加。保存旧值供撤销回退。
        self.halfmove_history.append(self.halfmove_clock)
        if captured_piece != '.' or moving_piece.upper() == 'P':
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1

        self.move_history.append((start_row, start_col, end_row, end_col, captured_piece))
        self.current_player = 'black' if self.current_player == 'red' else 'red'
        self.last_move = (start_row, start_col, end_row, end_col)  # 记录最后一次移动

        # 记录本步是否将军对方；搜索热路径用占位 None 跳过昂贵的 is_in_check
        gave_check = self.is_in_check(self.current_player) if track_check else None
        self.check_history.append((mover, gave_check))

        return captured_piece

    def undo_move(self, start_row, start_col, end_row, end_col, captured_piece):
        """撤销走法"""
        self.board[start_row][start_col] = self.board[end_row][end_col]
        self.board[end_row][end_col] = captured_piece
        self.move_history.pop()
        self.current_player = 'black' if self.current_player == 'red' else 'red'

        # 回退自然限着计数
        if self.halfmove_history:
            self.halfmove_clock = self.halfmove_history.pop()

        # 移除位置历史
        if self.position_history:
            self.position_history.pop()
        # 回退长将检测历史
        if self.check_history:
            self.check_history.pop()

        # 更新last_move为上一次移动
        if self.move_history:
            last_move = self.move_history[-1]
            self.last_move = (last_move[0], last_move[1], last_move[2], last_move[3])
        else:
            self.last_move = None

    def is_game_over(self):
        """检查游戏是否结束：将死 或 三次重复 或 自然限着。"""
        return (self.is_checkmate('red') or self.is_checkmate('black')
                or self.is_draw_by_repetition(3) or self.is_draw_by_60_moves())

    def is_checkmate(self, player):
        """检查是否被将死"""
        moves = self.get_all_legal_moves(player)
        return len(moves) == 0

    @property
    def game_over(self):
        """终局状态：由当前局面实时推导，避免与落子/悔棋不同步。"""
        return self.is_game_over()

    @property
    def winner(self):
        """胜负和：将死 > 长将判负 > 重复/自然限着和棋。"""
        if self.is_checkmate('red'):
            return 'black'
        if self.is_checkmate('black'):
            return 'red'
        # 长将方判负：重复周期内一方连续将军，则对方获胜
        loser = self.get_long_check_loser()
        if loser is not None:
            return 'black' if loser == 'red' else 'red'
        if self.is_draw_by_repetition(3) or self.is_draw_by_60_moves():
            return 'draw'
        return None

    def is_draw_by_repetition(self, threshold=3):
        """同一局面出现 threshold 次判和（position_history 记录走子前的局面）。"""
        if not self.position_history:
            return False
        current = self.get_zobrist_key()
        count = self.position_history.count(current)
        # 当前局面尚未记入历史，故出现次数 +1
        return count + 1 >= threshold

    def is_draw_by_60_moves(self):
        """自然限着判和：连续 natural_limit_plies 半回合无吃子且无兵/卒前进。"""
        return self.halfmove_clock >= self.natural_limit_plies

    def get_long_check_loser(self):
        """长将判负：在重复周期内若某一方每步都将军对方，返回该方（负方）；否则 None。

        position_history 记录走子前的局面，check_history[i] 对应第 i 步的
        (走子方, 是否将军)。当前局面重复出现时，取最近两次出现的下标区间为
        一个循环周期，检查该周期内某方是否步步将军（长将）。
        """
        if len(self.position_history) < 4 or len(self.check_history) < 4:
            return None
        current = self.get_zobrist_key()
        # 当前局面在“走子前”历史里出现的位置（重复周期起点）
        positions = [i for i, k in enumerate(self.position_history) if k == current]
        if not positions:
            return None
        start = positions[-1]  # 最近一次出现 = 本周期起点
        cycle = self.check_history[start:]
        if len(cycle) < 4:  # 周期太短不足以构成连续将军
            return None
        for side in ('red', 'black'):
            side_gaves = [gave for mover, gave in cycle if mover == side]
            # 该方在本周期至少有 2 步，且每步都在将军
            if len(side_gaves) >= 2 and all(side_gaves):
                return side
        return None

    def handle_command(self, command):
        """处理命令行输入"""
        parts = command.strip().split()
        if not parts:
            return False

        cmd = parts[0].lower()

        if cmd in ['quit', 'exit']:
            return True

        elif cmd == 'restart':
            self.__init__()
            print("游戏已重新开始")

        elif cmd == 'save' and len(parts) > 1:
            self.save_game(parts[1])

        elif cmd == 'load' and len(parts) > 1:
            self.load_game(parts[1])

        elif cmd == 'mode' and len(parts) > 1:
            if parts[1] in ['chinese', 'english']:
                self.display_mode = parts[1]
                print(f"显示模式已切换为: {parts[1]}")
            else:
                print("无效的显示模式")

        elif cmd == 'eval':
            score = self.evaluate_board()
            print(f"当前局面评估: {score}")

        elif cmd == 'moves':
            moves = self.get_all_legal_moves()
            print(f"合法走法数量: {len(moves)}")
            for i, move in enumerate(moves[:10]):  # 只显示前10个
                print(f"{i + 1}: {move}")
            if len(moves) > 10:
                print("...")

        elif cmd == 'ai':
            if len(parts) > 1:
                if parts[1] == 'on':
                    self.ai_enabled = True
                    print("AI已启用")
                elif parts[1] == 'off':
                    self.ai_enabled = False
                    print("AI已禁用")
                elif len(parts) > 2 and parts[1] == 'vs' and parts[2] == 'ai':
                    self.ai_vs_ai_mode()
                else:
                    print("无效AI命令，用法: ai on|off|vs ai")

        elif cmd == 'depth' and len(parts) > 1:
            try:
                self.search_depth = int(parts[1])
                print(f"AI搜索深度设置为: {self.search_depth}")
            except ValueError:
                print("无效的深度值")

        elif cmd == 'time' and len(parts) > 1:
            try:
                self.thinking_time = float(parts[1])
                print(f"AI思考时间设置为: {self.thinking_time}秒")
            except ValueError:
                print("无效的时间值")

        elif cmd == 'cache':
            if len(parts) > 1:
                if parts[1] == 'on':
                    self.use_cache = True
                    print("置换表缓存已启用")
                elif parts[1] == 'off':
                    self.use_cache = False
                    self.transposition_table.clear()
                    print("置换表缓存已禁用")

        elif cmd == 'book':
            if not OPENING_BOOK_AVAILABLE:
                print("开局库不可用（opening_book.py未找到）")
            elif len(parts) > 1:
                if parts[1] == 'on':
                    self.use_opening_book = True
                    print("开局库已启用")
                elif parts[1] == 'off':
                    self.use_opening_book = False
                    print("开局库已禁用")
                elif parts[1] == 'show':
                    self.show_opening_book_moves()
            else:
                status = "启用" if self.use_opening_book else "禁用"
                print(f"开局库状态: {status}")

        elif cmd == 'help':
            self.show_help()

        else:
            # 尝试解析为走法
            try:
                if len(parts) == 4:
                    start_row, start_col, end_row, end_col = map(int, parts)
                    if self.make_human_move(start_row, start_col, end_row, end_col):
                        return False
                    else:
                        print("无效的走法")
                else:
                    print("无效命令")
            except ValueError:
                print("无效命令")

        return False

    def make_human_move(self, start_row, start_col, end_row, end_col):
        """执行人类玩家的走法"""
        # 验证走法合法性
        moves = self.get_all_legal_moves()
        if (start_row, start_col, end_row, end_col) in moves:
            self.make_move(start_row, start_col, end_row, end_col)
            return True
        return False

    def ai_vs_ai_mode(self):
        """AI对战AI模式"""
        print("开始AI对战AI模式")
        max_moves = 200  # 防止无限循环

        for move_count in range(max_moves):
            if self.is_game_over():
                break

            print(f"\n--- 第{move_count + 1}回合 ---")
            self.display_board()

            ai_move = self.iterative_deepening_search()
            if ai_move:
                start_row, start_col, end_row, end_col = ai_move
                self.make_move(start_row, start_col, end_row, end_col)
                print(f"AI走法: {start_row} {start_col} {end_row} {end_col}")
            else:
                print("无合法走法，游戏结束")
                break

            # time.sleep(1)  # 暂停一下便于观察

        self.display_board()
        if self.is_checkmate('red'):
            print("黑方胜利!")
        elif self.is_checkmate('black'):
            print("红方胜利!")
        else:
            print("和棋或达到最大回合数")

    def save_game(self, filename):
        """保存游戏"""
        try:
            with open(filename, 'wb') as f:
                game_data = {
                    'board': self.board,
                    'current_player': self.current_player,
                    'move_history': self.move_history,
                    'last_move': self.last_move,
                    'ai_enabled': self.ai_enabled,
                    'search_depth': self.search_depth,
                    'thinking_time': self.thinking_time,
                    'use_cache': self.use_cache,
                    'display_mode': self.display_mode
                }
                pickle.dump(game_data, f)
            print(f"游戏已保存到: {filename}")
        except Exception as e:
            print(f"保存失败: {e}")

    def load_game(self, filename):
        """加载游戏"""
        try:
            with open(filename, 'rb') as f:
                game_data = pickle.load(f)
                self.board = game_data['board']
                self.current_player = game_data['current_player']
                self.move_history = game_data['move_history']
                self.last_move = game_data.get('last_move')
                self.ai_enabled = game_data.get('ai_enabled', True)
                self.search_depth = game_data.get('search_depth', 3)
                self.thinking_time = game_data.get('thinking_time', 5.0)
                self.use_cache = game_data.get('use_cache', True)
                self.display_mode = game_data.get('display_mode', 'chinese')
            print(f"游戏已从 {filename} 加载")
        except Exception as e:
            print(f"加载失败: {e}")

    def show_help(self):
        """显示帮助信息"""
        help_text = """
游戏控制:
  restart        - 重新开始游戏
  quit/exit      - 退出游戏
  save <file>    - 保存游戏
  load <file>    - 加载游戏

显示控制:
  mode chinese   - 中文显示模式
  mode english   - 英文显示模式
  eval           - 显示当前评估值
  moves          - 显示所有合法走法

AI控制:
  ai on/off      - 开启/关闭AI对战
  ai vs ai       - AI对战AI模式
  depth <n>      - 设置AI搜索深度
  time <秒>      - 设置AI思考时间
  cache on/off   - 开启/关闭置换表缓存
  book on/off    - 开启/关闭开局库
  book show      - 显示当前可用的开局库走法

走法输入:
  <起始行> <起始列> <目标行> <目标列>
  示例: 7 1 0 1

帮助:
  help           - 显示此帮助信息
        """
        print(help_text)

    def show_opening_book_moves(self):
        """显示当前局面的开局库走法"""
        if not self.opening_book:
            print("开局库不可用")
            return

        if len(self.move_history) >= 10:
            print("已超出开局库范围（前10步）")
            return

        # Determine position key based on move history
        position_key = None
        if len(self.move_history) == 0:
            position_key = "start"
        elif len(self.move_history) == 1:
            last_move = self.move_history[0]
            # Check if red played central cannon
            if last_move[2] == 5 and last_move[3] in [1, 7]:
                position_key = "after_red_central_cannon_right"
        elif len(self.move_history) == 2:
            # Check if black played screen horse
            black_move = self.move_history[1]
            if black_move[0] == 9 and black_move[2] == 7:
                position_key = "after_black_screen_horse"

        if position_key:
            moves = self.opening_book.get_all_book_moves(position_key)
            if moves:
                print("\n📚 可用的开局库走法:")
                for move_info in moves:
                    print(f"  {move_info['name']}: {move_info['move']} (权重: {move_info['weight']})")
            else:
                print("该局面不在开局库中")
        else:
            print("该局面不在开局库中")

    def play(self):
        """主游戏循环"""
        print("欢迎来到命令行中国象棋AI!")
        print("输入 'help' 查看可用命令")

        while True:
            self.display_board()

            if self.is_game_over():
                if self.is_checkmate('red'):
                    print("黑方胜利!")
                else:
                    print("红方胜利!")
                break

            if self.current_player == 'red' or not self.ai_enabled:
                # 人类玩家回合
                command = input("\n请输入命令或走法: ")
                if self.handle_command(command):
                    break
            else:
                # AI回合
                print("AI思考中...")
                ai_move = self.iterative_deepening_search()
                if ai_move:
                    start_row, start_col, end_row, end_col = ai_move
                    self.make_move(start_row, start_col, end_row, end_col)
                    print(f"AI走法: {start_row} {start_col} {end_row} {end_col}")
                else:
                    print("AI无法找到合法走法")
                    break


if __name__ == "__main__":
    game = ChineseChess()
    game.play()