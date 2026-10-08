"""Entry point: sets up logging before `main` is imported, since services log
as they're imported."""

from fabric_config.utils.log import setup_logging

setup_logging()


def main():
    from fabric_config.main import main

    main()
