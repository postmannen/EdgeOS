#!/usr/bin/env python3
import os
import argparse
import subprocess
import configparser
import re
import json
import certifi
import urllib3

DIR = os.path.dirname(os.path.realpath(__file__))

parser = argparse.ArgumentParser()
parser.add_argument('--build-dir', metavar='dir', help='the directory to persist the build (default: current directory)')
args = parser.parse_args()

if not args.build_dir:
    args.build_dir = os.getcwd()

http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED',ca_certs=certifi.where(),headers={'User-Agent': 'dolittle-edge/edgeos'})


## Get some Git metadata
git_head = ''
with open(os.path.join(DIR, '../.git/HEAD'), 'r') as file:
    (_, head) = file.read().split(':')
    git_head = head.strip()
git_config = configparser.ConfigParser()
git_config.read(os.path.join(DIR, '../.git/config'))

git_branch = ''
git_remote_url = ''
for section in git_config:
    if git_config.has_option(section, 'merge') and git_config.get(section, 'merge') == git_head:
        git_branch = re.search(r'^branch "(.*)"', section).group(1)
        remote = git_config.get(section, 'remote')
        git_remote_url = git_config.get('remote "{}"'.format(remote), 'url')

## Fetch latest changes from Git upstream
print('Pulling latest from "{}" for branch "{}"'.format(git_remote_url, git_branch))

subprocess.run(('git', 'pull'), cwd=os.path.join(DIR,'..'))
subprocess.run(('git', 'submodule', 'update', '--init', '--recursive'), cwd=os.path.join(DIR,'..'))


## Update bundles from submodules
(_, bundle_submodules, _) = next(os.walk(os.path.join(DIR, '../Bundles')))
bundles = {}

for bundle_submodule in sorted(bundle_submodules):
    # Remove bundles
    remove_dir = os.path.join(DIR, '../Bundles', bundle_submodule, 'Remove')
    if os.path.isdir(remove_dir):
        (_, _, bundles_to_remove) = next(os.walk(remove_dir))
        for bundle_to_remove in bundles_to_remove:
            bundles.pop(bundle_to_remove, None)

    # Add bundles
    add_dir = os.path.join(DIR, '../Bundles', bundle_submodule, 'Add')
    if os.path.isdir(add_dir):
        (_, _, bundles_to_add) = next(os.walk(add_dir))
        for bundle_to_add in bundles_to_add:
            with open(os.path.join(add_dir, bundle_to_add), 'r') as file:
                bundles[bundle_to_add] = file.read()


# Write all local bundles
updated_local_bundles = [bundle for bundle in bundles if len(bundles[bundle].strip())>0]
(_, _, existing_local_bundles) = next(os.walk(os.path.join(args.build_dir, 'local-bundles')))

for bundle in updated_local_bundles:
    print('Writing local bundle {} ...'.format(bundle))
    with open(os.path.join(args.build_dir, 'local-bundles', bundle), 'w') as file:
        # HACK: Remove empty lines as the 'mixer build upstream-format' craps out on empty lines
        nonempty_lines = [l for l in bundles[bundle].splitlines() if len(l) > 0]
        file.write(os.linesep.join(nonempty_lines))

for bundle in existing_local_bundles:
    if bundle not in updated_local_bundles:
        print('Removing local bundle {} ...'.format(bundle))
        os.remove(os.path.join(args.build_dir, 'local-bundles', bundle))

# Write mixbundles
print('Writing {} bundles to mixbundles file ...'.format(len(bundles)))
with open(os.path.join(args.build_dir, 'mixbundles'), 'w') as file:
    for bundle in sorted(bundles.keys()):
        print(bundle, file=file)


## Update packages from bundle submodules
package_repositories = []
# Get all package repositories in sorted order of priority
for bundle_submodule in sorted(bundle_submodules):
    packages_dir = os.path.join(DIR, '../Bundles', bundle_submodule, 'Packages')
    (_, _, package_repo_files) = next(os.walk(packages_dir))
    for package_repo_file in sorted(package_repo_files):
        with open(os.path.join(packages_dir, package_repo_file),'r') as file:
            package_repo = file.read().strip().strip('\r\n')
            package_repositories.append(package_repo)


# For each repository find latest version of each package
selected_packages = {}

for package_repository in package_repositories:
    response = http.request('GET', 'https://api.github.com/repos/{}/releases'.format(package_repository))
    releases = json.loads(response.data.decode('utf-8'))

    packages = {}

    def AddPackageToMap(name, version, filename, url):
        if name in packages:
            packages[name].append({'version': version, 'filename': filename, 'url': url})
        else:
            packages[name] = [{'version': version, 'filename': filename, 'url': url}]

    def SplitFileNameToPackageNameAndVersion(filename):
        (basename, _, _) = filename.rsplit('.',2)
        (name, version, release) = basename.rsplit('-',2)
        (major, minor, patch) = version.split('.')
        return (name, (int(major),int(minor),int(patch),int(release)))

    for release in releases:
        for asset in release['assets']:
            if asset['name'].endswith('.rpm'):
                name, version = SplitFileNameToPackageNameAndVersion(asset['name'])
                AddPackageToMap(name, version, asset['name'], asset['browser_download_url'])

    for package in packages:
        versions = packages[package]
        newest = sorted(versions, key=lambda e: e['version'], reverse=True)[0]

        # Add to overall selected package structure
        if package not in selected_packages:
            print('Adding package {} version {}.{}.{}-{} from {}'.format(package, version[0], version[1], version[2], version[3], package_repository))
            selected_packages[package] = newest
        else:
            print('Overriding package {} to version {}.{}.{}-{} from {}'.format(package, version[0], version[1], version[2], version[3], package_repository))
            selected_packages[package] = newest

# Download selected packages
downloaded_rpm_files = []
for selected_package in selected_packages:
    package = selected_packages[selected_package]
    print('Downloading {} ...'.format(package['url']))
    downloaded_rpm_files.append(package['filename'])
    with open(os.path.join(args.build_dir, 'local-rpms', package['filename']), 'wb') as file:
        response = http.request('GET', package['url'])
        file.write(response.data)

# Delete all packages that are not selected
(_, _, local_rpm_files) = next(os.walk(os.path.join(args.build_dir, 'local-rpms')))
for local_rpm_file in local_rpm_files:
    if local_rpm_file not in downloaded_rpm_files:
        print('Deleting old file {} ...'.format(local_rpm_file))
        os.remove(os.path.join(args.build_dir, 'local-rpms', local_rpm_file))
