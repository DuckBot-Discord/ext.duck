from setuptools import setup

version = "1.0b"

# append version identifier based on commit count
try:
    import subprocess

    p = subprocess.Popen(["git", "rev-list", "--count", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    if out:
        version += out.decode("utf-8").strip()
    p = subprocess.Popen(["git", "rev-parse", "--short", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    if out:
        version += "+g" + out.decode("utf-8").strip()
except Exception:
    pass

readme = ""
with open("README.md") as f:
    readme = f.read()


packages = [
    "discord.ext.duck.errors",
    "discord.ext.duck.webserver",
]

setup(
    name="discord-ext-duck",
    author="LeoCx1000",
    url="https://github.com/DuckBot-Discord/ext.duck",
    version=version,
    packages=packages,
    license="Mozilla Public License v2.0",
    description="Utility extensions for DuckBot and it's sister projects.",
    long_description=readme,
    long_description_content_type="text/markdown",
    include_package_data=True,
    install_requires=["discord.py>=2.0.0, <3.0.0"],
    python_requires=">=3.11.0",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Natural Language :: English",
        "Typing :: Typed",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Programming Language :: Python :: 3 :: Only",
    ],
)
