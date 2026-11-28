# Chinese Chess (中国象棋) - Setup and Run Guide

## 📋 Quick Start

### Step 1: Check Prerequisites
```bash
python check_prerequisites.py
```

This will check if you have all required packages installed.

### Step 2: Install Required Packages (if needed)
```bash
pip install flask flask-cors
```

### Step 3: Start the Server
```bash
python chess_server.py
```

You should see:
```
Starting Chinese Chess Server...
Server running at http://localhost:5000
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
```

### Step 4: Open the Game
Open `index.html` in your web browser:
- Double-click `index.html`, OR
- Right-click and choose "Open with" -> Your browser

### Step 5: Test the Server (Optional)
In a new terminal, while the server is running:
```bash
python test_server.py
```

## 🎮 How to Play

1. **Human vs Human**: Click pieces to select them, then click destination to move
2. **Human vs AI**: Click "AI 走棋 (AI Move)" button to let AI play
3. **Settings**: Adjust search depth and thinking time in the settings panel
4. **New Game**: Click "新游戏 (New Game)" to restart

## 🔧 Troubleshooting

### Problem: Server won't start
**Solution**: Make sure port 5000 is not already in use
```bash
# On Windows, check what's using port 5000:
netstat -ano | findstr :5000

# Kill the process if needed (replace PID with actual process ID):
taskkill /PID <PID> /F
```

### Problem: Can't connect to server
**Error**: "无法连接到服务器 (Cannot connect to server)"

**Solution**: 
1. Make sure server is running (`python chess_server.py`)
2. Check the server URL in browser console
3. Try accessing http://localhost:5000/api/board directly

### Problem: Import errors
**Error**: `ModuleNotFoundError: No module named 'flask'`

**Solution**: Install required packages:
```bash
pip install flask flask-cors
```

### Problem: AI is too slow/fast
**Solution**: Adjust settings in the UI:
- Search Depth: Lower = faster, Higher = stronger
- Thinking Time: Maximum time AI will spend thinking

## 📁 Project Structure

```
chess/
├── mini_chess.py           # Chess engine with AI
├── chess_server.py         # Flask REST API server
├── index.html              # Web UI
├── opening_book.py         # Opening book for better play
├── check_prerequisites.py  # Check if ready to run
├── test_integration.py     # Test chess engine
├── test_server.py          # Test server API
└── README.md               # This file
```

## 🚀 Features

### Chess Engine
- ✓ Full Chinese Chess rules implementation
- ✓ Legal move generation with check detection
- ✓ Alpha-Beta pruning with optimizations
- ✓ Transposition table for faster search
- ✓ Killer moves and history heuristic
- ✓ Quiescence search for stable positions
- ✓ Check extensions for tactical play
- ✓ Opening book for strong opening play

### AI Capabilities
- Search depth: 2-5 (configurable)
- Thinking time: 3-10 seconds (configurable)
- Position evaluation with material and positional scores
- Adaptive time management based on position complexity

### Web UI
- Beautiful gradient design
- Real-time board updates
- Move history tracking
- Check/checkmate warnings
- Responsive layout for different screen sizes

## 🔍 Testing

### Test Chess Engine Only
```bash
python test_integration.py
```

This tests:
- Board initialization
- Move generation
- Check detection
- AI move generation
- All piece movements

### Test Server API
```bash
# Terminal 1: Start server
python chess_server.py

# Terminal 2: Run tests
python test_server.py
```

This tests:
- All API endpoints
- Move validation
- AI integration
- Game state management

## 📊 API Endpoints

- `GET /api/board` - Get current board state
- `POST /api/new_game` - Start a new game
- `POST /api/legal_moves` - Get legal moves for a piece
- `POST /api/move` - Make a move
- `POST /api/ai_move` - Get AI to make a move
- `POST /api/settings` - Update AI settings

## 🎯 Current Status

✅ **Working:**
- Chess engine (all rules implemented correctly)
- Move generation (44 legal moves in starting position)
- AI with opening book
- Check/checkmate detection
- All piece movements (pawn, rook, horse, cannon, etc.)

⚠️ **Setup Required:**
- Install Flask and Flask-CORS (one-time setup)

## 💡 Tips

1. **For faster AI**: Set search depth to 2-3
2. **For stronger AI**: Set search depth to 4-5 (slower)
3. **Opening phase**: AI uses opening book for fast, strong moves
4. **Middle game**: AI searches deeply for tactical combinations
5. **Endgame**: AI evaluates positions accurately

## 📝 Notes

- The server must be running for the UI to work
- The UI connects to `http://localhost:5000`
- All data is stored in memory (restarting server = new game)
- The AI can think for up to the configured thinking time
- Opening book speeds up initial moves significantly

---

## 🔧 UCI / Pikafish Match Driver

The engine exposes a UCI interface (`uci_interface.py`, ICCS moves) usable from any
Chinese-chess GUI, and a match driver (`tools/match_vs_pikafish.py`) that plays two
UCI engines against each other with an in-process arbiter. Pikafish binaries/NNUE
are not committed (download separately into `pikafish/`).

```bash
# UCI engine (GUI command):
python uci_interface.py

# 100-game rating vs Pikafish (300ms/move), abnormal games replayed:
python tools/match_vs_pikafish.py --engine2 "pikafish/Pikafish-Windows-x86-64-universal.exe" \
    --games 100 --movetime 300 --max-plies 200 --max-retries 3 --out data/match100.json
```

Rating result (2026-11): **0W / 0D / 99L** (1 voided) vs Pikafish at 300ms/move —
a clear strength gap to a top NNUE engine.

## 🧪 P0 Search Enhancements (isolated A/B)

Five search fixes are behind switches in `mini_chess.py` (all default-on, set a
switch to `False` to restore old behavior): `fix_nmp_min_window`,
`use_root_best_ordering`, `progressive_aspiration`, `unify_mate_ply`,
`clear_tt_on_new_game`. Regression: `python test_search_enhance.py` (7 tests).

Isolated A/B (`tools/ab_search_enhance.py`, 40 games, 200ms/move, randomized
openings, same code with only the switches toggled): **NEW 15W / 12D / 13OLD**,
score 52.5% (Wilson 95% CI [37.5, 67.1]) — the CI crosses 50%: the fixes are
correct but **not statistically proven to gain strength** at this sample size.

---

**Enjoy playing Chinese Chess! 🎮♟️**
