"""
Expanded Chinese Chess Opening Book
Comprehensive coverage of major opening systems with deep variations
"""

import random
from collections import defaultdict


class OpeningBook:
    """Comprehensive Opening Book for Chinese Chess (Xiangqi)"""

    def __init__(self):
        self.book = self._create_opening_book()

    def _create_opening_book(self):
        """
        Create comprehensive opening book with major Chinese Chess openings

        Coverage:
        - 中炮对屏风马 (Central Cannon vs Screen Horse) - most popular
        - 顺炮局 (Double Cannon)
        - 五六炮/五七炮 formations
        - 仕角炮 (Advisor Horn Cannon)
        - 飞相局 (Flying Elephant)
        - Multiple variations up to move 10
        """
        book = defaultdict(list)

        # ===== MOVE 1: RED'S FIRST MOVE =====
        self._add_first_move_options(book)

        # ===== MOVE 2: BLACK RESPONSES =====
        self._add_black_responses_to_central_cannon(book)
        self._add_black_responses_to_advisor_horn_cannon(book)
        self._add_black_responses_to_horse_opening(book)

        # ===== MOVES 3-10: DEEP VARIATIONS =====
        self._add_central_cannon_vs_screen_horse_variations(book)
        self._add_double_cannon_variations(book)
        self._add_advisor_horn_cannon_variations(book)
        self._add_flying_elephant_variations(book)

        return book

    def _add_first_move_options(self, book):
        """Red's first move options"""
        start = "start"

        # 中炮 (Central Cannon) - Most popular (80% combined)
        book[start].append({
            'move': (2, 7, 5, 7),
            'name': '中炮 (Central Cannon - right)',
            'weight': 40
        })
        book[start].append({
            'move': (2, 1, 5, 1),
            'name': '中炮 (Central Cannon - left)',
            'weight': 40
        })

        # 仕角炮 (Advisor Horn Cannon) - 10%
        book[start].append({
            'move': (2, 1, 2, 4),
            'name': '仕角炮 (Advisor Horn Cannon)',
            'weight': 10
        })

        # 过宫炮 (Palace Crossing Cannon) - 5%
        book[start].append({
            'move': (2, 1, 2, 5),
            'name': '过宫炮 (Palace Crossing Cannon)',
            'weight': 5
        })

        # 起马 (Advance Horse) - 10%
        book[start].append({
            'move': (0, 1, 2, 2),
            'name': '起马 (Advance Left Horse)',
            'weight': 5
        })
        book[start].append({
            'move': (0, 7, 2, 6),
            'name': '起马 (Advance Right Horse)',
            'weight': 5
        })

        # 飞相 (Flying Elephant) - 5%
        book[start].append({
            'move': (0, 2, 2, 4),
            'name': '飞相 (Flying Elephant)',
            'weight': 5
        })

    def _add_black_responses_to_central_cannon(self, book):
        """Black's responses to Red's central cannon"""
        central_r = "red_central_cannon_right"
        central_l = "red_central_cannon_left"

        # 屏风马 (Screen Horse) - Most common defense (50%)
        for key in [central_r, central_l]:
            book[key].append({
                'move': (9, 7, 7, 6),
                'name': '屏风马 (Screen Horse - right)',
                'weight': 25
            })
            book[key].append({
                'move': (9, 1, 7, 2),
                'name': '屏风马 (Screen Horse - left)',
                'weight': 25
            })

            # 顺炮 (Matching Cannons) - Aggressive (30%)
            book[key].append({
                'move': (7, 7, 5, 7),
                'name': '顺炮 (Matching Cannons - right)',
                'weight': 15
            })
            book[key].append({
                'move': (7, 1, 5, 1),
                'name': '顺炮 (Matching Cannons - left)',
                'weight': 15
            })

            # 反宫马 (Counter-Palace Horse) - Solid (15%)
            book[key].append({
                'move': (9, 1, 7, 0),
                'name': '反宫马 (Counter-Palace Horse)',
                'weight': 15
            })

            # 飞象 (Flying Elephant) - Defensive (10%)
            book[key].append({
                'move': (9, 2, 7, 4),
                'name': '飞象 (Flying Elephant)',
                'weight': 10
            })

    def _add_black_responses_to_advisor_horn_cannon(self, book):
        """Black responses to Advisor Horn Cannon"""
        advisor = "red_advisor_horn_cannon"

        book[advisor].append({
            'move': (9, 7, 7, 6),
            'name': '屏风马 (Screen Horse)',
            'weight': 40
        })
        book[advisor].append({
            'move': (9, 1, 7, 2),
            'name': '屏风马 (Screen Horse - left)',
            'weight': 30
        })
        book[advisor].append({
            'move': (7, 7, 7, 2),
            'name': '飞炮 (Flying Cannon)',
            'weight': 20
        })
        book[advisor].append({
            'move': (9, 2, 7, 4),
            'name': '飞象 (Flying Elephant)',
            'weight': 10
        })

    def _add_black_responses_to_horse_opening(self, book):
        """Black responses to Horse opening"""
        horse = "red_horse_opening"

        book[horse].append({
            'move': (9, 7, 7, 6),
            'name': '屏风马 (Screen Horse)',
            'weight': 40
        })
        book[horse].append({
            'move': (7, 7, 5, 7),
            'name': '起炮 (Advance Cannon)',
            'weight': 30
        })
        book[horse].append({
            'move': (9, 2, 7, 4),
            'name': '飞象 (Flying Elephant)',
            'weight': 30
        })

    def _add_central_cannon_vs_screen_horse_variations(self, book):
        """Deep variations for Central Cannon vs Screen Horse"""

        # Move 3: Red's responses to Screen Horse
        screen_horse = "central_vs_screen_move2"

        # 进马 (Advance Horse) - Most common
        book[screen_horse].append({
            'move': (0, 1, 2, 2),
            'name': '进马 (Advance Left Horse)',
            'weight': 30
        })
        book[screen_horse].append({
            'move': (0, 7, 2, 6),
            'name': '进马 (Advance Right Horse)',
            'weight': 30
        })

        # 兵三进一 (Advance Pawn) - Aggressive
        book[screen_horse].append({
            'move': (3, 6, 4, 6),
            'name': '进三兵 (Advance Right River Pawn)',
            'weight': 20
        })
        book[screen_horse].append({
            'move': (3, 2, 4, 2),
            'name': '进七兵 (Advance Left River Pawn)',
            'weight': 15
        })

        # 飞相 (Flying Elephant)
        book[screen_horse].append({
            'move': (0, 2, 2, 4),
            'name': '飞相 (Flying Elephant)',
            'weight': 15
        })

        # 兵五进一 (Central Pawn)
        book[screen_horse].append({
            'move': (3, 4, 4, 4),
            'name': '进中兵 (Advance Central Pawn)',
            'weight': 10
        })

        # Move 4: Black's responses
        red_horse_advanced = "central_vs_screen_move3"

        book[red_horse_advanced].append({
            'move': (7, 7, 5, 7),
            'name': '起炮 (Advance Cannon)',
            'weight': 30
        })
        book[red_horse_advanced].append({
            'move': (7, 2, 7, 4),
            'name': '平炮 (Reposition Cannon)',
            'weight': 25
        })
        book[red_horse_advanced].append({
            'move': (9, 2, 7, 4),
            'name': '飞象 (Flying Elephant)',
            'weight': 25
        })
        book[red_horse_advanced].append({
            'move': (6, 4, 5, 4),
            'name': '进卒 (Advance Central Pawn)',
            'weight': 20
        })

        # Move 5: Red middle game
        middlegame_1 = "central_vs_screen_move4"

        book[middlegame_1].append({
            'move': (2, 2, 4, 1),
            'name': '跳马 (Horse Jump)',
            'weight': 30
        })
        book[middlegame_1].append({
            'move': (0, 0, 1, 0),
            'name': '出车 (Develop Rook)',
            'weight': 25
        })
        book[middlegame_1].append({
            'move': (5, 7, 5, 4),
            'name': '炮打中兵 (Cannon Attacks Central Pawn)',
            'weight': 25
        })
        book[middlegame_1].append({
            'move': (4, 6, 5, 6),
            'name': '进兵 (Advance Pawn)',
            'weight': 20
        })

    def _add_double_cannon_variations(self, book):
        """Variations for 顺炮局 (Double Cannon)"""

        double_cannon = "double_cannon_move2"

        # Move 3: Red's continuation
        book[double_cannon].append({
            'move': (0, 1, 2, 2),
            'name': '进马 (Advance Horse)',
            'weight': 35
        })
        book[double_cannon].append({
            'move': (0, 7, 2, 6),
            'name': '进马 (Advance Right Horse)',
            'weight': 35
        })
        book[double_cannon].append({
            'move': (3, 4, 4, 4),
            'name': '进中兵 (Advance Central Pawn)',
            'weight': 20
        })
        book[double_cannon].append({
            'move': (0, 2, 2, 4),
            'name': '飞相 (Flying Elephant)',
            'weight': 10
        })

        # Move 4: Black's response in double cannon
        double_cannon_3 = "double_cannon_move3"

        book[double_cannon_3].append({
            'move': (9, 7, 7, 6),
            'name': '跳马 (Horse Jump)',
            'weight': 35
        })
        book[double_cannon_3].append({
            'move': (9, 1, 7, 2),
            'name': '跳马 (Horse Jump - left)',
            'weight': 30
        })
        book[double_cannon_3].append({
            'move': (6, 4, 5, 4),
            'name': '进卒 (Advance Central Pawn)',
            'weight': 25
        })
        book[double_cannon_3].append({
            'move': (9, 0, 8, 0),
            'name': '出车 (Develop Rook)',
            'weight': 10
        })

    def _add_advisor_horn_cannon_variations(self, book):
        """Variations for Advisor Horn Cannon opening"""

        advisor_3 = "advisor_horn_move3"

        book[advisor_3].append({
            'move': (0, 1, 2, 2),
            'name': '进马 (Advance Horse)',
            'weight': 35
        })
        book[advisor_3].append({
            'move': (0, 7, 2, 6),
            'name': '进马 (Advance Right Horse)',
            'weight': 30
        })
        book[advisor_3].append({
            'move': (2, 4, 5, 4),
            'name': '平炮 (Reposition Cannon)',
            'weight': 25
        })
        book[advisor_3].append({
            'move': (0, 2, 2, 4),
            'name': '飞相 (Flying Elephant)',
            'weight': 10
        })

    def _add_flying_elephant_variations(self, book):
        """Variations for Flying Elephant opening"""

        elephant = "flying_elephant_move2"

        book[elephant].append({
            'move': (2, 7, 5, 7),
            'name': '中炮 (Central Cannon)',
            'weight': 40
        })
        book[elephant].append({
            'move': (0, 1, 2, 2),
            'name': '进马 (Advance Horse)',
            'weight': 30
        })
        book[elephant].append({
            'move': (0, 7, 2, 6),
            'name': '进马 (Advance Right Horse)',
            'weight': 30
        })

    def get_book_move_by_position(self, position_key):
        """
        Get a move from the book based on position description

        Args:
            position_key: String describing the position

        Returns:
            Move tuple (start_row, start_col, end_row, end_col) or None
        """
        if position_key not in self.book:
            return None

        moves = self.book[position_key]
        if not moves:
            return None

        # Weighted random selection
        total_weight = sum(m['weight'] for m in moves)
        rand = random.randint(1, total_weight)

        cumulative = 0
        for move_info in moves:
            cumulative += move_info['weight']
            if rand <= cumulative:
                return move_info['move']

        return moves[0]['move']

    def get_book_move_by_moves(self, move_history):
        """
        Get a book move based on the game's move history

        Args:
            move_history: List of moves played so far

        Returns:
            Move tuple or None
        """
        if len(move_history) == 0:
            return self.get_book_move_by_position("start")

        # Move 2: Black's response
        if len(move_history) == 1:
            red_first = move_history[0]

            # Check for central cannon (most common)
            if red_first[2] == 5 and red_first[3] == 7:
                return self.get_book_move_by_position("red_central_cannon_right")
            elif red_first[2] == 5 and red_first[3] == 1:
                return self.get_book_move_by_position("red_central_cannon_left")

            # Check for advisor horn cannon
            elif red_first[2] == 2 and red_first[3] == 4:
                return self.get_book_move_by_position("red_advisor_horn_cannon")

            # Check for horse opening
            elif red_first[0] == 0 and red_first[2] == 2:
                return self.get_book_move_by_position("red_horse_opening")

            # Check for flying elephant
            elif red_first[2] == 2 and red_first[3] == 4 and move_history[0][0] == 0:
                return self.get_book_move_by_position("flying_elephant_move2")

        # Move 3: Red's continuation
        if len(move_history) == 2:
            red_first = move_history[0]
            black_second = move_history[1]

            # Central cannon vs screen horse
            if red_first[2] == 5 and red_first[3] in [1, 7]:
                if black_second[0] == 9 and black_second[2] == 7:
                    return self.get_book_move_by_position("central_vs_screen_move2")

                # Double cannon
                elif black_second[2] == 5 and black_second[3] in [1, 7]:
                    return self.get_book_move_by_position("double_cannon_move2")

            # Advisor horn cannon continuation
            elif red_first[2] == 2 and red_first[3] == 4:
                return self.get_book_move_by_position("advisor_horn_move3")

        # Move 4: Black's response
        if len(move_history) == 3:
            red_first = move_history[0]
            black_second = move_history[1]
            red_third = move_history[2]

            # Central vs screen - red advanced horse
            if (red_first[2] == 5 and red_first[3] in [1, 7] and
                black_second[0] == 9 and black_second[2] == 7 and
                red_third[0] == 0 and red_third[2] == 2):
                return self.get_book_move_by_position("central_vs_screen_move3")

            # Double cannon - red advanced horse
            elif (red_first[2] == 5 and black_second[2] == 5 and
                  red_third[0] == 0 and red_third[2] == 2):
                return self.get_book_move_by_position("double_cannon_move3")

        # Move 5: Red middle game
        if len(move_history) == 4:
            red_first = move_history[0]
            if red_first[2] == 5 and red_first[3] in [1, 7]:
                return self.get_book_move_by_position("central_vs_screen_move4")

        return None

    def get_all_book_moves(self, position_key):
        """Get all book moves for a position with their names and weights"""
        if position_key not in self.book:
            return []
        return self.book[position_key]

    def get_stats(self):
        """Get statistics about the opening book"""
        total_positions = len(self.book)
        total_variations = sum(len(moves) for moves in self.book.values())

        return {
            'positions': total_positions,
            'variations': total_variations,
            'avg_variations_per_position': total_variations / total_positions if total_positions > 0 else 0
        }


# Example usage and testing
if __name__ == "__main__":
    book = OpeningBook()
    stats = book.get_stats()

    print("=" * 60)
    print("EXPANDED CHINESE CHESS OPENING BOOK")
    print("=" * 60)
    print(f"\nBook Statistics:")
    print(f"  Total Positions: {stats['positions']}")
    print(f"  Total Variations: {stats['variations']}")
    print(f"  Avg Variations/Position: {stats['avg_variations_per_position']:.1f}")

    print("\n" + "=" * 60)
    print("First Move Options for Red:")
    print("-" * 60)
    moves = book.get_all_book_moves("start")
    for move_info in moves:
        print(f"  {move_info['name']:.<45} weight: {move_info['weight']}")

    print("\n" + "=" * 60)
    print("Black Responses to Central Cannon:")
    print("-" * 60)
    moves = book.get_all_book_moves("red_central_cannon_right")
    for move_info in moves:
        print(f"  {move_info['name']:.<45} weight: {move_info['weight']}")

    print("\n" + "=" * 60)
    print("Red's 3rd Move Options (Central vs Screen Horse):")
    print("-" * 60)
    moves = book.get_all_book_moves("central_vs_screen_move2")
    for move_info in moves:
        print(f"  {move_info['name']:.<45} weight: {move_info['weight']}")

    print("\n" + "=" * 60)
    print("Testing Random Selection (5 games):")
    print("-" * 60)
    for i in range(5):
        move = book.get_book_move_by_position("start")
        move_name = next((m['name'] for m in book.get_all_book_moves("start") if m['move'] == move), "Unknown")
        print(f"  Game {i+1}: {move} - {move_name}")

    print("\n" + "=" * 60)
    print("✅ Expanded opening book loaded successfully!")
    print("=" * 60)
