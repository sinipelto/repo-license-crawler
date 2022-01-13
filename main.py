import importlib
import importlib.metadata
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Set

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
    logger.info("Ensuring necessary npm tools are installed..")

    npm = config['bins']['npm']

    for cmd in [
        [npm, "install", "npx"],
        [npm, "install", "license-checker"],
    ]:
        exec_cmd(cmd)

    logger.info("Installation done.")


def process_package_files(files: List[Dict[str, str]]) -> List[dict]:
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
                    result['packages'].append({'name': pkg, 'meta': False})
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
    summary = {'path': 'PACKAGE-SUMMARY', 'type': None, 'packages': None}
    licenses = {'N/A': 0}

    for res in results:
        for pkg in res['packages']:
            if 'license' not in pkg:
                licenses['N/A'] += 1
                continue
            lic = pkg['license']
            if lic not in licenses:
                licenses[lic] = 1
            else:
                licenses[lic] += 1

    # Order licenses by value (count) Descending
    summary['licenses'] = {k: v for k, v in sorted(licenses.items(), key=lambda it: it[1], reverse=True)}
    results.append(summary)

    return results


def process_node_modules(files: List[Dict[str, str]]) -> List[str]:
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
        deps: Set[str] = set(content['dependencies'].keys()) if 'dependencies' in content else set()

        # Collect also additional dependencies
        deps.update(set(content['devDependencies'].keys()) if 'devDependencies' in content else set())
        deps.update(set(content['peerDependencies'].keys()) if 'peerDependencies' in content else set())
        deps.update(set(content['bundledDependencies'].keys()) if 'bundledDependencies' in content else set())
        deps.update(set(content['optionalDependencies'].keys()) if 'optionalDependencies' in content else set())

        # Collect unique package names into list
        # NOTE: done in previous stage
        # if name is not None and name != "" and name not in results:
        #     results.append(content['name'])

        if len(deps) > 0:
            for dep in deps:
                if dep is not None and dep != "" and dep not in results:
                    results.append(dep)
        else:
            logger.debug("No dependencies found in package json file.")

    return results


def process_node_licenses(files: List[Dict[str, str]], data: List[dict]) -> None:
    modules: List[str] = process_node_modules(files)
    # TODO run crawler on node_modules dir
    #   -> parse licenses
    #   -> insert into data
    #   -> return

    # Required NPM binaries
    npm: str = config['bins']['npm']
    npx: str = config['bins']['npx']

    # Provided as pipe to --json argument
    lic_path: str = config['node_output']

    # Summary from --summary is plain text so piped into .txt file
    sum_path: str = config['node_summary']

    # Install all package.json packages
    # First, install all the used node modules into current location
    logger.info("Installing node modules (might take a very long time)..")
    # TODO NOTE: Running installs one at a time is extremely slow! Using bundled installation instead
    # for mod in modules:
    #     try:
    #         logger.debug(f"Installing module: {mod}")
    #         res = exec_cmd(
    #             [npm, "install", "--force", "--allow-missing", "--legacy-peer-deps", mod]
    #         )
    #         logger.debug(f"Module: {mod} installed: {res}")
    #     except Exception as ex:
    #         logger.exception(f"ERROR: Failed to install package: {mod}", exc_info=ex)
    res = exec_cmd(
        [npm, "install", "--force", "--allow-missing", "--legacy-peer-deps"] + modules
    )
    logger.debug(f"All Modules installed: {res}")
    logger.info("All node modules installed.")

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


def dump_results(result: List[Dict[str, str]], path: str):
    # Open output file to be written
    with open(path, "w", encoding="utf-8") as of:
        json.dump(result, of, indent=2)


def main():
    global config
    config = load_config(config_path)

    files: List[Dict[str, str]] = collect_files()

    # TODO enable
    # if len([f for f in files if f['type'] == TYPE_NODEPKG]) > 0:
    #     logger.debug("Found at least 1 node package. Preparing npm..")
    #     setup_node_tools()

    data = process_package_files(files)
    process_node_licenses(files, data)

    dump_results(data, config['output'])


if __name__ == '__main__':
    main()
