#!/usr/bin/env python3
import os
import argparse
import subprocess
import shutil

DIR = os.path.dirname(os.path.realpath(__file__))

parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('command', choices=['rebuild', 'new-version'], metavar='command', help='rebuild - rebuild current version and updatesite\nnew-version - creates a new version with newest changes from upstream ClearLinux')
parser.add_argument('--copy-www', metavar='directory', help='copy contents of updatatesite to directory')
parser.add_argument('--copy-img', metavar='directory', help='copy built images to directory')
parser.add_argument('--build-dir', metavar='dir', help='the directory to persist the build (default: current directory)')
args = parser.parse_args()

if not args.build_dir:
    args.build_dir = os.getcwd()

# Run mixer to build the updatesite
def RunMixerCommand(*args, workdir=None):
    command = ('mixer', '--native')+args
    subprocess.run(command, cwd=workdir)

if args.command == 'new-version':
    print('Bumping mix version')
    RunMixerCommand('versions', 'update', '--upstream-version', 'latest', workdir=args.build_dir)

print('Building mix')
RunMixerCommand('build', 'all', '--retries', '10', workdir=args.build_dir)

def copy2_verbose(src, dst):
    print('{} -> {}'.format(src, dst))
    shutil.copy2(src, dst)

# Copy updatesite content
if args.copy_www:
    print('Copying updatesite')

    # Always copy current build
    current_version = '0'
    with open(os.path.join(args.build_dir, 'mixversion'), 'r') as file:
        current_version = file.read().strip().strip('\r\n')
    print('Copying current version ({}) ...'.format(current_version))
    if os.path.isdir(os.path.join(args.copy_www, current_version)):
        shutil.rmtree(os.path.join(args.copy_www, current_version))
    shutil.copytree(os.path.join(args.build_dir, 'update/www', current_version), os.path.join(args.copy_www, current_version), copy_function=copy2_verbose)

    # Copy missing versions
    (_, built_versions, _) = next(os.walk(os.path.join(args.build_dir, 'update/www')))
    (_, copied_versions, _) = next(os.walk(args.copy_www))
    for version in built_versions:
        if version == 'version':
            pass
        elif version in copied_versions:
            print('Skipping version {}, already copied ...'.format(version))
        else:
            print('Copying version {} ...'.format(version))
            shutil.copytree(os.path.join(args.build_dir, 'update/www', version), os.path.join(args.copy_www, version), copy_function=copy2_verbose)
    
    # Copy versions directory
    print('Copying versions directory ...')
    shutil.copytree(os.path.join(args.build_dir, 'update/www/version'), os.path.join(args.copy_www, 'version'), copy_function=copy2_verbose)



def CopyOverwriteRecursively(src, dst):
    if not os.path.isdir(dst):
        os.mkdir(dst)

    for src_root, child_dirs, child_files in os.walk(src):
        dst_root = os.path.join(dst, os.path.relpath(src_root, src))
        for child_dir in child_dirs:
            dst_path = os.path.join(dst_root, child_dir)
            if os.path.isdir(dst_path):
                pass
            elif os.path.exists(dst_path):
                os.remove(dst_path)
                os.mkdir(dst_path)
            else:
                os.mkdir(dst_path)
        for child_file in child_files:
            src_path = os.path.join(src_root, child_file)
            dst_path = os.path.join(dst_root, child_file)
            if os.path.isdir(dst_path):
                shutil.rmtree(dst_path)
            else:
                shutil.copy2(src_path, dst_path)


# Construct images directories
images_build_dir = os.path.join(args.build_dir, 'images')
images_submodules_dir = os.path.join(DIR, '../Images')

shutil.rmtree(images_build_dir)
os.mkdir(images_build_dir)

(_, image_submodules, _) = next(os.walk(images_submodules_dir))
for image_submodule in image_submodules:
    (_, image_directories, _) = next(os.walk(os.path.join(images_submodules_dir, image_submodule)))

    for image_directory in image_directories:
        CopyOverwriteRecursively(os.path.join(images_submodules_dir, image_submodule, image_directory), os.path.join(images_build_dir, image_directory))

# Build all the images
(_, images, _) = next(os.walk(images_build_dir))
absolute_config_path = os.path.abspath(os.path.join(args.build_dir, 'builder.conf'))
for image in images:
    # Change workdingdir
    absoulute_image_path = os.path.abspath(os.path.join(images_build_dir, image))
    os.chdir(absoulute_image_path)

    # Build the image
    print('Building image {} ...'.format(image), end='')
    RunMixerCommand('build', 'image', '--config', absolute_config_path, '--template', 'image-config.json')
    print(' {0:.0f} MiB'.format(os.path.getsize('image.img')/(2**20)))

    # Compress the image
    print('Compressing image.img ...', end='')
    subprocess.run(('xz', '-zk', 'image.img'))
    print(' {0:.0f} MiB'.format(os.path.getsize('image.img.xz')/(2**20)))

    os.chdir(args.build_dir)

    # Copy the image
    if args.copy_img:
        print('Copying the image.img.xz to {}.img.xz ...'.format(image))
        shutil.copy2(os.path.join(images_build_dir, image, 'image.img.xz'), os.path.join(args.copy_img, '{}.img.xz'.format(image)))

