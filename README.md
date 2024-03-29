# (Universal) Repository License Crawler

License collector tool for Python PIP and NodeJS NPM package licenses.

The aim is to get a complete collection of what kind of licenses are being used in the given repository (path), in any form, as parts of the application or individual libraries.

This helps identify the legitimacy of the current software project, especially in larger repos with dozens of libraries or dependencies.

This tool collects the licenses into human and machine-readable JSON files. From there it should be relatively easy to detect any conflicting licenses and take actions based on that information.

# Getting Started

Install / ensure installed the following:
- [Python 3.8+](https://www.python.org/downloads/)
- [Node.js](https://nodejs.org/en/) (or Node Package Manager (NPM) at minimum)

After installation, ensure both `python` and `npm` are available through `PATH` directly.

Ensure pip is up-to-date:

```bash
pip -V
pip install -U pip
pip -V
```

Or through python if pip is not globally available

```bash
python -m pip -V
python -m pip install -U pip
python -m pip -V
```

Ensure NPM is globally up-to-date:

```bash
npm -v
npm install -g npm@latest
npm -v
```

Create an empty Python Virtual Environment (VENV) for the tool:

```bash
python -m venv C:\path\to\venv
```

Activate the newly created VENV:

```bash
.\venv\Scripts\activate
```

Ensure pip is up-to-date (inside VENV):

```bash
pip -V
pip install -U pip
pip -V
```

Or through python if pip is not globally available (inside VENV):

```bash
python -m pip -V
python -m pip install -U pip
python -m pip -V
```


Install the required dependencies for the tool into the VENV (if applicable):

```bash
pip install -r requirements.txt
```
OR
```bash
python -m pip install -r requirements.txt
```

Run the main file

```bash
python main.py
```

Once successfully finished, check the output file for results (default: `./out/output.json`)
