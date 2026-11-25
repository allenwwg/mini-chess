from flask import Flask, jsonify, request
from flask_cors import CORS
from mini_chess import ChineseChess
import json
import sys

# 控制台编码兜底：与 mini_chess 保持一致，避免 ✓/✗/emoji 输出时崩溃
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except (ValueError, OSError):
        pass

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Global game instance
game = None

def init_game():
    """Initialize a new game"""
    global game
    game = ChineseChess()
    game.search_depth = 3
    game.thinking_time = 5.0
    return game

# Initialize game on startup
init_game()

def board_to_json():
    """Convert board state to JSON format"""
    end_reason = None
    if game.game_over:
        if game.get_long_check_loser() is not None:
            end_reason = 'perpetual_check'
        elif game.is_draw_by_repetition(3):
            end_reason = 'repetition'
        elif game.is_draw_by_60_moves():
            end_reason = '60_moves'
        else:
            end_reason = 'checkmate'
    return {
        'board': game.board,
        'current_player': game.current_player,
        'game_over': game.game_over,
        'winner': game.winner,
        'end_reason': end_reason,
        'last_move': game.last_move,
        'move_history': game.move_history,
        'in_check': game.is_in_check(game.current_player),
        'search_stats': game.last_search_stats
    }

@app.route('/')
def index():
    """直接托管前端页面，访问 http://localhost:5000 即可打开"""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html')
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


@app.route('/api/board', methods=['GET'])
def get_board():
    """Get current board state"""
    return jsonify(board_to_json())

@app.route('/api/new_game', methods=['POST'])
def new_game():
    """Start a new game"""
    init_game()
    return jsonify({
        'success': True,
        'message': 'New game started',
        **board_to_json()
    })

@app.route('/api/legal_moves', methods=['POST'])
def get_legal_moves():
    """Get legal moves for a piece at given position"""
    data = request.json
    row = data.get('row')
    col = data.get('col')

    if row is None or col is None:
        return jsonify({'error': 'Missing row or col'}), 400

    piece = game.board[row][col]
    if piece == '.':
        return jsonify({'moves': []})

    # Check if it's the correct player's piece
    if (game.current_player == 'red' and not piece.isupper()) or \
       (game.current_player == 'black' and not piece.islower()):
        return jsonify({'moves': []})

    # Get all legal moves for this piece
    all_moves = game.get_all_legal_moves()
    piece_moves = [
        {'from': [m[0], m[1]], 'to': [m[2], m[3]]}
        for m in all_moves
        if m[0] == row and m[1] == col
    ]

    return jsonify({'moves': piece_moves})

@app.route('/api/move', methods=['POST'])
def make_move():
    """Make a move"""
    data = request.json
    start_row = data.get('start_row')
    start_col = data.get('start_col')
    end_row = data.get('end_row')
    end_col = data.get('end_col')

    if any(x is None for x in [start_row, start_col, end_row, end_col]):
        return jsonify({'error': 'Missing move coordinates'}), 400

    # Verify it's a legal move
    legal_moves = game.get_all_legal_moves()
    move = (start_row, start_col, end_row, end_col)

    if move not in legal_moves:
        return jsonify({
            'success': False,
            'error': 'Illegal move',
            **board_to_json()
        }), 400

    # make_move() 已负责落子、记历史、切换玩家、设置 last_move；
    # game_over / winner 由局面实时推导，无需（也不可）在此重复设置。
    captured = game.make_move(start_row, start_col, end_row, end_col)

    return jsonify({
        'success': True,
        'captured': captured,
        **board_to_json()
    })

@app.route('/api/ai_move', methods=['POST'])
def get_ai_move():
    """Get AI move for current player"""
    if game.game_over:
        return jsonify({
            'success': False,
            'error': 'Game is over',
            **board_to_json()
        })

    # Get AI move
    print(f"AI thinking for {game.current_player}...")
    best_move = game.iterative_deepening_search()

    if best_move is None:
        # 无合法走法，终局状态由 game_over/winner 属性自动推导
        return jsonify({
            'success': False,
            'error': 'No legal moves',
            **board_to_json()
        })

    start_row, start_col, end_row, end_col = best_move

    # make_move() 已负责全部状态更新，禁止在此重复
    captured = game.make_move(start_row, start_col, end_row, end_col)

    return jsonify({
        'success': True,
        'move': {
            'from': [start_row, start_col],
            'to': [end_row, end_col]
        },
        'captured': captured,
        **board_to_json()
    })

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update AI settings"""
    data = request.json

    if 'search_depth' in data:
        game.search_depth = data['search_depth']

    if 'thinking_time' in data:
        game.thinking_time = data['thinking_time']

    if 'ai_enabled' in data:
        game.ai_enabled = data['ai_enabled']

    if 'use_pro_book' in data and hasattr(game, 'use_pro_book'):
        game.use_pro_book = bool(data['use_pro_book'])

    if 'use_endgame_book' in data and hasattr(game, 'use_endgame_book'):
        game.use_endgame_book = bool(data['use_endgame_book'])

    settings = {
        'search_depth': game.search_depth,
        'thinking_time': game.thinking_time,
        'ai_enabled': game.ai_enabled,
    }
    if hasattr(game, 'use_pro_book'):
        settings['use_pro_book'] = game.use_pro_book
    if hasattr(game, 'use_endgame_book'):
        settings['use_endgame_book'] = game.use_endgame_book

    return jsonify({'success': True, 'settings': settings})

if __name__ == '__main__':
    print("Starting Chinese Chess Server...")
    print("Server running at http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
