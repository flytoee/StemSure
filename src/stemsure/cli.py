"""Canonical CLI for the current StemSure release."""


def main() -> None:
    from stemsure_reliable.cli import main as reliable_main
    reliable_main()
