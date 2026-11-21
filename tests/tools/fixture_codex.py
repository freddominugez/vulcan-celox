"""PTY sensor fixture. Bracketed paste accumulates a draft, and a separate Enter saves it."""

import os
import sys
import termios
import tty
from pathlib import Path

START = b"\x1b[200~"
END = b"\x1b[201~"


def run(destination):
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    tty.setraw(fd)
    try:
        sys.stdout.write("\x1b[?2004hFixture Codex pronta\r\n")
        sys.stdout.flush()
        draft = bytearray()
        while True:
            value = os.read(fd, 1)
            if not value or value == b"\x03":
                return
            if value == b"\r" and draft.endswith(END) and draft.startswith(START):
                text = draft[len(START):-len(END)].decode("utf-8").replace("\r", "\n")
                temporary = destination.with_suffix(".writing")
                temporary.write_text(text, encoding="utf-8")
                temporary.replace(destination)
                draft.clear()
            else:
                draft.extend(value)
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, previous)


if __name__ == "__main__":
    run(Path(sys.argv[1]))
