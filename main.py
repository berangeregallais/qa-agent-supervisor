"""Point d'entrée CLI.

Usage :
  python main.py "spécification en langage naturel"
  python main.py "" --tests tests/test_homepage.py::test_homepage_loads[chromium]
  python main.py "" --tests tests/test_homepage.py::test1 --tests tests/test_homepage.py::test2
"""

import argparse

from orchestrator.runner import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("specification", nargs="?", default="", help="Spécification en langage naturel (optionnelle)")
    parser.add_argument(
        "--tests",
        action="append",
        default=[],
        help="Node ID pytest à exécuter (répétable). Omis = toute la suite.",
    )
    args = parser.parse_args()

    report = run_pipeline(specification=args.specification, selected_tests=args.tests)

    print("\n" + "=" * 72)
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
