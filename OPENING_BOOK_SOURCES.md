# Where to Get Chinese Chess Opening Book Data

## Method 1: Online Game Databases (Best Source)

### 1.1 XQBase (中国象棋棋谱仓库)
**Website**: http://www.xqbase.com/

**What you get**:
- Thousands of professional games in PGN/XQF format
- Master-level games from tournaments
- Opening statistics and variations

**How to use**:
1. Download game collections (棋谱下载)
2. Parse the game files to extract opening moves
3. Build statistics: which moves are played most often from each position

**Example parsing**:
```python
def parse_xqf_games(filename):
    """Parse XQF format Chinese Chess games"""
    opening_stats = defaultdict(lambda: defaultdict(int))
    
    # Read games from file
    games = load_xqf_file(filename)
    
    # Extract first 10 moves of each game
    for game in games:
        position_hash = initial_position_hash()
        
        for move_num, move in enumerate(game.moves[:10]):
            # Count how often this move is played from this position
            opening_stats[position_hash][move] += 1
            
            # Update position
            position_hash = update_hash_after_move(position_hash, move)
    
    return opening_stats
```

### 1.2 Chinese Chess Database Sites
- **www.dpxq.com** (东萍象棋网) - Large game database
- **www.chessx.cn** - Professional games
- **象棋巫师** (Chess Wizard) - Software with huge game database

---

## Method 2: Published Opening Theory Books

### Popular Chinese Chess Opening Books:
1. **《象棋布局定式与战理》** - Standard opening patterns
2. **《象棋开局陷阱100例》** - Opening traps
3. **《象棋中局杀法》** - Middle game tactics (useful after opening)
4. **《中炮对屏风马》** - Central Cannon vs Screen Horse (most common)

**How to use**:
- Manually encode the recommended moves from these books
- Focus on "main lines" (主变) rather than all variations

---

## Method 3: Extract from Strong Engines

### Existing Strong Chinese Chess Engines:
1. **Pikafish** - Very strong, open source
   - GitHub: https://github.com/official-pikafish/Pikafish
   - Has opening book support

2. **ElephantEye (象眼)** - Popular Chinese engine
   - Can export its opening knowledge

3. **Cyclone** - Strong commercial engine
   - Book format is documented

**How to extract**:
```python
def analyze_engine_games(engine_path, num_games=1000):
    """
    Play the engine against itself many times,
    record what it plays in the opening
    """
    opening_moves = defaultdict(lambda: defaultdict(int))
    
    for _ in range(num_games):
        game = play_engine_self_game(engine_path, max_moves=10)
        
        position = initial_position()
        for move in game.moves:
            pos_key = hash_position(position)
            opening_moves[pos_key][move] += 1
            position = apply_move(position, move)
    
    return opening_moves
```

---

## Method 4: Web Scraping Opening Statistics

### CloudBook API (云开局库)
Some Chinese Chess websites offer opening statistics APIs:

```python
import requests

def get_opening_stats_from_cloud(position_fen):
    """
    Query cloud opening database for move statistics
    """
    # Example API (you'd need to find actual working APIs)
    url = "http://api.example.com/xiangqi/opening"
    params = {
        'fen': position_fen,
        'moves': 10
    }
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        # Returns: {move: {count: 1234, win_rate: 0.52}}
        return data['moves']
    
    return None
```

---

## Method 5: Machine Learning from Games

### Generate Opening Book from PGN Collection:

```python
import chess  # or python-chess library adapted for Chinese chess

class OpeningBookGenerator:
    def __init__(self):
        self.move_stats = defaultdict(lambda: defaultdict(lambda: {
            'count': 0,
            'wins': 0,
            'draws': 0,
            'losses': 0
        }))
    
    def process_game(self, game, max_ply=20):
        """
        Process a single game and extract opening moves
        
        Args:
            game: Game object with moves and result
            max_ply: How many half-moves to consider as "opening"
        """
        board = ChineseChessBoard()
        
        for ply, move in enumerate(game.moves[:max_ply]):
            position_key = board.zobrist_hash()
            move_key = self.move_to_key(move)
            
            # Update statistics
            self.move_stats[position_key][move_key]['count'] += 1
            
            if game.result == '1-0':  # Red wins
                if ply % 2 == 0:  # Red's move
                    self.move_stats[position_key][move_key]['wins'] += 1
                else:  # Black's move
                    self.move_stats[position_key][move_key]['losses'] += 1
            elif game.result == '0-1':  # Black wins
                if ply % 2 == 0:
                    self.move_stats[position_key][move_key]['losses'] += 1
                else:
                    self.move_stats[position_key][move_key]['wins'] += 1
            else:  # Draw
                self.move_stats[position_key][move_key]['draws'] += 1
            
            board.push(move)
    
    def process_pgn_collection(self, pgn_file):
        """Process entire PGN file"""
        with open(pgn_file) as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                self.process_game(game)
    
    def export_book(self, min_games=5, min_win_rate=0.45):
        """
        Export opening book, filtering by quality
        
        Args:
            min_games: Minimum times a move must be played
            min_win_rate: Minimum win rate to include move
        """
        book = {}
        
        for position, moves in self.move_stats.items():
            book[position] = []
            
            for move, stats in moves.items():
                if stats['count'] >= min_games:
                    win_rate = (stats['wins'] + 0.5 * stats['draws']) / stats['count']
                    
                    if win_rate >= min_win_rate:
                        book[position].append({
                            'move': move,
                            'count': stats['count'],
                            'win_rate': win_rate,
                            'weight': int(stats['count'] * win_rate * 100)
                        })
            
            # Sort by weight (popularity * quality)
            book[position].sort(key=lambda x: x['weight'], reverse=True)
        
        return book
    
    def save_to_file(self, filename):
        """Save opening book to file"""
        import json
        book = self.export_book()
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(book, f, ensure_ascii=False, indent=2)

# Usage:
generator = OpeningBookGenerator()
generator.process_pgn_collection('chinese_chess_games.pgn')
generator.save_to_file('opening_book.json')
```

---

## Method 6: Use the Basic Book I Created + Expand It

The `opening_book.py` I created has the most common openings. You can expand it by:

### Adding More Variations:

```python
def add_advanced_openings(self):
    """Add more detailed opening variations"""
    
    # After 中炮对屏风马 (Central Cannon vs Screen Horse)
    # Red's 3rd move options
    book["after_2_moves_central_vs_screen"].append({
        'move': (2, 7, 2, 8),  # Cannon shifts right
        'name': '巡河炮 (River Patrol Cannon)',
        'weight': 40
    })
    
    book["after_2_moves_central_vs_screen"].append({
        'move': (0, 7, 2, 8),  # Horse protects cannon
        'name': '边马 (Edge Horse)',
        'weight': 30
    })
    
    # After 仕角炮 (Advisor Horn Cannon)
    book["after_advisor_horn_cannon"].append({
        'move': (9, 1, 7, 2),  # Screen horse response
        'name': '屏风马 (Screen Horse)',
        'weight': 50
    })
    
    # Middlegame transitions (moves 6-10)
    book["middlegame_transition"].append({
        'move': (5, 7, 5, 4),  # Cannon to center
        'name': '炮打中兵 (Cannon attacks central pawn)',
        'weight': 45
    })
```

---

## Recommended Approach for You:

### Phase 1 (Immediate):
✅ Use the basic opening book I created  
✅ Test it and see the improvement  

### Phase 2 (1-2 weeks):
✅ Download 100-200 master games from XQBase  
✅ Parse them and extract opening statistics  
✅ Add the most common moves to your book  

### Phase 3 (Advanced):
✅ Implement the ML-based book generator  
✅ Process 10,000+ games  
✅ Generate a comprehensive opening book with win rates  

---

## Quick Start: Expand the Basic Book

I can help you add more openings to the basic book right now. The most important ones to add:

1. **中炮进三兵对屏风马** - Most common at master level
2. **仕角炮对反宫马** - Popular counter-attack
3. **飞相局** - Defensive opening for Red
4. **五六炮** - Aggressive double cannon setup
5. **五七炮** - Another popular cannon formation

Would you like me to:
1. **Expand the basic opening book** with more variations?
2. **Create a PGN parser** to extract moves from game files?
3. **Show you how to download** game collections from XQBase?

Let me know which approach you prefer!
