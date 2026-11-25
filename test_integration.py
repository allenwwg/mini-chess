#!/usr/bin/env python3
"""
Comprehensive test script for chess engine and server integration
"""

import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except (ValueError, OSError):
        pass

from mini_chess import ChineseChess

def test_engine_basic():
    """Test basic engine functionality"""
    print("\n=== Testing Chess Engine ===")

    try:
        game = ChineseChess()
        print("✓ Game initialized successfully")

        # Test board setup
        assert game.board[0][4] == 'K', "Red king should be at (0,4)"
        assert game.board[9][4] == 'k', "Black king should be at (9,4)"
        print("✓ Board initialized correctly")

        # Test initial player
        assert game.current_player == 'red', "Red should start"
        print("✓ Correct starting player")

        # Test move generation
        moves = game.get_all_legal_moves()
        print(f"✓ Generated {len(moves)} legal moves for red")

        if len(moves) == 0:
            print("✗ ERROR: No legal moves generated!")
            return False

        # Test making a move
        first_move = moves[0]
        print(f"  Testing move: {first_move}")

        start_row, start_col, end_row, end_col = first_move
        captured = game.make_move(start_row, start_col, end_row, end_col)
        print(f"✓ Move executed successfully (captured: {captured})")

        # Test player switch
        game.current_player = 'black'
        black_moves = game.get_all_legal_moves()
        print(f"✓ Generated {len(black_moves)} legal moves for black")

        # Test undo
        game.undo_move(start_row, start_col, end_row, end_col, captured)
        game.current_player = 'red'
        assert game.board[start_row][start_col] != '.', "Undo failed"
        print("✓ Undo move works")

        return True

    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ai_move():
    """Test AI move generation"""
    print("\n=== Testing AI Move Generation ===")

    try:
        game = ChineseChess()
        game.search_depth = 2  # Shallow depth for quick test
        game.thinking_time = 3.0

        print("Requesting AI move (depth=2, time=3s)...")
        start_time = time.time()

        best_move = game.iterative_deepening_search()

        elapsed = time.time() - start_time
        print(f"✓ AI returned move in {elapsed:.2f}s")

        if best_move is None:
            print("✗ ERROR: AI returned None")
            return False

        print(f"✓ AI move: {best_move}")
        print(f"  Nodes searched: {game.nodes_searched}")

        # Verify it's a legal move
        legal_moves = game.get_all_legal_moves()
        if best_move not in legal_moves:
            print("✗ ERROR: AI returned illegal move!")
            return False

        print("✓ AI move is legal")
        return True

    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_check_detection():
    """Test check and checkmate detection"""
    print("\n=== Testing Check Detection ===")

    try:
        game = ChineseChess()

        # Test initial position (should not be in check)
        assert not game.is_in_check('red'), "Red shouldn't be in check initially"
        assert not game.is_in_check('black'), "Black shouldn't be in check initially"
        print("✓ Initial position: no check")

        # Test checkmate detection
        assert not game.is_checkmate('red'), "Red shouldn't be checkmated initially"
        assert not game.is_checkmate('black'), "Black shouldn't be checkmated initially"
        print("✓ Checkmate detection works")

        return True

    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_server_imports():
    """Test if server can import required modules"""
    print("\n=== Testing Server Imports ===")

    try:
        from flask import Flask
        print("✓ Flask imported")

        from flask_cors import CORS
        print("✓ Flask-CORS imported")

        import chess_server
        print("✓ chess_server module imported")

        return True

    except ImportError as e:
        print(f"✗ Import ERROR: {e}")
        print("  Run: pip install flask flask-cors --break-system-packages")
        return False
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_specific_moves():
    """Test specific piece movements"""
    print("\n=== Testing Specific Piece Movements ===")

    try:
        game = ChineseChess()

        # Test pawn moves
        pawn_moves = game.get_piece_moves(3, 0)  # Red pawn at (3,0)
        print(f"✓ Pawn at (3,0) has {len(pawn_moves)} moves")

        # Test rook moves
        rook_moves = game.get_piece_moves(0, 0)  # Red rook at (0,0)
        print(f"✓ Rook at (0,0) has {len(rook_moves)} moves")

        # Test horse moves
        horse_moves = game.get_piece_moves(0, 1)  # Red horse at (0,1)
        print(f"✓ Horse at (0,1) has {len(horse_moves)} moves")

        # Test cannon moves
        cannon_moves = game.get_piece_moves(2, 1)  # Red cannon at (2,1)
        print(f"✓ Cannon at (2,1) has {len(cannon_moves)} moves")

        return True

    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("Chinese Chess Engine & Server Integration Tests")
    print("=" * 60)

    results = {}

    # Run tests
    results['basic'] = test_engine_basic()
    results['moves'] = test_specific_moves()
    results['check'] = test_check_detection()
    results['ai'] = test_ai_move()
    results['imports'] = test_server_imports()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:20s}: {status}")

    total = len(results)
    passed = sum(results.values())

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ All tests PASSED! Ready to start server.")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) FAILED. See errors above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
