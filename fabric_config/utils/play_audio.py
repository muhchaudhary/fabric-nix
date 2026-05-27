from fabric.utils import exec_shell_command_async


def play_sound(file: str):
    exec_shell_command_async(f"play {file}", None)
