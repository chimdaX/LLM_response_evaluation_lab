"""Small, testable prompt helpers for the interactive collection and annotation tools.

All terminal I/O goes through a ``Console`` so tests can drive the workflows with a
scripted list of answers instead of a real keyboard.
"""

from __future__ import annotations

import textwrap
from collections.abc import Callable, Iterable
from datetime import date
from typing import Protocol


class Console(Protocol):
    def say(self, text: str = "") -> None: ...

    def ask(self, prompt: str) -> str: ...


class TerminalConsole:
    """Real terminal I/O. ``input`` raises EOFError / KeyboardInterrupt on Ctrl+D / Ctrl+C."""

    def say(self, text: str = "") -> None:
        print(text)

    def ask(self, prompt: str) -> str:
        return input(prompt)


class ScriptedConsole:
    """Feeds pre-recorded answers; records everything shown. Used by the test-suite."""

    def __init__(self, answers: Iterable[str]) -> None:
        self._answers = iter(answers)
        self.output: list[str] = []

    def say(self, text: str = "") -> None:
        self.output.append(text)

    def ask(self, prompt: str) -> str:
        self.output.append(prompt)
        try:
            return next(self._answers)
        except StopIteration:
            # Behave like a closed terminal so "interrupted session" paths can be tested.
            raise EOFError from None

    @property
    def text(self) -> str:
        return "\n".join(self.output)


def wrap(text: str, indent: str = "    ", width: int = 96) -> str:
    """Wrap each paragraph for display while keeping the author's line breaks."""
    lines = []
    for line in text.splitlines() or [""]:
        lines.append(
            textwrap.fill(line, width, initial_indent=indent, subsequent_indent=indent)
            if line.strip()
            else indent.rstrip()
        )
    return "\n".join(lines)


def ask_text(
    console: Console, prompt: str, *, required: bool = True, default: str | None = None
) -> str | None:
    """Ask for one line of text. Empty input returns ``default`` (or re-asks if required)."""
    suffix = f" [{default}]" if default else ""
    while True:
        value = console.ask(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        if not required:
            return None
        console.say("  A response is required here.")


def ask_multiline(console: Console, prompt: str) -> str | None:
    """Collect several lines until a line containing only '.'; '.' alone means none."""
    console.say(f"{prompt} (finish with a line containing only '.'; enter '.' alone to skip)")
    lines: list[str] = []
    while True:
        line = console.ask("> ")
        if line.strip() == ".":
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    return text or None


def ask_choice(
    console: Console, prompt: str, choices: dict[str, str], *, default: str | None = None
) -> str:
    """Ask until the answer is one of ``choices`` (keys are typed, values are returned)."""
    options = "/".join(f"[{k}]" if k == default else k for k in choices)
    while True:
        value = console.ask(f"{prompt} ({options}): ").strip().lower()
        if not value and default is not None:
            value = default
        if value in choices:
            return choices[value]
        console.say(f"  Please enter one of: {', '.join(choices)}.")


def ask_yes_no(console: Console, prompt: str, *, default: bool = False) -> bool:
    return (
        ask_choice(console, prompt, {"y": "yes", "n": "no"}, default="y" if default else "n")
        == "yes"
    )


def ask_date(console: Console, prompt: str, *, default: date, latest: date) -> date:
    """Ask for a YYYY-MM-DD date that is not later than ``latest``."""
    while True:
        raw = ask_text(console, prompt, default=default.isoformat())
        try:
            value = date.fromisoformat(raw or "")
        except ValueError:
            console.say("  Use the format YYYY-MM-DD.")
            continue
        if value > latest:
            console.say(f"  The date cannot be later than {latest.isoformat()}.")
            continue
        return value


def ask_validated(console: Console, prompt: str, check: Callable[[str], str | None]) -> str:
    """Ask until ``check`` returns no error message for the (stripped) answer."""
    while True:
        value = console.ask(f"{prompt}: ").strip()
        problem = check(value)
        if problem is None:
            return value
        console.say(f"  {problem}")
