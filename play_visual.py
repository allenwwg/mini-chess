#!/usr/bin/env python3
"""
Chinese Chess - Visual Board UI
Clean grid display with box-drawing characters
"""

import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except (ValueError, OSError):
        pass

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mini_chess import ChineseChess, pad_cell


def display_board_visual(game, last_move_info=None, captured_pieces=None, move_number=1):
    """Display board with box-drawing characters and enhancements"""

    # Piece symbols with better visibility
    piece_symbols = {
        'K': '帅', 'k': '将',  # King
        'R': '車', 'r': '车',  # Rook
        'H': '馬', 'h': '马',  # Horse
        'C': '炮', 'c': '砲',  # Cannon
        'B': '相', 'b': '象',  # Bishop
        'A': '仕', 'a': '士',  # Advisor
        'P': '兵', 'p': '卒'   # Pawn
    }

    # Piece names for move notation
    piece_names = {
        'K': 'King', 'k': 'King',
        'R': 'Rook', 'r': 'Rook',
        'H': 'Horse', 'h': 'Horse',
        'C': 'Cannon', 'c': 'Cannon',
        'B': 'Bishop', 'b': 'Bishop',
        'A': 'Advisor', 'a': 'Advisor',
        'P': 'Pawn', 'p': 'Pawn'
    }

    # Column letters for notation
    cols = 'ABCDEFGHI'

    # Captured pieces display
    if captured_pieces is None:
        captured_pieces = {'red': [], 'black': []}

    CELL = 3
    print("\n     " + ''.join(pad_cell(str(j), CELL + 1) for j in range(9)))
    print("   ┌" + '┬'.join('─' * CELL for _ in range(9)) + '┐')

    # Track last move squares for highlighting
    highlight_squares = []
    if game.last_move:
        highlight_squares = [(game.last_move[0], game.last_move[1]),
                           (game.last_move[2], game.last_move[3])]

    for i in range(10):
        # Build row
        row_str = f" {i} │"

        for j in range(9):
            piece = game.board[i][j]
            is_highlighted = (i, j) in highlight_squares

            if piece == '.':
                symbol = '·'
            else:
                symbol = piece_symbols.get(piece, piece)
            cell = ('*' + symbol) if is_highlighted else symbol
            row_str += ' ' + pad_cell(cell, CELL - 1) + '│'

        # Add side label with captured pieces
        if i == 0:
            row_str += f" RED  Captured: {' '.join(captured_pieces['black'][:8])}"
        elif i == 1:
            if len(captured_pieces['black']) > 8:
                row_str += f"            {' '.join(captured_pieces['black'][8:])}"
            else:
                row_str += " RED"
        elif i < 5:
            row_str += " RED"
        elif i == 9:
            row_str += f" BLK  Captured: {' '.join(captured_pieces['red'][:8])}"
        elif i == 8:
            if len(captured_pieces['red']) > 8:
                row_str += f"            {' '.join(captured_pieces['red'][8:])}"
            else:
                row_str += " BLK"
        else:
            row_str += " BLK"

        print(row_str)

        # Separator between rows
        if i < 9:
            if i == 4:
                # River crossing
                print("   ├───┼───┼───┼───┼───┼───┼───┼───┼───┤ ═══ RIVER ═══")
            else:
                print("   ├───┼───┼───┼───┼───┼───┼───┼───┼───┤")

    print("   └" + '┴'.join('─' * CELL for _ in range(9)) + '┘')
    print("     " + ''.join(pad_cell(str(j), CELL + 1) for j in range(9)))
    print("     " + ''.join(pad_cell(c, CELL + 1) for c in cols))

    # Game info with move number
    player = "RED (上)" if game.current_player == 'red' else "BLACK (下)"
    print(f"\n  Move {move_number} - Current Turn: {player}")

    # Enhanced last move notation
    if last_move_info:
        from_pos, to_pos, piece_moved, captured = last_move_info
        piece_name = piece_names.get(piece_moved, '?')
        from_notation = f"{cols[from_pos[1]]}{from_pos[0]}"
        to_notation = f"{cols[to_pos[1]]}{to_pos[0]}"

        move_desc = f"  Last Move: {piece_name} {from_notation} → {to_notation}"
        if captured and captured != '.':
            captured_name = piece_names.get(captured, '?')
            move_desc += f" (captured {captured_name})"
        print(move_desc)

    # Helpful hint
    if game.current_player == 'red':
        print("  💡 Your turn! Type 'moves' to see options, or 'ai' to let engine play")
    else:
        print("  💡 Black's turn! Type 'moves' to see options, or 'ai' to let engine play")


def display_menu():
    """Display command menu"""
    print("\n" + "="*60)
    print("COMMANDS:")
    print("="*60)
    print("  move <from_row> <from_col> <to_row> <to_col>")
    print("       Example: move 0 1 2 2")
    print("  m <from_row> <from_col> <to_row> <to_col>  (shortcut)")
    print("       Example: m 0 1 2 2")
    print()
    print("  ai           - Let AI move")
    print("  depth <N>    - Set AI search depth (default 3)")
    print("  time <N>     - Set AI thinking time (default 5.0)")
    print("  moves        - Show all legal moves")
    print("  eval         - Show position evaluation")
    print("  undo         - Undo last move")
    print("  restart      - Start new game")
    print("  help         - Show this menu")
    print("  quit         - Exit")
    print("="*60)


def show_legal_moves(game):
    """Show all legal moves"""
    moves = game.get_all_legal_moves()
    print(f"\nLegal moves ({len(moves)}):")

    # Group by starting position
    move_groups = {}
    for move in moves:
        key = (move[0], move[1])
        if key not in move_groups:
            move_groups[key] = []
        move_groups[key].append((move[2], move[3]))

    for start, destinations in sorted(move_groups.items()):
        piece = game.board[start[0]][start[1]]
        print(f"  From {start}: {piece} -> {destinations[:5]}", end='')
        if len(destinations) > 5:
            print(f" ... (+{len(destinations)-5} more)")
        else:
            print()


def play_visual():
    """Main game loop with visual UI"""
    game = ChineseChess()
    game.init_board()

    print("\n" + "╔" + "═"*58 + "╗")
    print("║" + " "*15 + "CHINESE CHESS ENGINE" + " "*23 + "║")
    print("║" + " "*19 + "Visual Board UI" + " "*24 + "║")
    print("╚" + "═"*58 + "╝")

    display_menu()

    # Game state tracking
    move_history = []
    captured_pieces = {'red': [], 'black': []}
    move_number = 1
    last_move_info = None

    # Piece symbols for captured display
    piece_symbols = {
        'K': '帅', 'k': '将',
        'R': '車', 'r': '车',
        'H': '馬', 'h': '马',
        'C': '炮', 'c': '砲',
        'B': '相', 'b': '象',
        'A': '仕', 'a': '士',
        'P': '兵', 'p': '卒'
    }

    display_board_visual(game, last_move_info, captured_pieces, move_number)

    while not game.is_game_over():
        try:
            cmd = input("\n>>> ").strip()

            if not cmd:
                continue

            parts = cmd.split()
            command = parts[0].lower()

            # Quit
            if command in ['quit', 'exit', 'q']:
                print("Thanks for playing!")
                break

            # Help
            elif command == 'help':
                display_menu()

            # Restart
            elif command == 'restart':
                game = ChineseChess()
                game.init_board()
                move_history = []
                captured_pieces = {'red': [], 'black': []}
                move_number = 1
                last_move_info = None
                print("\n✅ New game started!")
                display_board_visual(game, last_move_info, captured_pieces, move_number)

            # Undo
            elif command == 'undo':
                if move_history:
                    last_move, captured, old_move_info = move_history.pop()
                    game.undo_move(*last_move, captured)

                    # Remove from captured list
                    if captured and captured != '.':
                        if captured.isupper():
                            captured_pieces['red'].pop()
                        else:
                            captured_pieces['black'].pop()

                    move_number -= 1
                    last_move_info = move_history[-1][2] if move_history else None

                    print("✅ Move undone")
                    display_board_visual(game, last_move_info, captured_pieces, move_number)
                else:
                    print("❌ No moves to undo")

            # Set depth
            elif command == 'depth' and len(parts) > 1:
                game.search_depth = int(parts[1])
                print(f"✅ Search depth set to {game.search_depth}")

            # Set time
            elif command == 'time' and len(parts) > 1:
                game.thinking_time = float(parts[1])
                print(f"✅ Thinking time set to {game.thinking_time}s")

            # Show moves
            elif command == 'moves':
                show_legal_moves(game)

            # Evaluation
            elif command == 'eval':
                eval_score = game.evaluate_board()
                print(f"\n📊 Position Evaluation: {eval_score:.1f}")
                if eval_score > 100:
                    print("   Red is winning")
                elif eval_score < -100:
                    print("   Black is winning")
                else:
                    print("   Position is roughly equal")

            # AI move
            elif command == 'ai':
                print(f"\n🤔 AI thinking (depth {game.search_depth}, time {game.thinking_time}s)...")

                # Remember piece before move
                move = game.iterative_deepening_search()

                if move:
                    piece_moved = game.board[move[0]][move[1]]
                    captured = game.make_move(*move)

                    # Track captured pieces
                    if captured and captured != '.':
                        symbol = piece_symbols.get(captured, captured)
                        if captured.isupper():
                            captured_pieces['red'].append(symbol)
                        else:
                            captured_pieces['black'].append(symbol)

                    # Create move info
                    last_move_info = (
                        (move[0], move[1]),  # from_pos
                        (move[2], move[3]),  # to_pos
                        piece_moved,         # piece_moved
                        captured            # captured piece
                    )

                    move_history.append((move, captured, last_move_info))

                    display_board_visual(game, last_move_info, captured_pieces, move_number)
                    move_number += 1

                    if game.is_in_check(game.current_player):
                        print("⚠️  CHECK!")
                else:
                    print("❌ AI couldn't find a move!")

            # Manual move
            elif command in ['move', 'm'] and len(parts) >= 5:
                try:
                    move = (int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
                    legal_moves = game.get_all_legal_moves()

                    if move in legal_moves:
                        piece_moved = game.board[move[0]][move[1]]
                        captured = game.make_move(*move)

                        # Track captured pieces
                        if captured and captured != '.':
                            symbol = piece_symbols.get(captured, captured)
                            if captured.isupper():
                                captured_pieces['red'].append(symbol)
                            else:
                                captured_pieces['black'].append(symbol)

                        # Create move info
                        last_move_info = (
                            (move[0], move[1]),
                            (move[2], move[3]),
                            piece_moved,
                            captured
                        )

                        move_history.append((move, captured, last_move_info))

                        display_board_visual(game, last_move_info, captured_pieces, move_number)
                        move_number += 1

                        if game.is_in_check(game.current_player):
                            print("⚠️  CHECK!")
                    else:
                        print("❌ Illegal move!")
                        print("   Type 'moves' to see legal moves")

                except ValueError:
                    print("❌ Invalid move format")
                    print("   Use: move <from_row> <from_col> <to_row> <to_col>")

            # Short move notation (just 4 numbers)
            elif len(parts) == 4 and all(p.isdigit() for p in parts):
                try:
                    move = tuple(int(x) for x in parts)
                    legal_moves = game.get_all_legal_moves()

                    if move in legal_moves:
                        piece_moved = game.board[move[0]][move[1]]
                        captured = game.make_move(*move)

                        # Track captured pieces
                        if captured and captured != '.':
                            symbol = piece_symbols.get(captured, captured)
                            if captured.isupper():
                                captured_pieces['red'].append(symbol)
                            else:
                                captured_pieces['black'].append(symbol)

                        # Create move info
                        last_move_info = (
                            (move[0], move[1]),
                            (move[2], move[3]),
                            piece_moved,
                            captured
                        )

                        move_history.append((move, captured, last_move_info))

                        display_board_visual(game, last_move_info, captured_pieces, move_number)
                        move_number += 1

                        if game.is_in_check(game.current_player):
                            print("⚠️  CHECK!")
                    else:
                        print("❌ Illegal move!")

                except ValueError:
                    print("❌ Invalid move")

            else:
                print("❌ Unknown command. Type 'help' for commands")

        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            print("   Type 'help' for commands")

    print("\n" + "="*60)
    print("Game Over!")
    print("="*60)

    # Check for checkmate and announce winner
    if game.is_game_over():
        if game.is_checkmate('red'):
            print("🎉 BLACK WINS! Red is checkmated.")
        elif game.is_checkmate('black'):
            print("🎉 RED WINS! Black is checkmated.")


if __name__ == "__main__":
    play_visual()
