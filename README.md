# osf-hpc-wrapper
A wrapper for OSF upload using fof as input

## Install:
pip install -e .
conda install conda-forge::osfclient 

## Usage:

### Configuration
TOKEN: export OSF_TOKEN="your_personal_access_token"

INIT REMOTE: osf init

### Sync files to a subfolder (default: agc_compressed)
osf-sync -i files_to_upload.txt -d subfolder_name

### Sync files directly to the root directory
osf-sync -i files_to_upload.txt -d ""

### Check MD5 hashes and overwrite only if files have changed locally
osf-sync -i files_to_upload.txt --update

### Force and overwrite
osf-sync -i files_to_upload.txt --force