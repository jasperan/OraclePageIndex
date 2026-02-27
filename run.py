#!/usr/bin/env python3
"""Convenience entry point for running OraclePageIndex from the project root.

All logic lives in ``oracle_pageindex.cli``; this file simply delegates so
that ``python run.py <subcommand>`` works identically to the installed
``oracle-pageindex`` console script.
"""

from oracle_pageindex.cli import main

if __name__ == "__main__":
    main()
