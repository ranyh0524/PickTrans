"""端到端交互测试辅助：注入真实鼠标/键盘事件。

用法：
  python tools/e2e_click.py dbl <x> <y>            双击
  python tools/e2e_click.py click <x> <y>          单击
  python tools/e2e_click.py drag <x1> <y1> <x2> <y2>  拖选
  python tools/e2e_click.py hotkey <combo>         热键，如 ctrl+alt+o
  python tools/e2e_click.py esc                    按 Esc
"""
import sys
import time

from pynput.keyboard import Controller as Kb, Key
from pynput.mouse import Button, Controller

m = Controller()
kb = Kb()


def dbl(x, y):
    m.position = (int(x), int(y))
    time.sleep(0.4)
    m.click(Button.left, 2)
    print(f"double-clicked ({x},{y})", flush=True)


def click(x, y):
    m.position = (int(x), int(y))
    time.sleep(0.3)
    m.click(Button.left, 1)
    print(f"clicked ({x},{y})", flush=True)


def drag(x1, y1, x2, y2):
    m.position = (int(x1), int(y1))
    time.sleep(0.4)
    m.press(Button.left)
    steps = max(6, int(abs(x2 - x1) / 20))
    for i in range(1, steps + 1):
        m.position = (int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
        time.sleep(0.012)
    m.release(Button.left)
    print(f"dragged ({x1},{y1}) -> ({x2},{y2})", flush=True)


KEY_NAMES = {"ctrl": Key.ctrl, "alt": Key.alt, "shift": Key.shift, "win": Key.cmd}


def hotkey(combo):
    parts = [KEY_NAMES.get(p.strip().lower(), p.strip()) for p in combo.split("+")]
    held = []
    for p in parts[:-1]:
        kb.press(p)
        held.append(p)
    time.sleep(0.05)
    last = parts[-1]
    kb.tap(last if isinstance(last, Key) else last[0])
    for p in reversed(held):
        kb.release(p)
    print(f"hotkey {combo} injected", flush=True)


def esc():
    kb.tap(Key.esc)
    print("esc injected", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    args = sys.argv[2:]
    if cmd == "dbl":
        dbl(*args)
    elif cmd == "click":
        click(*args)
    elif cmd == "drag":
        drag(*map(float, args))
    elif cmd == "hotkey":
        hotkey(args[0])
    elif cmd == "esc":
        esc()
    else:
        print(__doc__)
