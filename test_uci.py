#!/usr/bin/env python3
"""
UCI Interface Tester
Tests the UCI protocol implementation
"""

import os
import subprocess
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(errors='replace')
    except (ValueError, OSError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

def test_uci():
    """Test UCI interface"""
    failures = []
    print("="*60)
    print("UCI INTERFACE TESTER")
    print("="*60)
    print()

    # Start UCI interface
    print("Starting UCI interface...")
    proc = subprocess.Popen(
        [sys.executable, 'uci_interface.py'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=HERE
    )

    def send_cmd(cmd):
        """Send command and print"""
        print(f"\n> {cmd}")
        proc.stdin.write(cmd + '\n')
        proc.stdin.flush()

    def read_until(keyword, timeout=5):
        """Read until keyword found or timeout"""
        start = time.time()
        lines = []
        while time.time() - start < timeout:
            try:
                line = proc.stdout.readline().strip()
                if line:
                    print(f"< {line}")
                    lines.append(line)
                    if keyword in line:
                        return lines
            except:
                break
            time.sleep(0.01)
        return lines

    try:
        # Test 1: UCI handshake
        print("\n" + "="*60)
        print("TEST 1: UCI Handshake")
        print("="*60)
        send_cmd('uci')
        lines = read_until('uciok', timeout=2)
        if any('uciok' in l for l in lines):
            print("✅ UCI handshake successful")
        else:
            print("❌ UCI handshake failed")
            failures.append('handshake')

        # Test 2: isready
        print("\n" + "="*60)
        print("TEST 2: IsReady")
        print("="*60)
        send_cmd('isready')
        lines = read_until('readyok', timeout=1)
        if any('readyok' in l for l in lines):
            print("✅ IsReady successful")
        else:
            print("❌ IsReady failed")
            failures.append('isready')

        # Test 3: New game and position
        print("\n" + "="*60)
        print("TEST 3: Position Setup")
        print("="*60)
        send_cmd('ucinewgame')
        time.sleep(0.1)
        send_cmd('position startpos')
        time.sleep(0.1)
        print("✅ Position setup sent")

        # Test 4: Search
        print("\n" + "="*60)
        print("TEST 4: Search for Best Move")
        print("="*60)
        send_cmd('go movetime 2000')
        print("⏳ Searching (this will take 2 seconds)...")
        lines = read_until('bestmove', timeout=5)
        if any(l.startswith('bestmove') for l in lines):
            print("✅ Search successful - engine found a move!")
        else:
            print("❌ Search failed - no bestmove received")
            failures.append('search')

        # Quit
        print("\n" + "="*60)
        print("TEST 5: Quit")
        print("="*60)
        send_cmd('quit')
        proc.wait(timeout=2)
        print("✅ Engine stopped gracefully")

        if failures:
            print("\n" + "="*60)
            print("❌ FAILED: " + ", ".join(failures))
            print("="*60)
        else:
            print("\n" + "="*60)
            print("✅ ALL TESTS PASSED!")
            print("="*60)
            print("\nYour UCI interface is working correctly!")
            print("\nTo use in a Chess GUI:")
            print("1. Download Cute Chess or Arena")
            print("2. Add engine with command:")
            print(f"   python {sys.executable} {os.path.join(HERE, 'uci_interface.py')}")
            print("3. Play games!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        failures.append('exception')
        proc.kill()

    finally:
        try:
            proc.kill()
        except:
            pass

    return failures


if __name__ == "__main__":
    sys.exit(1 if test_uci() else 0)
