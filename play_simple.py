#!/usr/bin/env python3
"""
Simple Text UI for Chess Engine
Clean ASCII display, no color codes, better terminal compatibility
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mini_chess import ChineseChess


def display_board_simple(game):
    """Simple ASCII board display"""
    print("\n   0 1 2 3 4 5 6 7 8")
    print("  " + "=" * 19)

    piece_symbols = {
        'K': 'K', 'k': 'k',  # King
        'R': 'R', 'r': 'r',  # Rook
        'H': 'N', 'h': 'n',  # Horse (Knight)
        'C': 'C', 'c': 'c',  # Cannon
        'B': 'B', 'b': 'b',  # Bishop
        'A': 'A', 'a': 'a',  # Advisor
        'P': 'P', 'p': 'p'   # Pawn
    }

    for i in range(10):
        row_str = f"{i} |"
        for j in range(9):
            piece = game.board[i][j]
            if piece == '.':
                row_str += " ."
            else:
                symbol = piece_symbols.get(piece, piece)
                row_str += f" {symbol}"

        side = "RED" if i < 5 else "BLK"
        row_str += f" | {side}"
        print(row_str)

    print("  " + "=" * 19)
    print("   0 1 2 3 4 5 6 7 8")

    player = "RED" if game.current_player == 'red' else "BLACK"
    print(f"\nCurrent player: {player}")


def play_game():
    """Simple game loop"""
    game = ChineseChess()
    game.init_board()

    print("="*50)
    print("CHINESE CHESS ENGINE - SIMPLE UI")
    print("="*50)
    print("\nCommands:")
    print("  move: <from_row> <from_col> <to_row> <to_col>")
    print("  Example: 0 1 2 2  (move from 0,1 to 2,2)")
    print("  ai      - Let AI move")
    print("  depth N - Set AI depth (default 3)")
    print("  time N  - Set AI time (default 5.0)")
    print("  restart - New game")
    print("  quit    - Exit")
    print()

    display_board_simple(game)

    while not game.game_over:
        try:
            cmd = input("\n> ").strip().lower()

            if not cmd:
                continue

            parts = cmd.split()

            if parts[0] == 'quit':
                break

            elif parts[0] == 'restart':
                game = ChineseChess()
                game.init_board()
                display_board_simple(game)

            elif parts[0] == 'depth' and len(parts) > 1:
                game.search_depth = int(parts[1])
                print(f"Depth set to {game.search_depth}")

            elif parts[0] == 'time' and len(parts) > 1:
                game.thinking_time = float(parts[1])
                print(f"Time set to {game.thinking_time}s")

            elif parts[0] == 'ai':
                print("AI thinking...")
                move = game.iterative_deepening_search()
                if move:
                    game.make_move(*move)
                    print(f"AI moved: {move}")
                    display_board_simple(game)
                else:
                    print("No legal move!")

            elif len(parts) == 4:
                # Move: from_row from_col to_row to_col
                try:
                    move = tuple(int(x) for x in parts)
                    legal_moves = game.get_all_legal_moves()

                    if move in legal_moves:
                        game.make_move(*move)
                        display_board_simple(game)
                    else:
                        print("Illegal move!")
                        print(f"Legal moves: {len(legal_moves)}")
                except ValueError:
                    print("Invalid move format")

            else:
                print("Unknown command. Type 'quit' to exit")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

    print("\nGame over!")


if __name__ == "__main__":
    play_game()
