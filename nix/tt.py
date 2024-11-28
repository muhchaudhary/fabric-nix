import os
import subprocess
import sys
GIR_PATHS = []


GIR_PATH: str = os.environ.get("nativeBuildInputs")

seen_gir = []
for buildinput in GIR_PATH.split(" "):
    test_path= buildinput + "/share/gir-1.0"
    if os.path.exists(test_path):
        for f in os.listdir(test_path):
            if (
                os.path.isfile(f"{test_path}/{f}")
                and f not in seen_gir
                and f.endswith(".gir")
            ):
                seen_gir.append(f)
                GIR_PATHS.append(f"{test_path}/{f}")


acc = ["gengir"]
acc.extend(["-o", f"/home/{os.environ.get('USERNAME')}/.local/lib/python3.11/site-packages/gi"])
acc.extend(GIR_PATHS)
subprocess.run(acc)

# print(sys.argv)