import os, json
from os import listdir
from os.path import isfile, join, abspath, dirname


def main():
    path = "./mol/stdlib/modules/"
    mvs = [f for f in listdir(path) if f.endswith(".mv") or f.endswith(".mvsm")]
    for mv in mvs:
        newf = mv.split("_")[-1] # rename transaction_0_module_Signature.mv to Signature.mv
        if newf != mv:
            os.rename(join(path, mv), join(path, newf))

if __name__ == '__main__':
    main()
