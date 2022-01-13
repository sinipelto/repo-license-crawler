# license-collector

License collector tool for Python PIP and NodeJS NPM package licenses.

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
