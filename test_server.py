#!/usr/bin/env python3
"""
Test the chess server API endpoints
Run this AFTER starting the server with: python chess_server.py
"""

import sys
import json

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except (ValueError, OSError):
        pass

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: 'requests' module not available, using urllib instead")
    import urllib.request
    import urllib.parse

BASE_URL = 'http://localhost:5000/api'

def make_request(endpoint, method='GET', data=None):
    """Make HTTP request to server"""
    url = f"{BASE_URL}{endpoint}"

    if REQUESTS_AVAILABLE:
        if method == 'GET':
            response = requests.get(url)
        elif method == 'POST':
            response = requests.post(url, json=data)
        return response.status_code, response.json()
    else:
        # Use urllib. POST endpoints (/ai_move, /new_game) take no body but
        # must still be sent as POST - pass `method` through in both branches.
        if method == 'POST':
            body = json.dumps(data or {}).encode('utf-8')
            req = urllib.request.Request(url, data=body,
                                        headers={'Content-Type': 'application/json'},
                                        method='POST')
        else:
            req = urllib.request.Request(url, method=method)

        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode('utf-8'))

def test_get_board():
    """Test GET /api/board"""
    print("\n1. Testing GET /api/board")
    try:
        status, data = make_request('/board')
        if status == 200:
            print(f"   ✓ Status: {status}")
            print(f"   ✓ Current player: {data.get('current_player')}")
            print(f"   ✓ Game over: {data.get('game_over')}")
            print(f"   ✓ Board data received")
            return True
        else:
            print(f"   ✗ Status: {status}")
            return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False

def test_legal_moves():
    """Test POST /api/legal_moves"""
    print("\n2. Testing POST /api/legal_moves")
    try:
        # Test getting legal moves for red cannon at (2,1)
        status, data = make_request('/legal_moves', 'POST', {'row': 2, 'col': 1})
        if status == 200:
            moves = data.get('moves', [])
            print(f"   ✓ Status: {status}")
            print(f"   ✓ Got {len(moves)} legal moves for cannon at (2,1)")
            return True
        else:
            print(f"   ✗ Status: {status}")
            return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False

def test_make_move():
    """Test POST /api/move"""
    print("\n3. Testing POST /api/move")
    try:
        # Try to move red cannon from (2,1) to (5,1)
        status, data = make_request('/move', 'POST', {
            'start_row': 2,
            'start_col': 1,
            'end_row': 5,
            'end_col': 1
        })
        if status == 200 and data.get('success'):
            print(f"   ✓ Status: {status}")
            print(f"   ✓ Move executed successfully")
            print(f"   ✓ Current player now: {data.get('current_player')}")
            return True
        else:
            print(f"   ✗ Status: {status}, Success: {data.get('success')}")
            return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False

def test_ai_move():
    """Test POST /api/ai_move"""
    print("\n4. Testing POST /api/ai_move")
    try:
        status, data = make_request('/ai_move', 'POST')
        if status == 200 and data.get('success'):
            move = data.get('move')
            print(f"   ✓ Status: {status}")
            print(f"   ✓ AI move: {move}")
            print(f"   ✓ Current player now: {data.get('current_player')}")
            return True
        else:
            print(f"   ✗ Status: {status}, Success: {data.get('success')}")
            return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False

def test_new_game():
    """Test POST /api/new_game"""
    print("\n5. Testing POST /api/new_game")
    try:
        status, data = make_request('/new_game', 'POST')
        if status == 200 and data.get('success'):
            print(f"   ✓ Status: {status}")
            print(f"   ✓ New game started")
            print(f"   ✓ Current player: {data.get('current_player')}")
            return True
        else:
            print(f"   ✗ Status: {status}")
            return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False

def main():
    print("=" * 60)
    print("Testing Chinese Chess Server API")
    print("=" * 60)
    print("\nMake sure the server is running:")
    print("  python chess_server.py")
    if sys.stdin.isatty():
        print("\nPress Enter to continue...")
        input()

    results = {}

    # Run tests
    results['get_board'] = test_get_board()
    results['legal_moves'] = test_legal_moves()
    results['make_move'] = test_make_move()
    results['ai_move'] = test_ai_move()
    results['new_game'] = test_new_game()

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
        print("\n✓ All server tests PASSED!")
        print("You can now open index.html in your browser")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) FAILED")
        print("Check if the server is running on http://localhost:5000")
        return 1

if __name__ == '__main__':
    sys.exit(main())
