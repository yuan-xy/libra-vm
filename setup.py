import setuptools
import hashlib
import re

with open("README.md", "r") as fh:
    content = fh.read()
    arr = content.split("\n")
    long_description = "\n".join(arr[3:])


with open("libra_vm/version.py", "r") as fp:
    try:
        version = re.findall(
            r"^version = \"([0-9\.]+)\"", fp.read(), re.M
        )[0]
    except IndexError:
        raise RuntimeError("Unable to determine version.")


install_requires=[
    'canoser>=0.8.2',
    'libra-core==0.8.4',
    "python-graph-core",
    "dataclasses-json",
    "multiaddr",
]

tests_require = [
    'pytest',
]


setuptools.setup(
    name="libra-vm",
    version=version,
    author="yuan xinyu",
    author_email="yuan_xin_yu@hotmail.com",
    description="Libra Virtual Machine for Move Language",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yuan_xy/libra-vm.git",
    packages=setuptools.find_packages(),
    include_package_data=True,
    install_requires=install_requires,
    tests_require=tests_require,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)
