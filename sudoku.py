#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sudoku

/ᐠ > ˕ <マ ₊˚⊹♡

Made by @literal-gargoyle

Controls
  Arrow keys .. Move cursor
  1-9 ......... Enter digit
  0/Backspace . Clear cell
  Enter/Space . Fill cell (with current number)
  U .......... Undo
  H .......... Hint (fill one cell)
  S .......... Settings
  N .......... New game
  Q .......... Quit
"""

import os, sys, json, time, random, locale, subprocess
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field

# ------------------------------------------------------------
# Dependency bootstrap (for Windows): install windows-curses
# ------------------------------------------------------------

def _ensure_curses():
    try:
        import curses
        return
    except Exception as e:
        if os.name == 'nt':
            try:
                print("Installing windows-curses ...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
            except Exception:
                pass
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "windows-curses"])
            except Exception as ie:
                print("Couldn't install windows-curses automatically. Please run: pip install windows-curses")
                print("Error:", ie)
                raise
        else:
            raise e
_ensure_curses()
import curses

# ------------------------------------------------------------
# Paths & persistence
# ------------------------------------------------------------
APP_DIR = os.path.join(os.path.expanduser("~"), ".sudoku_cmd")
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
DEFAULT_SETTINGS = {
    "theme": "classic",       # classic | high_contrast | green | blue
    "ascii_only": False,      # force ASCII fallback for box drawing
    "show_hints": True,
    "animations": False,
}

if not os.path.isdir(APP_DIR):
    os.makedirs(APP_DIR, exist_ok=True)

def load_settings() -> Dict[str, Any]:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # merge with defaults
        for k, v in DEFAULT_SETTINGS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings: Dict[str, Any]) -> None:
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass

# ------------------------------------------------------------
# Sudoku Model & Generator
# ------------------------------------------------------------

@dataclass
class Cell:
    value: int = 0         # current value (0=empty)
    fixed: bool = False    # was in puzzle or not
    pencil: int = 0        # candidate value (for hint)

@dataclass
class SudokuState:
    grid: List[List[Cell]] = field(default_factory=lambda: [[Cell() for _ in range(9)] for _ in range(9)])
    puzzle: List[List[int]] = field(default_factory=lambda: [[0]*9 for _ in range(9)])
    solution: List[List[int]] = field(default_factory=lambda: [[0]*9 for _ in range(9)])
    moves: int = 0
    start_time: float = 0.0

    def clone(self) -> 'SudokuState':
        gs = SudokuState()
        gs.grid = [[Cell(c.value, c.fixed, c.pencil) for c in row] for row in self.grid]
        gs.puzzle = [row[:] for row in self.puzzle]
        gs.solution = [row[:] for row in self.solution]
        gs.moves = self.moves
        gs.start_time = self.start_time
        return gs

def valid(grid, r, c, n):
    for i in range(9):
        if grid[r][i] == n or grid[i][c] == n:
            return False
    br, bc = 3*(r//3), 3*(c//3)
    for i in range(3):
        for j in range(3):
            if grid[br+i][bc+j] == n:
                return False
    return True

def solve(grid, fill=False):
    for r in range(9):
        for c in range(9):
            if grid[r][c] == 0:
                for n in random.sample(range(1,10),9) if fill else range(1,10):
                    if valid(grid, r, c, n):
                        grid[r][c] = n
                        if solve(grid, fill):
                            return True
                        grid[r][c] = 0
                return False
    return True

def generate_sudoku(num_clues=35) -> Tuple[List[List[int]], List[List[int]]]:
    grid = [[0]*9 for _ in range(9)]
    solve(grid, fill=True)
    sol = [row[:] for row in grid]
    # Remove cells
    cells = [(r, c) for r in range(9) for c in range(9)]
    random.shuffle(cells)
    removed = 0
    for r, c in cells:
        if removed >= 81-num_clues:
            break
        backup = grid[r][c]
        grid[r][c] = 0
        grid2 = [row[:] for row in grid]
        if not unique_solution(grid2):
            grid[r][c] = backup
        else:
            removed += 1
    puzzle = [row[:] for row in grid]
    return puzzle, sol

def unique_solution(grid):
    # Returns True if the puzzle has a unique solution
    solutions = [0]
    def dfs():
        for r in range(9):
            for c in range(9):
                if grid[r][c] == 0:
                    for n in range(1,10):
                        if valid(grid, r, c, n):
                            grid[r][c] = n
                            dfs()
                            grid[r][c] = 0
                    return
        solutions[0] += 1
    dfs()
    return solutions[0] == 1

def new_game() -> SudokuState:
    puzzle, sol = generate_sudoku()
    gs = SudokuState()
    for r in range(9):
        for c in range(9):
            gs.grid[r][c].value = puzzle[r][c]
            gs.grid[r][c].fixed = puzzle[r][c] != 0
    gs.puzzle = puzzle
    gs.solution = sol
    gs.moves = 0
    gs.start_time = time.monotonic()
    return gs

def is_complete(gs: SudokuState):
    for r in range(9):
        for c in range(9):
            v = gs.grid[r][c].value
            if v == 0 or v != gs.solution[r][c]:
                return False
    return True

# ------------------------------------------------------------
# Curses UI
# ------------------------------------------------------------

class UI:
    def __init__(self, stdscr, settings):
        self.stdscr = stdscr
        self.settings = settings
        self.ascii_only = settings.get("ascii_only", False) or not self._supports_unicode()
        self.theme = settings.get("theme", "classic")
        self.status_msg = ""
        self.cursor = (0, 0) # (row, col)

    def _supports_unicode(self):
        try:
            enc = locale.getpreferredencoding(False) or "utf-8"
            "│".encode(enc, errors="strict")
            return True
        except Exception:
            return False

    def init_colors(self):
        curses.start_color()
        curses.use_default_colors()
        # color pairs: 1 default, 2 red, 3 highlight, 4 dim, 5 accent
        base_fg = self._theme_color()
        curses.init_pair(1, base_fg, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.init_pair(4, curses.COLOR_CYAN, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

    def _theme_color(self):
        if self.theme == "green":
            return curses.COLOR_GREEN
        if self.theme == "blue":
            return curses.COLOR_BLUE
        if self.theme == "high_contrast":
            return curses.COLOR_WHITE
        return curses.COLOR_WHITE

    def draw(self, gs: SudokuState):
        self.stdscr.erase()
        maxy, maxx = self.stdscr.getmaxyx()
        # title and stats
        title = "Sudoku - made with ❤ by literal-gargoyle"
        self.stdscr.addstr(0, 2, title, curses.color_pair(4) | curses.A_BOLD)
        elapsed = int(time.monotonic() - gs.start_time)
        mins, secs = divmod(max(elapsed, 0), 60)
        stats = f"Time {mins:02d}:{secs:02d}  Moves {gs.moves}  H for hint  S settings"
        self.stdscr.addstr(1, 2, stats, curses.color_pair(1))
        if self.status_msg:
            self.stdscr.addstr(2, 2, self.status_msg[:max(0, maxx-4)], curses.color_pair(5))
        # draw sudoku grid
        y0, x0 = 4, 4
        for r in range(9):
            for c in range(9):
                cell = gs.grid[r][c]
                selected = (self.cursor == (r, c))
                fixed = cell.fixed
                v = cell.value
                ch = str(v) if v != 0 else "."
                color = 2 if fixed else 1
                attr = curses.color_pair(color)
                if selected:
                    attr |= curses.A_REVERSE
                try:
                    self.stdscr.addstr(y0 + r*2, x0 + c*4, f" {ch} ", attr)
                except curses.error:
                    pass
            # horizontal lines
            if r % 3 == 2 and r != 8:
                try:
                    self.stdscr.addstr(y0 + r*2 + 1, x0, self._hline(37), curses.color_pair(4))
                except curses.error:
                    pass
        # vertical lines
        if not self.ascii_only:
            for i in range(1, 3):
                for rr in range(19):
                    try:
                        self.stdscr.addstr(y0-1 + rr, x0 + i*12, "│", curses.color_pair(4))
                    except curses.error:
                        pass
        if is_complete(gs):
            msg = "SUDOKU SOLVED! Press N for new game."
            self._center_banner(msg, color=5)
        self.stdscr.refresh()

    def _hline(self, width):
        if self.ascii_only:
            return "-"*width
        return "─"*width

    def _center_banner(self, msg: str, color=4):
        maxy, maxx = self.stdscr.getmaxyx()
        y = maxy//2
        x = max(0, (maxx - len(msg))//2)
        try:
            self.stdscr.addstr(y, x, msg, curses.color_pair(color) | curses.A_BOLD)
        except curses.error:
            pass

# ------------------------------------------------------------
# Menus
# ------------------------------------------------------------

def show_settings(stdscr, settings: Dict[str, Any]) -> bool:
    opts = [
        ("Theme", ["classic", "high_contrast", "green", "blue"]),
        ("ASCII box", ["Off", "On"]),
        ("Show hints", ["Off", "On"]),
        ("Animations", ["Off", "On"]),
    ]
    idxs = {
        0: ["classic","high_contrast","green","blue"].index(settings['theme']),
        1: 1 if settings['ascii_only'] else 0,
        2: 1 if settings['show_hints'] else 0,
        3: 1 if settings['animations'] else 0,
    }
    sel = 0
    changed = False

    while True:
        stdscr.erase()
        maxy, maxx = stdscr.getmaxyx()
        title = "Settings — arrows to change, Enter to toggle, Q to exit"
        stdscr.addstr(1, max(0,(maxx-len(title))//2), title, curses.color_pair(4) | curses.A_BOLD)
        y = 4
        for i, (name, choices) in enumerate(opts):
            current = None
            if i == 0:
                current = settings['theme']
            elif i == 1:
                current = "On" if settings['ascii_only'] else "Off"
            elif i == 2:
                current = "On" if settings['show_hints'] else "Off"
            elif i == 3:
                current = "On" if settings['animations'] else "Off"
            row = f"{name:<14}: {current}"
            attr = curses.A_REVERSE if i==sel else 0
            stdscr.addstr(y+i, 4, row, curses.color_pair(1) | attr)
        ch = stdscr.getch()
        if ch in (ord('q'), ord('Q')):
            break
        elif ch in (curses.KEY_UP,):
            # Im so fucking retarded bro
            sel = (sel - 1) % len(opts)
        elif ch in (curses.KEY_DOWN,):
            sel = (sel + 1) % len(opts)
        elif ch in (curses.KEY_LEFT):
            changed = True
            if sel == 0:
                themes = ["classic","high_contrast","green","blue"]
                settings['theme'] = themes[(themes.index(settings['theme']) - 1) % len(themes)]
            elif sel == 1:
                settings['ascii_only'] = not settings['ascii_only']
            elif sel == 2:
                settings['show_hints'] = not settings['show_hints']
            elif sel == 3:
                settings['animations'] = not settings['animations']
        elif ch in (curses.KEY_RIGHT, ord('l'), 10, 13):
            changed = True
            if sel == 0:
                themes = ["classic","high_contrast","green","blue"]
                settings['theme'] = themes[(themes.index(settings['theme']) + 1) % len(themes)]
            elif sel == 1:
                settings['ascii_only'] = not settings['ascii_only']
            elif sel == 2:
                settings['show_hints'] = not settings['show_hints']
            elif sel == 3:
                settings['animations'] = not settings['animations']
    return changed

# ------------------------------------------------------------
# Main game loop
# ------------------------------------------------------------

class Game:
    def __init__(self, stdscr, settings):
        self.stdscr = stdscr
        self.settings = settings
        self.ui = UI(stdscr, settings)
        self.ui.init_colors()
        self.state = new_game()
        self.undo_stack: List[SudokuState] = []

    def push_undo(self):
        self.undo_stack.append(self.state.clone())
        if len(self.undo_stack) > 200:
            self.undo_stack.pop(0)

    def undo(self):
        if self.undo_stack:
            self.state = self.undo_stack.pop()

    def game_loop(self):
        curses.curs_set(0)
        self.stdscr.nodelay(False)
        cur_r, cur_c = self.ui.cursor
        while True:
            self.ui.draw(self.state)
            ch = self.stdscr.getch()
            if ch in (ord('q'), ord('Q')):
                break
            elif ch in (curses.KEY_LEFT,):
                cur_r, cur_c = self.ui.cursor
                self.ui.cursor = (cur_r, (cur_c-1)%9)
            elif ch in (curses.KEY_RIGHT,):
                cur_r, cur_c = self.ui.cursor
                self.ui.cursor = (cur_r, (cur_c+1)%9)
            elif ch in (curses.KEY_UP,):
                cur_r, cur_c = self.ui.cursor
                self.ui.cursor = ((cur_r-1)%9, cur_c)
            elif ch in (curses.KEY_DOWN,):
                cur_r, cur_c = self.ui.cursor
                self.ui.cursor = ((cur_r+1)%9, cur_c)
            elif ch in (ord('n'), ord('N')):
                self.state = new_game()
                self.undo_stack.clear()
            elif ch in (ord('u'), ord('U')):
                self.undo()
            elif ch in (ord('s'), ord('S')):
                if show_settings(self.stdscr, self.settings):
                    save_settings(self.settings)
                    self.ui = UI(self.stdscr, self.settings)
                    self.ui.init_colors()
            elif ch in (ord('h'), ord('H')):
                self.hint()
            elif ch in (10, 13, ord(' ')):
                # fill with pencil value if present
                cur_r, cur_c = self.ui.cursor
                cell = self.state.grid[cur_r][cur_c]
                if not cell.fixed and cell.pencil:
                    self.push_undo()
                    cell.value = cell.pencil
                    cell.pencil = 0
                    self.state.moves += 1
            elif ch in (curses.KEY_BACKSPACE, 127, ord('0')):
                cur_r, cur_c = self.ui.cursor
                cell = self.state.grid[cur_r][cur_c]
                if not cell.fixed and cell.value != 0:
                    self.push_undo()
                    cell.value = 0
                    cell.pencil = 0
                    self.state.moves += 1
            elif ord('1') <= ch <= ord('9'):
                cur_r, cur_c = self.ui.cursor
                cell = self.state.grid[cur_r][cur_c]
                if not cell.fixed:
                    self.push_undo()
                    v = ch - ord('0')
                    cell.value = v
                    cell.pencil = 0
                    self.state.moves += 1
            # ignore others

    def hint(self):
        #Updated hint function, no longer just chooses the first option, finds all, then chooses one a random
        if not self.settings.get('show_hints', True):
            self.ui.status_msg = "Hints are disabled in Settings."
            return
        # Collect all available cells
        available_cells = [
            (r, c) for r in range(9) for c in range(9)
            if not self.state.grid[r][c].fixed and self.state.grid[r][c].value == 0
        ]
        if available_cells:
            r, c = random.choice(available_cells)
            cell = self.state.grid[r][c]
            cell.pencil = self.state.solution[r][c]
            self.ui.status_msg = f"Hint: try {cell.pencil} at ({r+1},{c+1})"
            self.ui.cursor = (r, c)
            return
        self.ui.status_msg = "No hints: puzzle already complete!"

# ------------------------------------------------------------
# Entry point
# ------------------------------------------------------------

def main(stdscr):
    settings = load_settings()
    game = Game(stdscr, settings)
    game.game_loop()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass

