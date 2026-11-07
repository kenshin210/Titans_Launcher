Garbage - files the launcher does not need to run.

Folder layout mirrors the project, so a file can be put back by moving it to the
same path without the "Garbage/" prefix.

- __init__.py files: Python 3 treats the folders as namespace packages without them,
  and they only held one-line docstrings.
- Compiled __pycache__ folders: Python regenerates these automatically.
- Empty placeholders (.gitkeep, Assets/Icons/test, Assets/Styles/Styler,
  Assets/Videos/Somevideo): not referenced by any code.

This folder can be deleted safely.
