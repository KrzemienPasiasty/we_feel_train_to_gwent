$python = Get-Command py -ErrorAction SilentlyContinue

if (-not $python) {
    Write-Error "Python launcher 'py' was not found. Install Python 3.14+ with Tkinter support and try again."
    exit 1
}

& py -3.14 -m pip install -r "$PSScriptRoot\requirements.txt"
& py -3.14 "$PSScriptRoot\main.py"
