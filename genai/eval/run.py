"""CLI dispatcher: python genai/eval/run.py <snapshot|questions|chat|advisory|mutation|judge-windows|judge|report> [...]"""

import importlib
import sys

COMMANDS = {
    "snapshot": ("snapshot", "main"),
    "questions": ("build_questions", "main"),
    "chat": ("chat_eval", "main"),
    "advisory": ("advisory_eval", "main"),
    "mutation": ("mutation_eval", "main"),
    "judge-windows": ("judge_windows", "main"),
    "judge": ("judge_eval", "main"),
    "report": ("report", "main"),
}

if __name__ == "__main__":
    import common  # noqa: F401  (sets sys.path)

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    mod, fn = COMMANDS[sys.argv[1]]
    getattr(importlib.import_module(mod), fn)(sys.argv[2:])
