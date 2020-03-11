import sys, os, json
from os import listdir
from os.path import isfile, join, abspath, dirname
import subprocess


def batch_of_dir(extern_dir):
    curdir = dirname(__file__)
    path = join(curdir, extern_dir)
    for root, dirs, files in os.walk(path):
        for file in files:
            if(file.endswith(".rs")):
                rs_src = abspath(join(root,file))
                print(rs_src)
                cmds = ["/bin/bash", "/usr/bin/rust2py.sh", rs_src]
                subprocess.run(cmds)
                py_src = rs_src[0:-3] + ".py"
                cmds = ["mv", rs_src, py_src]
                subprocess.run(cmds)
                #subprocess.run(cmds, cwd=curdir, check=True)
            elif file.endswith(".py"):
                rs_src = abspath(join(root,file))
                print(rs_src)
                cmds = ["/bin/bash", "/usr/bin/rust2py.sh", rs_src]
                subprocess.run(cmds)

def main():
    if len(sys.argv) <= 1:
        print(f"Usage: python3 {sys.argv[0]} dir")
        return
    rust_dir = sys.argv[1]
    batch_of_dir(rust_dir)


if __name__ == '__main__':
    main()
