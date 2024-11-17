from fabric.utils import exec_shell_command_async


def play_sound(file: str):
    print(file)
    exec_shell_command_async(f"play {file}", None)
