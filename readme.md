# What is this?
This is my repo for getting fabric to work in nixOS, hassle free. You can find the derrivation for fabric in the nix folder.

I also have my personal config for fabric located in the `fabric` folder. If you want to start fresh, you can clone the `fresh-env` branch

# How to set up

* The provided flake.nix will create a development shell with all the dependincies you need to use fabric. **ADD INFO ON WHY WE NEED THIS HERE**
* By default, a direnv will need to be rebuild on each reload, I reccomded setting up [nix-direnv](https://github.com/nix-community/nix-direnv) to cache the nix-shell

1. run `direnv allow` in your terminal
2. your terminal should automatically build and load into the development environment.
3. Start developing your widgets!

**TIP:** If you want to use this devshell outside of this directory, in a script for example, you can use a script like this:

```bash
#!/usr/bin/env bash

function direnv_cd() {
  cd "$1"
  eval "$(direnv export bash)"
}

direnv_cd /PATH/TO/DIRENV/DIRECTORY

# commands here will be ran from the development environment

```
(This works with subdirectories as well)

**TIP:** Since fabric is not installed globally, you will not be able to do `python -m fabric` to send commands to the fabric dbus service. You can do the following instead (I put mine in a script)

```bash
#!/usr/bin/env bash

dbus-send --session --print-reply --dest=org.Fabric.fabric  /org/Fabric/fabric org.Fabric.fabric.Evaluate string:"$1"  > /dev/null 2>&1
```

# Fixing python autocompletions and type checking.

You might have noticed that your gi.repository imports are
missing type checking and autocompletions. Unfortunately there
isn't a perfect solution for this. The issue stems from how
girepostiory handles python. In order to fix this,
I use [fakegir](https://github.com/strycore/fakegir/tree/master).
I made a small tweak to the script to make it work on nixOS however:
```python
# Replace starting from line 18 to line 23
GIR_PATHS = []

GIR_PATH = os.environ.get("XDG_DATA_DIRS")
GIR_PATH = GIR_PATH.split(":")


for path in GIR_PATH:
    if os.path.exists(path + "/gir-1.0"):
        GIR_PATHS.append(path + "/gir-1.0")
```

You can also read more about this issue on the fabric wiki:
[Getting a Stub Package](https://fabric-development.github.io/fabric-wiki/installing-stubs.html)
