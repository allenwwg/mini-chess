#!/usr/bin/env python3
"""回归测试：锁定已修复的 5 类问题 + 搜索口径。运行：python test_regression.py"""
import os
import sys
import types

sys.stdout.reconfigure(errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from mini_chess import ChineseChess

FAILS = []


def check(name, cond, detail=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + ('  ' + str(detail) if detail else ''))
    if not cond:
        FAILS.append(name)


def blank(red=(0, 3), black=(9, 5)):
    """空盘 + 两位合法九宫内的将帅（不同列，避免照面）。"""
    g = ChineseChess()
    g.board = [['.' for _ in range(9)] for _ in range(10)]
    g.board[red[0]][red[1]] = 'K'
    g.board[black[0]][black[1]] = 'k'
    g.use_opening_book = False
    g.use_cache = False
    g.thinking_time = 60.0
    return g


def test_search_convention():
    print('\n--- 搜索口径 ---')
    g = blank(); g.board[4][0] = 'R'; g.board[4][4] = 'p'; g.board[8][4] = 'r'
    g.current_player = 'red'; g.search_depth = 2
    mv = g.iterative_deepening_search_single()
    check('避开被保护的兵', mv != (4, 0, 4, 4), mv)

    g = blank(); g.board[4][0] = 'R'; g.board[4][3] = 'r'
    g.current_player = 'red'; g.search_depth = 2
    mv = g.iterative_deepening_search_single()
    check('白吃无保护的车', mv == (4, 0, 4, 3), mv)

    g = blank(); g.board[4][8] = 'r'; g.board[4][4] = 'R'
    g.current_player = 'black'; g.search_depth = 2
    mv = g.iterative_deepening_search_single()
    check('黑方白吃红车', mv == (4, 8, 4, 4), mv)


def test_server_no_double_apply():
    print('\n--- 服务端不重复落子 ---')
    flask = types.ModuleType('flask')

    class Flask:
        def __init__(self, *a, **k): pass
        def route(self, *a, **k): return lambda f: f
        def run(self, *a, **k): pass

    class Req:
        json = {}

    flask.Flask = Flask
    flask.jsonify = lambda o: o
    flask.request = Req()
    sys.modules['flask'] = flask
    cors = types.ModuleType('flask_cors')
    cors.CORS = lambda *a, **k: None
    sys.modules['flask_cors'] = cors
    import chess_server as cs

    cs.game = ChineseChess()
    flask.request.json = {'start_row': 2, 'start_col': 1, 'end_row': 5, 'end_col': 1}
    r = cs.make_move()
    check('api/move 轮次只切一次', r['current_player'] == 'black', r['current_player'])
    check('api/move 历史不重复', len(r['move_history']) == 1, len(r['move_history']))

    cs.game.iterative_deepening_search = lambda: (5, 1, 4, 1)
    r = cs.get_ai_move()
    check('api/ai_move 轮次只切一次', r['current_player'] == 'red', r['current_player'])
    check('api/ai_move 历史不重复', len(r['move_history']) == 2, len(r['move_history']))


def test_game_state():
    print('\n--- 终局状态 ---')
    g = ChineseChess()
    check('初始未终局', g.game_over is False and g.winner is None)

    g = blank(); g.board[8][0] = 'R'; g.board[9][0] = 'R'
    check('将死判定与胜方', g.game_over is True and g.winner == 'red', (g.game_over, g.winner))
    g.board[9][0] = '.'
    check('撤销后自动回退', g.game_over is False and g.winner is None)

    g = ChineseChess()
    g.handle_command('ai vs')
    check('ai vs 不越界', True)
    g.handle_command('ai nonsense')
    check('ai nonsense 有提示不崩溃', True)


def test_repetition():
    print('\n--- 重复局面判和 ---')
    g = ChineseChess()
    check('初始非重复和', g.is_draw_by_repetition() is False)

    g = blank(); g.board[4][0] = 'R'; g.current_player = 'red'
    cycle = [(4, 0, 4, 1), (9, 5, 9, 4), (4, 1, 4, 0), (9, 4, 9, 5)]
    for mv in cycle:
        g.make_move(*mv)
    check('两轮后仍未判和', g.is_draw_by_repetition() is False)
    for mv in cycle:
        g.make_move(*mv)
    check('局面重复三次判和', g.is_draw_by_repetition() is True)
    # P0: 重复和已接入终局状态与胜方
    check('重复和纳入 game_over', g.game_over is True)
    check('重复和 winner=draw', g.winner == 'draw', g.winner)


def test_60_move_rule():
    print('\n--- 自然限着 ---')
    g = blank(); g.current_player = 'red'
    check('初始限着未触发', g.is_draw_by_60_moves() is False and g.halfmove_clock == 0)
    g.natural_limit_plies = 8
    # 车 (4,0)<->(4,1) 来回，黑将 (9,5)<->(9,4) 来回，均无吃子，每个半回合 +1；共 8 步
    for k in range(2):
        g.make_move(4, 0, 4, 1); g.make_move(9, 5, 9, 4)   # +2
        g.make_move(4, 1, 4, 0); g.make_move(9, 4, 9, 5)   # +2
    check('无吃子累加到上限判和', g.halfmove_clock == 8 and g.is_draw_by_60_moves() is True
          and g.game_over is True,
          (g.halfmove_clock, g.is_draw_by_60_moves()))
    # 撤销最后一步后回退
    g.undo_move(9, 4, 9, 5, '.')
    check('撤销后限着回退且终局解除', g.halfmove_clock == 7
          and g.is_draw_by_60_moves() is False and g.game_over is False,
          g.halfmove_clock)
    # 吃子重置计数
    g2 = blank(); g2.board[4][4] = 'p'; g2.current_player = 'red'
    g2.make_move(4, 0, 4, 4)
    check('吃子重置限着计数', g2.halfmove_clock == 0, g2.halfmove_clock)
    # 兵移动重置计数
    g3 = blank(); g3.current_player = 'red'
    g3.board[3][0] = 'P'
    g3.make_move(3, 0, 4, 0)
    check('兵移动重置限着计数', g3.halfmove_clock == 0, g3.halfmove_clock)


def test_long_check():
    print('\n--- 长将判负 ---')
    # 先用真实走子产生三次重复（保证 position_history 里的 key 与当前局面一致）
    g = blank(); g.board[4][0] = 'R'; g.current_player = 'red'
    cycle = [(4, 0, 4, 1), (9, 5, 9, 4), (4, 1, 4, 0), (9, 4, 9, 5)]
    for _ in range(2):
        for mv in cycle:
            g.make_move(*mv)
    check('长将测试局面已三次重复', g.is_draw_by_repetition() is True)
    # 覆盖 check_history 为长将模式：红方每步将军、黑方应将，重复两轮
    g.check_history = [
        ('red', True), ('black', False), ('red', True), ('black', False),
        ('red', True), ('black', False), ('red', True), ('black', False),
    ]
    loser = g.get_long_check_loser()
    check('连续将军方被判长将负', loser == 'red', loser)
    check('长将时 winner 为对方胜', g.winner == 'black', g.winner)
    # 双方都未将军的普通重复 -> 和棋，非长将
    g.check_history = [('red', False), ('black', False)] * 4
    check('无将军的重复不判长将', g.get_long_check_loser() is None)
    # 搜索层占位 None 不得误判为将军
    g.check_history = [('red', None), ('black', None)] * 4
    check('占位 None 不误判长将', g.get_long_check_loser() is None)

    # 集成：真实走子时 check_history 正确记录“将军”
    g2 = blank(); g2.board[4][0] = 'R'; g2.board[9][4] = 'k'
    g2.board[4][4] = 'r'; g2.current_player = 'red'  # 红车(4,0) 可纵向照将黑将(9,4)?
    g2.board = [['.' for _ in range(9)] for _ in range(10)]
    g2.board[0][3] = 'K'; g2.board[9][4] = 'k'; g2.board[5][4] = 'R'
    g2.current_player = 'red'
    g2.make_move(5, 4, 8, 4)  # 红车到 (8,4) 将军黑将 (9,4)
    check('真实走子记录将军=True', len(g2.check_history) == 1
          and g2.check_history[-1] == ('red', True), g2.check_history)
    g2.undo_move(5, 4, 8, 4, '.')
    check('撤销后将军历史回退', len(g2.check_history) == 0)


def test_delta_pruning():
    print('\n--- Delta pruning ---')
    g = blank(); g.board[4][0] = 'R'; g.board[4][4] = 'p'; g.board[8][4] = 'r'
    g.current_player = 'red'; g.search_depth = 3
    g.use_delta_pruning = True
    mv_on = g.iterative_deepening_search_single()
    g2 = blank(); g2.board[4][0] = 'R'; g2.board[4][4] = 'p'; g2.board[8][4] = 'r'
    g2.current_player = 'red'; g2.search_depth = 3
    g2.use_delta_pruning = False
    mv_off = g2.iterative_deepening_search_single()
    check('delta pruning 开关不改变战术选择', mv_on == mv_off and mv_on != (4, 0, 4, 4),
          'on=%s off=%s' % (mv_on, mv_off))


def test_search_quality():
    print('\n--- 搜索质量（优化回归） ---')
    # NMP 符号 bug：开启/关闭 null move 应走出同样的棋，不能出现 inf 评分
    g = blank(); g.board[4][0] = 'R'; g.board[4][4] = 'p'; g.board[8][4] = 'r'
    g.current_player = 'red'; g.search_depth = 3
    mv_on = g.iterative_deepening_search_single()

    g2 = blank(); g2.board[4][0] = 'R'; g2.board[4][4] = 'p'; g2.board[8][4] = 'r'
    g2.current_player = 'red'; g2.search_depth = 3
    orig = g2.alpha_beta_search
    def no_nmp(depth, alpha, beta, mx, st, ply=0, allow_null_move=True, extensions=0):
        return orig(depth, alpha, beta, mx, st, ply, False, extensions)
    g2.alpha_beta_search = no_nmp
    mv_off = g2.iterative_deepening_search_single()
    check('NMP 开关不改变选择（无 inf/毒饵）', mv_on == mv_off and mv_on != (4,0,4,4),
          'on=%s off=%s' % (mv_on, mv_off))

    # 攻击地图：不能因将帅照面把同列的士误判为受攻击
    g3 = blank(red=(0,3), black=(9,3)); g3.board[1][3] = 'A'
    ra, ba = g3._build_attack_maps()
    check('照面列上的士不被误判受攻击', (1,3) not in ba)

    # 将死检测仍然有效（evaluate_board 已移除重复判死）
    g4 = blank(red=(0,3), black=(9,5)); g4.board[8][0] = 'R'; g4.board[9][0] = 'R'
    check('将死仍被检测', g4.game_over is True and g4.winner == 'red')


if __name__ == '__main__':
    test_search_convention()
    test_server_no_double_apply()
    test_game_state()
    test_repetition()
    test_60_move_rule()
    test_long_check()
    test_delta_pruning()
    test_search_quality()
    print('\n失败项：%d' % len(FAILS))
    sys.exit(1 if FAILS else 0)
