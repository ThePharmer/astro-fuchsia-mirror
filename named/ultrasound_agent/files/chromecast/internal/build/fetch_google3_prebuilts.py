#!/usr/bin/env python3
"""Downloads Google3 prebuilts and supplies them to the build environment.

The prebuilts are downloaded from a GCS bucket and stored locally.

GN files are generated from the prebuilts to expose their contents to GN
using build targets.

Prebuilt manifest files are read from each individual prebuilt's destination
directory, and used to collate a runtime dependencies file, "runtime_deps";
this file is used to copy files into the output directory of the build, and
are eventually loaded at runtime by various executables.

The versions to fetch are governed by various prebuilt configuration files
on the file system, such as ../vendor/google3/prebuilts.json. See the
prebuilts.downloading module for the specific configuration files which are
loaded by this program.
"""

import argparse
import logging
import os
import sys

# This file is run during the `gclient sync` step of various Nest builds, as
# well as from a unit test recipe. There does not appear to be an import style
# compatible with both invocations of this script, so we declare a fallback
# below.
#
# gclient sync:
# http://cs/eureka_internal/chromium/.gclient?l=21&rcl=2dd7110abfd44c802c5ba0b7e255559a8e31d0d2
#
# Unit tests:
# http://cs/eureka_internal/continuous-tests/cq/scripts/slave/recipe/py_test_runner.py?l=16&rcl=0b2855eaa9b2003d9db847b26f9c8318325f0d08
# pylint: disable=g-import-not-at-top
try:
  from prebuilts import downloading
  from prebuilts import privileges
except ImportError:
  from build.prebuilts import downloading
  from build.prebuilts import privileges
# pylint: enable=g-import-not-at-top


def main():
  _configure_logging()

  def default_action(args):
    logging.info('Downloading all available prebuilts.')
    if hasattr(args, 'access_level'):
      level = privileges.RequestedAccessLevel(args.access_level)
    else:
      level = privileges.RequestedAccessLevel.INFER
    downloading.download_and_unpack_all_google3_prebuilts(
        requested_access_level=level)

  main_description = ('This is a command-line utility for interacting with '
                      'Google3 prebuilts; packages that have been built from '
                      'Piper source and exported for use in builds defined in '
                      'Git-on-Borg. Further information is available at: '
                      'go/nest-prebuilts')
  parser = argparse.ArgumentParser(description=main_description)
  parser.set_defaults(func=default_action)
  subparsers = parser.add_subparsers(help='The command to execute.')

  download_all_subparser = subparsers.add_parser(
      'download-all-prebuilts', help='Download all available prebuilts.')
  download_all_subparser.add_argument(
      '--access-level',
      required=False,
      choices=[l.value for l in privileges.RequestedAccessLevel],
      default=privileges.RequestedAccessLevel.INFER.value,
      help='Specify the desired access level.')
  download_all_subparser.set_defaults(func=default_action)

  def download_single_action(args):
    downloading.download_and_unpack_single_google3_prebuilt(
        requested_name=args.name,
        requested_architecture=args.architecture,
        requested_access_level=privileges.RequestedAccessLevel(
            args.access_level))
  download_single_subparser = subparsers.add_parser(
      'download-single-prebuilt', help='Download a single prebuilt version.')
  download_single_subparser.add_argument('--name', required=True)
  download_single_subparser.add_argument(
      '--architecture', required=True)
  download_single_subparser.add_argument(
      '--access-level',
      required=False,
      choices=[l.value for l in privileges.RequestedAccessLevel],
      default=privileges.RequestedAccessLevel.INFER,
      help='Specify the desired access level.')
  download_single_subparser.set_defaults(func=download_single_action)

  delete_description = ('When prebuilts are downloaded one-at-a-time from a '
                        'build process, that build process should clear '
                        'incremental files before beginning. this avoids '
                        'out-of-date incremental files from being included in '
                        'build outputs, using this command.')
  delete_files_subparser = subparsers.add_parser(
      'delete-incremental-files', help=delete_description)
  delete_files_subparser.set_defaults(
      func=lambda args: downloading.delete_incremental_files())

  generate_description = ('When prebuilts are downloaded one-at-a-time from a '
                          'build process, that build process should generate '
                          'those incremental files once all downloads are '
                          'complete, using this command.')
  gen_incremental_subparser = subparsers.add_parser(
      'generate-incremental-files', help=generate_description)
  gen_incremental_subparser.set_defaults(
      func=lambda args: downloading.generate_incremental_files())

  def check_access_action(_):
    print(privileges.check_access_level(
        privileges.RequestedAccessLevel.INFER).value)
  check_access_description = ('Emits the highest access level to which the '
                              'current user has access; "internal", or '
                              'otherwise "public". If the current user has '
                              'access to neither, the process exits with a '
                              'non-zero status code.')
  check_access_subparser = subparsers.add_parser(
      'check-access-level', help=check_access_description)
  check_access_subparser.set_defaults(func=check_access_action)

  if _check_gsutil_is_on_path():
    args = parser.parse_args()
    args.func(args)
    return 0
  else:
    logging.error('The depot_tools directory must be on your PATH in order to '
                  'find gsutil.py.')
    return 1


def _check_gsutil_is_on_path():
  return any(os.path.exists(os.path.join(path, 'gsutil.py'))
             for path in os.environ.get('PATH', '').split(os.pathsep))


def _configure_logging():
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)s %(asctime)s [%(filename)s:%(lineno)d] %(message)s')


if __name__ == '__main__':
  sys.exit(main())

