"""Executa uma pergunta real e informa a latência total da pipeline ACTA."""

import argparse
import json
import sys
from time import perf_counter
from uuid import uuid4

from pipeline import get_response


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="Pergunta enviada ao chatbot.")
    parser.add_argument("--id-ciclo", type=int, default=None)
    parser.add_argument("--session-id", default=f"benchmark::{uuid4()}")
    args = parser.parse_args()

    started = perf_counter()
    answer = get_response(
        message=args.question,
        session_id=args.session_id,
        id_ciclo=args.id_ciclo,
    )
    elapsed_seconds = perf_counter() - started

    print(
        json.dumps(
            {
                "session_id": args.session_id,
                "elapsed_seconds": round(elapsed_seconds, 2),
                "answer": answer,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
