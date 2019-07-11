#!/usr/bin/env python3
import os
import argparse
import subprocess

DIR = os.path.dirname(os.path.realpath(__file__))

parser = argparse.ArgumentParser()
parser.add_argument('--update-url', metavar='url', help='the url where the content of the updatesite will be hosted', required=True)
parser.add_argument('--build-dir', metavar='dir', help='the directory to persist the build (default: current directory)')
args = parser.parse_args()

# Run mixer to build the updatesite
def RunMixerCommand(*args, workdir=None):
    command = ('mixer', '--native')+args
    subprocess.run(command, cwd=workdir)

if not args.build_dir:
    args.build_dir = os.getcwd()

# Create the builder.conf
builder_conf = '''
#VERSION 1.1

[Builder]
  CERT = "{0}/Swupd_Root.pem"
  SERVER_STATE_DIR = "{0}/update"
  VERSIONS_PATH = "{0}"
  YUM_CONF = "{0}/.yum-mix.conf"

[Swupd]
  BUNDLE = "os-core-update"
  CONTENTURL = "{1}"
  VERSIONURL = "{1}"

[Server]
  DEBUG_INFO_BANNED = "true"
  DEBUG_INFO_LIB = "/usr/lib/debug"
  DEBUG_INFO_SRC = "/usr/src/debug"

[Mixer]
  LOCAL_BUNDLE_DIR = "{0}/local-bundles"
  LOCAL_REPO_DIR = "{0}/local-yum"
  LOCAL_RPM_DIR = "{0}/local-rpms"
  DOCKER_IMAGE_PATH = "clearlinux/mixer"
  OS_RELEASE_PATH = ""
'''.format(args.build_dir, args.update_url)

# Write config to file
print('Writing mix configuration to {} ...'.format(os.path.join(args.build_dir, 'builder.conf')))
with open(os.path.join(args.build_dir, 'builder.conf'), 'w') as file:
    file.write(builder_conf)

RunMixerCommand('init', workdir=args.build_dir)