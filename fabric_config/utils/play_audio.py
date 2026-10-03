from fabric_config.utils.process import run_command_async


def play_sound(file: str):
    # argv, not a shell string: paths with spaces work
    run_command_async(["play", "-q", file])
