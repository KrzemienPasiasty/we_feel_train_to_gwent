# We Feel Train to Gwent

## Why it was failing

The app depends on Tkinter and the customtkinter GUI library. On this machine, the default `python` command was using a Python build without Tkinter, so startup failed with `ModuleNotFoundError: No module named 'tkinter'`.

## Run it correctly

From PowerShell in the project folder:

```powershell
py -3.14 -m pip install -r requirements.txt
py -3.14 main.py
```

or simply:

```powershell
.\run_app.ps1
```

This project expects Python 3.14 with Tkinter support.
