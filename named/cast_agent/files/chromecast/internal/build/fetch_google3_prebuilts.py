#!/usr/bin/env python2
"""Downloads Google3 prebuilts and supplies them to the build environment.

The prebuilts are downloaded from a GCS bucket and stored locally. A GN file
is generated from the prebuilts to expose them as build targets.

The versions to fetch are governed by prebuilts.json
"""


from __future__ import absolute_import
import codecs
import collections
import glob
import json
import logging
import multiprocessing
import os
import re
import shutil
import signal
import stat
import subprocess
import sys

from prebuilts import gn_util
from prebuilts import packages

GCS_BUCKET_PUBLIC = 'nest-prebuilts-public'
GCS_BUCKET_INTERNAL = 'nest-prebuilts-internal'
CONFIGURATION_PATH = os.path.join(packages.get_base_path(), 'prebuilts.json')
RUNTIME_DEPS_FILE = os.path.join(packages.get_packages_path(), 'runtime_deps')
GOOGLE3_RESOURCE_DIR = os.path.join('resources', 'google3')
SUPPORTED_ARCHITECTURES = ['arm', 'arm64', 'x64']

NOT_AUTHENTICATED_ERROR_MSG = r'ServiceException: 401'
ACCESS_DENIED_ERROR_MSG = r'AccessDeniedException: 403'


Manifest = collections.namedtuple(
    'Manifest',
    field_names=['headers', 'resources', 'binary', 'generate_gn_targets'])
Manifest.__new__.__defaults__ = (None, True)


def run_shell_command(cmd, cwd=None, raise_on_failure=True):
  """Runs a shell command and returns returncode, stdout, and stderr.

  Args:
    cmd: A list of command args to be run in a subprocess.
    cwd: The directory from which the command will run.
    raise_on_failure: If True, raises an exception when cmd fails.

  Raises:
    RuntimeError: If the command failed and |raise_on_failure| is True.

  Returns:
    (returncode, stdout, stderr) as a tuple.
  """
  logging.info(' '.join(cmd))
  p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       cwd=cwd)
  stdout, stderr = p.communicate()
  if p.returncode != 0 and raise_on_failure:
    raise RuntimeError('"{}" failed with returncode {}: {}'.format(
        ' '.join(cmd), p.returncode, stderr))
  return p.returncode, stdout, stderr


def run_gsutil_command(cmd):
  """Run gsutil commands with error handling. See RunShellCmd() docstring."""
  cmd = ['gsutil.py'] + cmd
  returncode, stdout, stderr = run_shell_command(cmd, raise_on_failure=False)
  if returncode != 0:
    if (re.search(NOT_AUTHENTICATED_ERROR_MSG, stderr) or
        re.search(ACCESS_DENIED_ERROR_MSG, stderr)):
      logging.error(
          '\n\nYou are not authenticated with a Google account whitelisted for '
          'this GCS resource. Please run: \n\n'
          '    gsutil.py config \n\n'
          'to authenticate via your whitelisted Google account. Internal '
          'developers should use their @google.com account. Partners should '
          'use an account from their whitelisted Google-managed domain '
          '(ex. you@yourcompany.com).\n\n'
          'For write access to all buckets, join the '
          'mdb/cast-goog3-bucket-writers group.')
    raise RuntimeError('"{}" failed with returncode {}: {}'.format(
        ' '.join(cmd), returncode, stderr))
  return returncode, stdout, stderr


def _can_access_internal_gcs_bucket():
  """Returns True if the current user can access the internal GCS bucket."""
  try:
    # Note: we intentionally do not use run_gsutil_command() here. We expect
    # this call to fail for external developers, and we shouldn't print an error
    # instructing them to re-authenticate in that case.
    run_shell_command(['gsutil.py', 'ls', 'gs://' + GCS_BUCKET_INTERNAL])
  except RuntimeError as e:
    logging.error('Cannot access %s. Only fetching public prebuilts. '
                  'REASON: %s',
                  GCS_BUCKET_INTERNAL,
                  e.message)
    return False
  return True


def _write_runtime_deps_file(prebuilts, has_internal_access):
  """Write a file with all possible artifacts and resources, one per line."""
  deps = []
  for p in prebuilts:
    first_arch = list(p['versions'].items())[0]
    first_prebuilt = _get_package(p, first_arch[0], has_internal_access)
    manifest = _load_manifest(first_prebuilt)
    if manifest.binary:
      deps.append(os.path.basename(manifest.binary))
    for r in manifest.resources:
      deps.append(os.path.join(GOOGLE3_RESOURCE_DIR, os.path.basename(r)))
  with codecs.open(os.path.abspath(RUNTIME_DEPS_FILE), mode='w',
                   encoding='UTF-8') as f:
    f.write('\n'.join(deps))


def _load_manifest(package):
  """Loads a prebuilt manifest JSON file."""
  path = os.path.join(packages.get_package_path(package), 'manifest.json')
  with open(path, 'r') as f:
    return Manifest(**json.load(f))


def _get_supported_prebuilt_gn_data(prebuilt, arch, has_internal_access):
  """Generates the data to be added to the GN file for a supported prebuilt."""
  package = _get_package(prebuilt, arch, has_internal_access)
  manifest = _load_manifest(package)
  if not manifest.generate_gn_targets:
    return None
  data = {
      'name': prebuilt['name'],
      'path': os.path.relpath(
          packages.get_package_path(package), packages.get_base_path()),
      'public': prebuilt['public'],
      'headers': manifest.headers,
      'resources': manifest.resources,
  }
  if manifest.binary:
    data['artifact'] = manifest.binary
    binary_name = os.path.basename(manifest.binary)
    if binary_name.endswith('.so'):
      data['lib'] = binary_name.replace('lib', '').replace('.so', '')
  return data


def _get_unsupported_prebuilt_gn_data(prebuilt):
  """Generates the data for the GN file for an unsupported prebuilt."""
  return {
      'name': prebuilt['name'],
      'supported_cpus': prebuilt['architectures']
  }


def _write_gn_file(prebuilts, has_internal_access):
  """Write a file to disk that GN will use to copy all necessary targets."""
  for arch in SUPPORTED_ARCHITECTURES:
    supported_prebuilts = [
        _get_supported_prebuilt_gn_data(p, arch, has_internal_access)
        for p in prebuilts
        if arch in p['architectures']]
    supported_prebuilts = [p for p in supported_prebuilts if p]

    unsupported_prebuilts = [
        _get_unsupported_prebuilt_gn_data(p)
        for p in prebuilts
        if arch not in p['architectures']]

    gn_data = {
        'modules': supported_prebuilts,
        'unsupported_modules': unsupported_prebuilts,
    }

    file_name = os.path.abspath(
        os.path.join(packages.get_packages_path(), '%s_prebuilts.gn' % arch))
    with  codecs.open(file_name, mode='w', encoding='UTF-8') as f:
      f.write('# This file is auto-generated by'
              ' fetch_google3_prebuilts.py during\n')
      f.write('# `gclient sync`. Do not manually modify.\n\n')
      f.write(gn_util.dumps(gn_data))


def _filter_accessible_prebuilts(nested_prebuilts, has_internal_access):
  """Filters the prebuilts to those that the user has access to."""
  if has_internal_access:
    return nested_prebuilts
  else:
    return [p for p in nested_prebuilts if p['public']]


def _get_package(prebuilt, architecture, has_internal_access):
  """Gets package version metadata for the given prebuilt and architecture."""
  version_key = 'internal' if has_internal_access else 'public'
  version = prebuilt['versions'][architecture][version_key]
  return packages.Package(prebuilt['name'], architecture, version)


def _get_packages(prebuilts, has_internal_access):
  """Gets package version metadata for the given prebuilts."""
  key = 'internal' if has_internal_access else 'public'
  packages = set()
  for p in prebuilts:
    for architecture, versions in p['versions'].items():
      if key in versions:
        packages.add(_get_package(p, architecture, has_internal_access))
  return packages


def _load_prebuilt_configuration():
  """Loads the prebuilt JSON configuration files from disk."""
  relative_path = [
      '..', '..', '..', '..', '..', '..',
      'vendor', '*', 'google3_prebuilts.json']
  search_pattern = os.path.abspath(os.path.normpath(os.path.join(
      __file__, *relative_path)))
  json_paths = [CONFIGURATION_PATH] + glob.glob(search_pattern)
  prebuilts = []
  for path in json_paths:
    with open(path, 'r') as f:
      prebuilts.extend(json.load(f)['prebuilts'])
  return prebuilts


def _get_package_gcs_path(package, bucket):
  gs_prefix = 'gs://'
  if package.version.startswith(gs_prefix):
    return '{}/*'.format(package.version)
  return '{}{}/{}/{}/{}/*'.format(
      gs_prefix,
      bucket,
      package.name,
      package.architecture,
      package.version
  )


def _fetch_package(x):
  """Fetches a single package in a worker process."""
  p, bucket = x
  logging.debug('Fetching {}'.format(p))
  gsc_path = _get_package_gcs_path(p, bucket)
  output_path = packages.get_package_path(p)
  os.makedirs(output_path)
  run_gsutil_command(['cp', '-r', gsc_path, output_path])
  fix_permissions(output_path)


def fix_permissions(path):
  """Sets executable bit to match forge permissions."""
  permissions = (stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR |
                 stat.S_IRGRP | stat.S_IXGRP |
                 stat.S_IROTH)
  for dirpath, _, filenames in os.walk(path):
    for filename in filenames:
      os.chmod(os.path.join(dirpath, filename), permissions)

def _ignore_sig_int():
  """Ignore SIG INT (Ctrl-C) on child processes; the parent handles clean up."""
  signal.signal(signal.SIGINT, signal.SIG_IGN)


def _fetch_packages(fetch_packages, bucket):
  """Download packages from the GCS bucket to the local disk."""
  if not fetch_packages:
    return
  data = [(p, bucket) for p in fetch_packages]
  pool = multiprocessing.Pool(processes=min(multiprocessing.cpu_count(),
                                            len(data)),
                              initializer=_ignore_sig_int)
  pool.map(_fetch_package, data)


def _find_existing_packages(wanted_packages, manifest):
  """Find packages that have been fetched by previous invocations."""
  packages_path = packages.get_packages_path()
  if not os.path.exists(packages_path):
    return set()
  paths = {os.path.join(packages_path, p) for p in os.listdir(packages_path)}
  return {p for p in wanted_packages if _package_exists(p, paths, manifest)}


def _package_exists(package, paths, manifest):
  local_path = packages.get_package_path(package)
  return (
      local_path in paths
      and package.version == manifest.get_package_version(package)
  )


def _remove_obsolete_files(keep_packages):
  """Remove packages that are no longer needed from the disk."""
  if not os.path.exists(packages.get_packages_path()):
    return
  prebuilt_paths = {packages.get_package_path(p) for p in keep_packages}
  for filename in os.listdir(packages.get_packages_path()):
    filepath = os.path.join(packages.get_packages_path(), filename)
    if os.path.isfile(filepath):
      os.unlink(filepath)
    elif os.path.isdir(filepath) and filepath not in prebuilt_paths:
      shutil.rmtree(filepath)


def _update_root_manifest(manifest, packages):
  for package in packages:
    manifest.set_package_version(package)
  manifest.save()


def _fetch_google3_prebuilts():
  """Fetch any outdated or missing prebuilts."""
  prebuilts = _load_prebuilt_configuration()
  manifest = packages.load_root_manifest()
  has_internal_access = _can_access_internal_gcs_bucket()
  bucket = GCS_BUCKET_INTERNAL if has_internal_access else GCS_BUCKET_PUBLIC
  accessible_prebuilts = _filter_accessible_prebuilts(
      prebuilts, has_internal_access)
  wanted_packages = _get_packages(accessible_prebuilts, has_internal_access)
  existing_packages = _find_existing_packages(wanted_packages, manifest)
  missing_packages = wanted_packages - existing_packages

  _remove_obsolete_files(existing_packages)
  _fetch_packages(missing_packages, bucket)

  _write_gn_file(accessible_prebuilts, has_internal_access)
  _write_runtime_deps_file(accessible_prebuilts, has_internal_access)

  _update_root_manifest(manifest, wanted_packages)


def _check_gsutil_on_path():
  return any(os.path.exists(os.path.join(path, 'gsutil.py'))
             for path in os.environ.get('PATH', '').split(os.pathsep))


def main():
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)s %(asctime)s [%(filename)s:%(lineno)d] %(message)s')

  if not _check_gsutil_on_path():
    logging.error(
        'depot_tools must be on your PATH in order to find gsutil.py')
    return 1

  _fetch_google3_prebuilts()
  return 0


if __name__ == '__main__':
  sys.exit(main())
