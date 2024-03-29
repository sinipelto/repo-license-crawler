import importlib
import importlib.metadata
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Tuple

import pip

logging.basicConfig(
    level=logging.DEBUG
)

logger: logging.Logger = logging.getLogger("license-collector")

config_path: str = os.path.join("config", "config.json")
config: Dict[str, any]

TYPE_PYREQ: str = "py-req"
TYPE_NODEPKG: str = "node-pkg"


def log_error(err, *args, **kwargs):
    logging.error(f"ERROR: {err} {args} {kwargs}")


def load_config(path: str) -> Dict[str, any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as ex:
        logger.exception(f"Could not parse Config from Path: {path}", exc_info=ex)
        raise


# To support older Python versions
def find_recursive_old(path: str, filename: str) -> List[str]:
    logger.debug(f"Find file: {filename} in: {path}")
    matches = []
    for root, dirs, files in os.walk(path, topdown=True, onerror=log_error, followlinks=False):
        if filename.lower() in [name.lower() for name in files]:
            logger.debug(f"FOUND: {filename} in: {files}")
            matches.append(os.path.join(root, files[files.index(filename)]))
    return matches


def find_recursive(path: str, file_glob: str) -> List[Path]:
    logger.debug(f"Find file: {file_glob} in: {path}")
    return [file for file in Path(path).rglob(file_glob)]


def collect_files() -> List[Dict[str, str]]:
    results = []
    # Go through each path and find the file recursively
    for name, path in config['locations'].items():
        # For each filename in package files list
        for file in config['files']:
            targets = find_recursive(path, file['name'])
            logger.debug(f"FILES: {targets}")
            if len(targets) > 0:
                for tgt in targets:
                    results.append({'path': str(tgt), 'type': file['type']})
    return results


text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7f})


def is_binary_string(bts):
    return bool(bts.translate(None, text_chars))


def exec_cmd(args: List[str], capture: bool = True, output: any = None) -> subprocess.CompletedProcess:
    if not capture and output is None:
        raise ReferenceError("Output capture requested but No capture output was given.")

    capture_args = {
        'capture_output': False,
        'text': True,
        'stdout': output,
        'stderr': subprocess.STDOUT
    }

    # NOTE: subprocess.call is part of older Python 3.5 API
    # and is only available due to backwards compatibility
    # Thus, use subprocess.run instead!
    try:
        logger.debug(f"Executing command: {args}")
        res = subprocess.run(args, capture_output=True, text=True) if capture else subprocess.run(args, **capture_args)
        if res.returncode != 0:
            logger.error(f"ERROR: CMD Return code not SUCCESS: {args} STDOUT: {res.stdout} STDERR: {res.stderr}")
            raise SystemError(f"Command return code was not SUCCESS for command: {args}")
        return res
    except FileNotFoundError as ex:
        logger.error("ERROR: npm was not found. Ensure npm (Node.js runtime) is installed on the system.")
        raise ex
    except Exception as ex:
        logger.error(f"ERROR: Caught unexpected exception during command run. Command: {args}", exc_info=ex)
        raise ex


def setup_node_tools():
    # Ensure npm exists, installed
    # Ensure npx installed
    # Ensure license-crawler installed
    logger.info("Ensuring necessary npm tools are installed and up to date..")

    npm = config['bins']['npm']

    for cmd in [
        [npm, "install", "npx"],
        [npm, "install", "license-checker"],
    ]:
        exec_cmd(cmd)

    logger.info("Tools installation done.")


def process_package_files(files: List[Dict[str, str]]) -> Tuple[List[Dict[str, any]], Dict[str, int]]:
    results: List[Dict[str, any]] = []

    for file in files:
        path: str = file['path']
        ftype: str = file['type']

        result: Dict[str, any] = {'path': path, 'type': ftype, 'packages': []}

        # For python requirements
        # Install all the packages in req file
        # Scan through all packages and fetch the license field
        if ftype == TYPE_PYREQ:
            logger.debug("IS PYTHON PACKAGE FILE!")
            # pip install -r requirements.txt into VENV
            pip.main(['install', '-r', path])
            if is_binary_string(open(path, 'rb').read(1024)):
                logger.warning("Target is possibly binary file. Trying UTF-16.")

                def read_lines():
                    with open(path, "r", encoding="utf-16") as f16:
                        return f16.read().split("\n")
            else:
                def read_lines():
                    with open(path, "r", encoding="utf-8") as f8:
                        return f8.readlines()

            for line in read_lines():
                line = line.strip("\r\n").strip("\r").strip("\n").strip("\t").strip(" ")
                pkg = line.split(",")[0].split("==")[0].split(">=")[0].split("~=")[0].split("!=")[0]
                # Skip empty lines
                if pkg == "":
                    continue
                try:
                    meta = importlib.metadata.metadata(pkg)
                    # Returns value in dict or None if key not found
                    ver = meta['Version']
                    lic = meta['License']
                    result['packages'].append({'name': pkg, 'meta': True, 'version': ver, 'license': lic})
                except Exception as ex:
                    logger.exception(f"ERROR: Failed to read package meta for: {pkg}", exc_info=ex)
                    result['packages'].append({'name': pkg, 'meta': False, 'version': None, 'license': None})
            results.append(result)

        elif ftype == TYPE_NODEPKG:
            logger.debug("IS NODE PACKAGE FILE!")
            if not path.endswith(".json"):
                raise ValueError("INVALID JSON FILE!")
            with open(path, "r", encoding="utf-8") as nf:
                content: Dict[str, any] = json.load(nf)

            name = content['name'] if 'name' in content else None
            ver = content['version'] if 'version' in content else None
            lic = content['license'] if 'license' in content else None

            if name is None:
                logger.debug("Package json file missing attribute NAME.")

            result['packages'].append({'name': name, 'version': ver, 'license': lic})
            results.append(result)

        elif type == "ANY_OTHER_PACKAGE_TYPE":
            # Define other package type parsing here
            pass

        else:
            # This should never occur
            # If happens, error in config, missing definition(s) etc.
            logger.error("ERROR: Unknown package type!")
            raise KeyError("Unknown package type requested.")

    # Generate a summary of all licenses in results
    # And add as a part of the output
    summary: Dict[str, int] = {'NONE': 0}

    for res in results:
        for pkg in res['packages']:
            if 'license' not in pkg:
                summary['NONE'] += 1
                continue
            lic = pkg['license']
            if lic is None or lic == "":
                summary['NONE'] += 1
            if lic not in summary:
                summary[lic] = 1
            else:
                summary[lic] += 1

    # Order licenses Descending by count (license with most uses first)
    summary = {k: v for k, v in sorted(summary.items(), key=lambda it: it[1], reverse=True)}

    return results, summary


def process_npm_modules(files: List[Dict[str, str]]) -> List[Dict[str, any]]:
    results = []
    for file in files:
        path: str = file['path']
        ftype: str = file['type']

        if ftype != TYPE_NODEPKG:
            continue

        with open(path, "r", encoding="utf-8") as f:
            content: Dict[str, any] = json.load(f)

        # Not every pkg file has name!!
        # name: str = content['name'] if 'name' in content else None

        # Collect all possible dependencies from the package json file
        # Collect also additional dependencies
        deps: Set[str] = set()
        for key in [
            'dependencies',
            'devDependencies',
            'peerDependencies'
            'bundledDependencies',
            'optionalDependencies',
        ]:
            deps.update(set(content[key].keys()) if key in content else set())

        # Collect unique package names into list
        # NOTE: done in previous stage
        # if name is not None and name != "" and name not in results:
        #     results.append(content['name'])

        # results.update(deps)

        if len(deps) > 0:
            results.append({
                'path': path,
                'type': ftype,
                'packages': [dep for dep in deps if dep is not None and dep != ""]
            })
        else:
            logger.warning(f"No dependencies found in package json file: {path}")

    return results


def scan_npm_licenses(files: List[Dict[str, str]], results: List[dict]) -> None:
    modules: List[Dict[str, any]] = process_npm_modules(files)

    # Required NPM binaries
    npm: str = config['bins']['npm']
    npx: str = config['bins']['npx']

    # Provided as pipe to --json argument
    lic_path: str = config['node_output']

    # Summary from --summary is plain text so piped into .txt file
    sum_path: str = config['node_summary']

    # Output for packages summary (which packages belong to which file, etc
    pkg_path: str = config['node_deps']
    dump_json(modules, pkg_path)

    # Install all package.json packages
    # First, install all the used node modules into current location
    logger.info("Installing node modules (might take a very long time)..")
    # TODO NOTE: Running installs one package at a time is extremely slow! Using bundled installation instead
    # for mod in modules:
    #     try:
    #         logger.debug(f"Installing module: {mod}")
    #         res = exec_cmd(
    #             [npm, "install", "--force", "--allow-missing", "--legacy-peer-deps", mod]
    #         )
    #         logger.debug(f"Module: {mod} installed: {res}")
    #     except Exception as ex:
    #         logger.exception(f"ERROR: Failed to install package: {mod}", exc_info=ex)

    packages: Set[str] = set()
    for mod in modules:
        packages.update(set(mod['packages']))

    res = exec_cmd(
        [npm, "install", "--force", "--allow-missing", "--legacy-peer-deps"] + list(packages)
    )
    logger.debug(f"All Modules installed: {res}")
    logger.info("All node modules installed.")

    # After installing all packages, ensure tools installed & up to date
    setup_node_tools()

    # Run the crawler on node_modules
    # After, crawl through the installed modules for licenses
    logger.info("Crawling through licenses..")
    with open(lic_path, "w", encoding="utf-8") as f:
        out = exec_cmd([npx, "license-checker", "--json"], capture=False, output=f)
    logger.debug(f"RESULT: {out}")
    logger.info("Crawling done. Licenses written.")

    # Collect a separate summary of licenses
    logger.info("Collect license summary..")
    with open(sum_path, "w", encoding="utf-8") as f:
        out = exec_cmd([npx, "license-checker", "--summary"], capture=False, output=f)
    logger.debug(f"RESULT: {out}")
    logger.info("Summary written.")


def process_license_info(data: List[Dict[str, str]]):
    # TODO walk through licenses and fetch full info based on the lic type from some API?
    pass


def dump_json(data: any, path: str):
    # Open output file to be written
    with open(path, "w", encoding="utf-8") as of:
        json.dump(data, of, indent=2)


def main():
    global config
    config = load_config(config_path)

    files: List[Dict[str, str]] = collect_files()

    # Process Python packages and NPM package meta
    data, summary = process_package_files(files)

    # If npm packages exist, run the package collection on package files
    if len([f for f in files if f['type'] == TYPE_NODEPKG]) > 0:
        logger.debug("Found at least 1 node package. Processing also node packages..")
        scan_npm_licenses(files, data)

    dump_json(data, config['output'])
    # Dump the summary in a separate file
    dump_json(summary, config['output_summary'])


if __name__ == '__main__':
    main()
