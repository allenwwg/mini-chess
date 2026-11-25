"""
Integration Guide: Adding Opening Book to Chess Engine
"""

# Step 1: Import the opening book at the top of mini_chess.py
from opening_book import OpeningBook

# Step 2: Add opening book to __init__ method
class ChineseChess:
    def __init__(self):
        # ... existing code ...

        # Opening book
        self.opening_book = OpeningBook()
        self.use_opening_book = True  # Toggle opening book on/off


# Step 3: Modify iterative_deepening_search to check book first
def iterative_deepening_search(self):
    """迭代加深搜索（带开局库支持）"""

    # Check opening book first
    if self.use_opening_book and len(self.move_history) < 10:
        book_move = self.opening_book.get_book_move_by_moves(self.move_history)
        if book_move:
            print(f"使用开局库走法: {book_move}")
            return book_move

    # Otherwise, use normal search
    self.nodes_searched = 0
    start_time = time.time()

    # ... rest of existing code ...


# Step 4: Add command to toggle opening book
def handle_command(self, command):
    """处理命令行输入"""
    parts = command.strip().split()
    if not parts:
        return False

    cmd = parts[0].lower()

    # ... existing commands ...

    elif cmd == 'book':
        if len(parts) > 1:
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

    # ... rest of existing code ...


def show_opening_book_moves(self):
    """显示当前局面的开局库走法"""
    if len(self.move_history) < 10:
        # Determine position key based on move history
        if len(self.move_history) == 0:
            position_key = "start"
        elif len(self.move_history) == 1:
            position_key = "after_red_central_cannon_right"
        elif len(self.move_history) == 2:
            position_key = "after_black_screen_horse"
        else:
            print("该局面不在开局库中")
            return

        moves = self.opening_book.get_all_book_moves(position_key)
        if moves:
            print("\n可用的开局库走法:")
            for move_info in moves:
                print(f"  {move_info['name']}: {move_info['move']} (权重: {move_info['weight']})")
        else:
            print("该局面不在开局库中")
    else:
        print("已超出开局库范围（前10步）")
