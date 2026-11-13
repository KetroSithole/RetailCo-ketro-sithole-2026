"""RetailCo ETL

    python main.py setup     create the databases RETAIL_STG and RETAIL_DWH (run once)
    python main.py extract   download the source CSV into the inbox
    python main.py run       inbox -> RETAIL_STG -> RETAIL_DWH, then move the file to archive
    python main.py report    run the business queries -> output/report_<environment>.md

Add --env prod to use .config/prod.env (default: ENVIRONMENT in .config/settings.env).
"""
import argparse
import sys

from etl import pipeline
from etl.settings import Settings

COMMANDS = {
    "setup": pipeline.setup,
    "extract": pipeline.extract,
    "run": pipeline.run,
    "report": pipeline.report,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--env", help="environment name, e.g. dev or prod")
    arguments = parser.parse_args()

    settings = Settings(arguments.env)
    print(f"{arguments.command}: {settings}")

    result = COMMANDS[arguments.command](settings)
    return 1 if result is False else 0


if __name__ == "__main__":
    sys.exit(main())
