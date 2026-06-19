import os
import sys
import time
import argparse
import hashlib
import json
from pathlib import Path
from osfclient.api import OSF
import configparser

CONFIG_FILE_NAME = ".osf_exp_config.json"


def parse_arguments():
    """Parse command-line arguments (-i required, -d, -f, -u)."""
    parser = argparse.ArgumentParser(
        description="A robust python wrapper to reliably stream files to an OSF project subfolder."
    )
    parser.add_argument(
        "-i", "--input", 
        required=True,
        help="Path to the text file containing local file paths."
    )
    parser.add_argument(
        "-d", "--destination", 
        default=None,
        help="Target subfolder name on the OSF project repository (default: agc_compressed)"
    )
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force overwrite of existing files on OSF without checking hashes."
    )
    group.add_argument(
        "-u", "--update",
        action="store_true",
        help="Overwrite an existing file only if the local and remote MD5 hashes differ."
    )
    
    return parser.parse_args()


def get_osf_storage():
    """Authenticate and return the OSF storage object and project ID."""
    token = os.getenv("OSF_TOKEN")
    project_id = None

    # Paths to check: local directory first, then home directory
    config_paths = [Path(".osfcli.config"), Path.home() / ".osfcli.config"]
    
    for path in config_paths:
        if path.is_file():
            try:
                config = configparser.ConfigParser()
                config.read(path)
                if 'osf' in config and 'project' in config['osf']:
                    project_id = config['osf']['project'].strip()
                    break
            except Exception as e:
                print(f"Warning: Failed to parse config file at {path}: {e}")

    # Fallback to environment variable if config file didn't yield an ID
    if not project_id:
        project_id = os.getenv("OSF_PROJECT")

    if not token or not project_id:
        print("Error: Please set OSF_TOKEN and OSF_PROJECT environment variables.")
        sys.exit(1)

    osf = OSF(token=token)
    project = osf.project(project_id)
    return project.storage("osfstorage"), project_id


def fetch_remote_inventory(storage, project_id):
    """Fetch remote file inventory and map paths to file objects."""
    print(f"Fetching remote file inventory for project {project_id}...")
    inventory = {}
    try:
        for file_obj in storage.files:
            inventory[file_obj.path.lstrip("/")] = file_obj
        return inventory
    except Exception as e:
        print(f"Error reading remote manifest from OSF: {e}")
        sys.exit(1)


def parse_local_file_list(input_file_path):
    """Read, clean, and validate local paths from the input manifest file."""
    if not os.path.exists(input_file_path):
        print(f"Error: Input file '{input_file_path}' not found.")
        sys.exit(1)

    valid_paths = []
    with open(input_file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            local_path = Path(line)
            if not local_path.is_file():
                print(f"Skipping lookup: Local file not found: {local_path}")
                continue
            
            valid_paths.append(local_path)
    return valid_paths


def calculate_local_md5(local_file_path):
    """Calculate the MD5 checksum of a local file using buffered chunks."""
    hash_md5 = hashlib.md5()
    with open(local_file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def upload_file_with_retry(storage, local_path, expected_remote_path, max_attempts=5):
    """Stream binary file descriptor to OSF with a retry mechanism for 502 errors."""
    filename = local_path.name
    attempt = 1

    while attempt <= max_attempts:
        try:
            with open(local_path, "rb") as fp:
                storage.create_file(expected_remote_path, fp, force=True)
            print(f"Successfully uploaded: {filename}")
            return True
        except Exception as e:
            print(f"Warning: Attempt {attempt}/{max_attempts} failed for {filename}. Error: {e}")
            if attempt < max_attempts:
                print("Waiting 15 seconds before retrying...")
                time.sleep(15)
            attempt += 1

    print(f"ERROR: Failed to upload {filename} after {max_attempts} attempts.")
    return False


def main():
    args = parse_arguments()

    storage, resolved_project_id = get_osf_storage()
    remote_inventory = fetch_remote_inventory(storage, resolved_project_id)
    local_files = parse_local_file_list(args.input)

    for local_path in local_files:
        filename = local_path.name

        if args.destination and args.destination.strip():
            expected_remote_path = f"{args.destination.strip()}/{filename}"
        else:
            expected_remote_path = filename

        if expected_remote_path in remote_inventory:
            if args.force:
                print(f"Force overwrite active: {filename}")
            elif args.update:
                print(f"Checking hashes for: {filename}")
                remote_file_obj = remote_inventory[expected_remote_path]
                if calculate_local_md5(local_path) == remote_file_obj.hashes.get('md5'):
                    print(f"Skipping: {filename} has identical MD5 hash.")
                    continue
                print(f"Hashes differ. Updating: {filename}")
            else:
                print(f"Skipping: {filename} already exists on OSF.")
                continue
        else:
            print(f"New target detected: {filename} -> {expected_remote_path}")

        success = upload_file_with_retry(storage, local_path, expected_remote_path)
        
        if success and args.update:
            remote_inventory[expected_remote_path] = True

        time.sleep(1.5)

    print("Sync workflow execution finished.")


if __name__ == "__main__":
    main()