"""
"""

import os
import sys
import zipfile
import json
import importlib
import threading
import time
import traceback
import hashlib

try:
    import sublime
    import sublime_plugin

    pc = importlib.import_module('Package Control.package_control.package_manager')
    pdm = importlib.import_module('Package Control.package_control.package_disabler')
    # pm = pc.PackageManager()
except:
    pass

# add modules to the system path
dir_path = os.path.dirname(os.path.realpath(__file__))
if os.path.join(dir_path,'modules') not in sys.path:
    sys.path.append(os.path.join(dir_path,'modules'))
if dir_path not in sys.path:
    sys.path.append(dir_path)

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from apiclient.http import MediaFileUpload
from apiclient.discovery import build

working_dir_stack = []

def md5_file(filename):
    file_hash = hashlib.md5()
    with open(filename, "rb") as f:
        chunk = f.read(8192)
        while chunk:
            file_hash.update(chunk)
            chunk = f.read(8192)

    return file_hash.hexdigest()

def md5_string(content):
    md5 = hashlib.md5()
    md5.update(content.encode())
    return md5.hexdigest()


def zipdir(path, ziph, ignore_dirs = [], ignore_files = []):
    # ziph is zipfile handle
    for root, dirs, files in os.walk(path):
        for file in files:
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            ziph.write(os.path.join(root, file))


def push_cwd(path):
    global working_dir_stack
    working_dir_stack.append(os.getcwd())
    os.chdir(path)

def pop_cwd():
    global working_dir_stack
    os.chdir(working_dir_stack.pop())


def is_installed_by_package_control(package_name):
    """Check if installed by package control."""
    settings = sublime.load_settings('Package Control.sublime-settings')
    return package_name in set(settings.get('installed_packages', []))

def get_disabled_packages():
    """Check if disabled by package control."""
    settings = sublime.load_settings('Global.sublime-settings')
    return settings.get('ignored_packages', [])

class GDrive():
    def __init__(self):
        push_cwd(dir_path)
        self.gauth  = GoogleAuth()
        self.gdrive = GoogleDrive(self.gauth)
        pop_cwd()

    def upload_file(self, **kwargs):
        title = kwargs['title']
        content = kwargs['content']
        mimeType = kwargs['mimeType']
        parents = kwargs['parents']
        # override = kwargs['override'] if 'override' in kwargs else False

        # file already exists
        # if override and self.file_exists(title):
        #     return False

        push_cwd(dir_path)
        file = self.gdrive.CreateFile({
            'title': title,
            'mimeType': mimeType,
            'parents': parents
        })
        if os.path.isfile(content):
            file.SetContentFile(content)
        else:
            file.SetContentString(content)
        file.Upload()
        pop_cwd()
        return True

    def upload_file_async(self, **kwargs):
        onDone = kwargs['onDone'] if 'onDone' in kwargs else lambda x: None
        t = threading.Thread(target=lambda : onDone(self.upload_file(**kwargs)))
        t.start()

    def delete_file(self, title):
        fileId = self.file_id(title)
        if fileId is None:
            return False

        push_cwd(dir_path)
        file = self.gdrive.CreateFile({'id': fileId})
        file.Delete()
        pop_cwd()
        return True

    def delete_file_async(self, title, onDone = lambda x: None):
        t = threading.Thread(target=lambda : onDone(self.delete_file(title)))
        t.start()

    def get_file_contents(self, title):
        fileId = self.file_id(title)
        if fileId is None:
            return None

        push_cwd(dir_path)
        file = self.gdrive.CreateFile({'id': fileId})
        content = file.GetContentString()
        pop_cwd()
        return content

    def get_file_contents_async(self, title, onDone = lambda x: None):
        t = threading.Thread(target=lambda : onDone(self.get_file_contents(**kwargs)))
        t.start()

    def download_file(self, **kwargs):
        title = kwargs['title']
        filepath = kwargs['filepath']

        fileId = self.file_id(title)
        if fileId is None:
            return False

        if filepath is None:
            filepath = title

        push_cwd(dir_path)
        file = self.gdrive.CreateFile({'id': fileId})
        file.GetContentFile(filepath)
        pop_cwd()
        return True

    def download_file_async(self, **kwargs):
        onDone = kwargs['onDone'] if 'onDone' in kwargs else lambda x: None
        t = threading.Thread(target=lambda : onDone(self.download_file(**kwargs)))
        t.start()

    def file_id(self, title):
        push_cwd(dir_path)
        query = "title='{}'".format(title)
        fileList = self.gdrive.ListFile({'q': query}).GetList()
        if len(fileList) == 0:
            return None

        file = fileList[0]
        pop_cwd()
        return file['id']

    def file_id_async(self, title, onDone = lambda x: None):
        t = threading.Thread(target=lambda : onDone(self.file_id(title)))
        t.start()

    def file_exists(self, title):
        fileId = self.file_id(title)
        return fileId is not None

    def file_exists_async(self, title, onDone = lambda x: None):
        t = threading.Thread(target=lambda : onDone(self.file_exists(title)))
        t.start()


    def file_info(self, title):
        fileId = self.file_id(title)
        if fileId is None:
            return None

        push_cwd(dir_path)
        file = self.gdrive.CreateFile({'id': fileId})
        file.FetchMetadata(fetch_all=True)
        pop_cwd()
        return file.metadata

    def file_info_async(self, title, onDone = lambda x: None):
        t = threading.Thread(target=lambda : onDone(self.file_info(title)))
        t.start()

    def login(self, timeout = 30):
        if self.logged_in():
            return True
        push_cwd(dir_path)
        gauth = GoogleAuth()
        gauth.LocalWebserverAuth(timeout=timeout)
        try:
            gauth = GoogleAuth()
            gauth.LocalWebserverAuth(timeout=timeout)
        except Exception as e:
            pop_cwd()
            print(e)
            return False
        else:
            pop_cwd()
            return gauth.access_token_expired == False

    def login_async(self, timeout = 60, onDone = lambda x: None):
        t = threading.Thread(target=lambda : onDone(self.login(timeout)))
        t.start()

    def logged_in(self):
        return self.gauth.access_token_expired == False

gdrive = GDrive()

def collect_user_settings(filename):
    zipf = zipfile.ZipFile(os.path.join(sublime.packages_path(), filename), 'w', zipfile.ZIP_DEFLATED)
    push_cwd(sublime.packages_path())
    zipdir("User/", zipf, ['Package Control.cache', '.git'])
    pop_cwd()
    zipf.close()

def extract_user_settings(filename):
    zipf = zipfile.ZipFile(os.path.join(sublime.packages_path(), filename), 'r', zipfile.ZIP_DEFLATED)
    push_cwd(sublime.packages_path())
    zipf.extractall('.')
    pop_cwd()
    zipf.close()


def create_active_state_data(profile):
    local_packages = []
    sublime_packages = []
    package_manager = pc.PackageManager()
    for p in package_manager.list_packages():
        if is_installed_by_package_control(p) == False:
            local_packages.append(p)
        else:
            sublime_packages.append(p)

    return {
        'name': profile,
        'installed_packages': sublime_packages,
        'disabled_packages': get_disabled_packages(),
        'local_packages': local_packages
    }

# This is just an example.  Adjust as desired.
def get_setting(name, default=None):
    settings = sublime.load_settings('ProfileManager.sublime-settings')
    return settings.get(name) or default

def set_setting(name, value):
    settings = sublime.load_settings('ProfileManager.sublime-settings')
    settings.set(name, value)
    sublime.save_settings('ProfileManager.sublime-settings')


def get_meta(name, default=None):
    filepath = os.path.join(sublime.cache_path(), 'profile_manager.meta')
    if os.path.isfile(filepath) == False:
        return default

    with open(filepath, 'r') as f:
        data = json.loads(f.read())
        if name in data:
            return data[name]

    return default

def set_meta(name, value):
    filepath = os.path.join(sublime.cache_path(), 'profile_manager.meta')
    data = {}
    if os.path.isfile(filepath):
        with open(filepath, 'r') as f:
            data = json.loads(f.read())
            if name in data:
                return data[name]

    data[name] = value
    with open(filepath, 'w') as f:
        f.write(json.dumps(data))

def get_active_profile():
    return get_meta('active_profile', 'default')

def current_package_status():
    local_packages = []
    sublime_packages = []
    pm = pc.PackageManager()

    for p in pm.list_packages():
        if is_installed_by_package_control(p) == False:
            local_packages.append(p)
        else:
            sublime_packages.append(p)

    return local_packages, sublime_packages, get_disabled_packages()

# output a ${name}.zip file in the sublime.packages_path()/${name}.zip location
def zip_local_package(name):
    filepath = os.path.join(sublime.packages_path(), name + '.zip')
    zipf = zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED)
    push_cwd(sublime.packages_path())
    zipdir(name, zipf, ['.git'])
    pop_cwd()
    zipf.close()



def get_profile_data(data, name):
    idx = 0
    for x in data['profiles']:
        if x['name'] == name:
            return x, idx
        idx += 1

    return None, -1


def create_profile(profile_name):
    data = gdrive.get_file_contents('profiles_info')
    data = json.loads(data)
    if profile_name in [x['name'] for x in data['profiles']]:
        sublime.error_message('ProfileManager: There is already a profile named: "{}"'.format(profile_name))
        return

    profile, idx = get_profile_data(data, get_active_profile())
    new_profile = {}
    new_profile.update(profile)
    new_profile['name'] = profile_name
    data['profiles'].append(new_profile)

    gdrive.upload_file(**{
        'title': 'profiles_info',
        'content': json.dumps(data),
        'mimeType': 'text/json',
        'parents': [{'id': 'appDataFolder'}],
    })
    print('ProfileManager: Created profile "{}"'.format(profile_name))


def delete_profile(profile_name):
    data = gdrive.get_file_contents('profiles_info')
    data = json.loads(data)

    if profile_name not in [x['name'] for x in data['profiles']]:
        sublime.error_message('ProfileManager: There is no profile named: "{}"'.format(profile_name))
        return
    if profile_name == 'default':
        sublime.error_message('ProfileManager: Cannot delete default package!')
        return

    # we're deleting the active profile, we must switch to the default one before deleting
    if get_meta('active_profile', None) == profile_name:
        print('ProfileManager: Deleting active profile! Switching to default profile')
        set_meta('active_profile', None) # don't sync the profile we're about to delete
        switch_profile('default')

    # remove ${profile_name}
    data['profiles'] = [x for x in data['profiles'] if x['name'] != profile_name]

    # update the profile info
    gdrive.upload_file(**{
        'title': 'profiles_info',
        'content': json.dumps(data),
        'mimeType': 'text/json',
        'parents': [{'id': 'appDataFolder'}],
    })
    print('ProfileManager: Deleted profile "{}"'.format(profile_name))

def are_identical(a,b):
    return json.dumps(a) == json.dumps(b)

def sync_active_profile():
    profile_name = get_meta('active_profile', None)
    if profile_name is None:
        print('ProfileManager: No profile selected!')
        return

    meta = gd.file_info('profiles_info')
    if meta is None:
        print('ProfileManager: Cannot sync changes to profile "{}" because no meta information can be found online!'.format(profile_name))
        return

    # someone else changed the profiles info, we can sync our local changes to the cloud
    elif meta['md5Checksum'] != get_meta('profiles_info'):
        print('ProfileManager: Cannot push updates to profile "{}" because of remote changes!'.format(profile_name))
        return

    print('ProfileManager: ----------------------------------------------------------------------------------')
    print('ProfileManager: Syncing profile "{}"'.format(profile_name))
    print('ProfileManager: ----------------------------------------------------------------------------------')

    if gdrive.logged_in() == False:
        print('ProfileManager: Cannot sync profile "{}" because we are not logged in!'.format(profile_name))
        return False

    gd = GDrive()
    gd.login()
    data = gd.get_file_contents('profiles_info')
    profile_info = json.loads(data)

    profile, idx = get_profile_data(profile_info, profile_name)
    new_profile = create_active_state_data(profile_name)

    # need to update the profile info
    if are_identical(new_profile, profile) == False:
        profile_info['profiles'][idx] = new_profile
        gd.upload_file(**{
            'title': 'profiles_info',
            'content': json.dumps(profile_info),
            'mimeType': 'text/json',
            'parents': [{'id': 'appDataFolder'}],
        })

    upload_local_packages_to(gd, new_profile)
    upload_settings_to(gd, profile_name)

    # update the md5 of the profiles meta info
    set_meta('profiles_info', md5_string(json.dumps(profile_info)))

    print('ProfileManager: ----------------------------------------------------------------------------------')
    print('ProfileManager: Synced profile "{}"'.format(profile_name))
    print('ProfileManager: ----------------------------------------------------------------------------------')

def switch_profile(profile_name):
    sync_active_profile()

    # same profile, nothing to do
    if get_meta('active_profile', None) == profile_name:
        print('ProfileManager: Profile "{}" is already active!'.format(profile_name))
        return

    if gdrive.logged_in() == False:
        print('ProfileManager: Cannot sync profile "{}" because we are not logged in!'.format(profile_name))
        return False

    gd = GDrive()
    gd.login()

    meta = gd.file_info('profiles_info')
    if meta is None:
        print('ProfileManager: Cannot switch to profile "{}" because no meta information can be found online!'.format(profile_name))
        return

    dataStr = gd.get_file_contents('profiles_info')
    data = json.loads(dataStr)

    if profile_name not in [x['name'] for x in data['profiles']]:
        sublime.error_message('ProfileManager: There is no profile named: "{}"'.format(profile_name))
        return

    pm = pc.PackageManager()
    pd = pdm.PackageDisabler()

    profile, idx = get_profile_data(data, profile_name)

    set_meta('active_profile', profile_name)

    profile_installed_packages = [x for x in profile['installed_packages']]
    profile_local_packages = [x for x in profile['local_packages']]
    profile_disabled_packages = [x for x in profile['disabled_packages']]
    profile_all_packages = profile_installed_packages + profile_local_packages

    local_packages, sublime_packages, disabled_packages = current_package_status()

    extra_sublime_packages = [x for x in sublime_packages if x not in profile_all_packages]
    extra_local_packages = [x for x in local_packages if x not in profile_local_packages]
    extra_packages = extra_sublime_packages + extra_local_packages
    missing_sublime_packages = [x for x in profile_installed_packages if x not in sublime_packages]
    missing_local_packages = [x for x in profile_local_packages if x not in local_packages]
    disable_sublime_packages = [x for x in profile_disabled_packages if x not in disabled_packages]
    enable_sublime_packages = [x for x in profile_all_packages if x in disabled_packages and x not in profile_disabled_packages ]

    print('--------------------------------------------------')
    print('local_packages', local_packages)
    print('sublime_packages', sublime_packages)
    print('disabled_packages', disabled_packages)
    print('--------------------------------------------------')
    print('profile_installed_packages', profile_installed_packages)
    print('profile_local_packages', profile_local_packages)
    print('profile_disabled_packages', profile_disabled_packages)
    print('profile_all_packages', profile_all_packages)
    print('--------------------------------------------------')

    print('--------------------------------------------------')
    print('missing_sublime_packages', missing_sublime_packages)
    print('extra_sublime_packages', extra_sublime_packages)
    print('extra_local_packages', extra_local_packages)
    print('missing_local_packages', missing_local_packages)
    print('disable_sublime_packages', disable_sublime_packages)
    print('enable_sublime_packages', enable_sublime_packages)
    print('--------------------------------------------------')


    if 'ProfileManager' in extra_local_packages:
        extra_local_packages.remove('ProfileManager')
    if 'ProfileManager' in extra_packages:
        extra_packages.remove('ProfileManager')

    # extract user settings
    download_settings_from(gd, profile_name)

    # install missing packages
    for package in missing_sublime_packages:
        print('ProfileManager: Installing "{}"'.format(package))
        pm.install_package(package)

    # uninstall packages not used by this profile
    for package in extra_packages:
        print('ProfileManager: Removing "{}"'.format(package))
        pm.remove_package(package)

    # install missing local packages
    for package in missing_local_packages:
        package = profile_name + "_" + package
        print('ProfileManager: Installing local package "{}"'.format(package))
        filepath = os.path.join(sublime.packages_path(), package) + '.zip'
        gdrive.download_file(**{
            'title': package,
            'filepath': filepath,
        })
        # extract local package
        extract_user_settings(package + '.zip')
        # os.remove(filepath)

    # enable/disable installed packages not used by this profile
    for package in disable_sublime_packages:
        print('ProfileManager: Disabling "{}"'.format(package))
        pd.disable_packages(package, 'disable')

    for package in enable_sublime_packages:
        print('ProfileManager: Enabling "{}"'.format(package))
        pd.reenable_package(package, 'enable')

    # update the md5 of the profiles meta info
    set_meta('profiles_info', md5_string(dataStr))

    update_profile_status()

def download_settings_from(gd, profile_name):
    filename = profile_name + '-user-settings.zip'
    filepath = os.path.join(sublime.packages_path(), filename)
    gd.download_file(**{
        'title': filename,
        'filepath': filepath,
    })
    extract_user_settings(filename)
    os.remove(filepath)

def upload_settings_to(gd, profile_name):
    filename = profile_name + '-user-settings.zip'
    filepath = os.path.join(sublime.packages_path(), filename)
    collect_user_settings(filename)
    push_cwd(sublime.packages_path())
    meta = gd.file_info(filename)
    md5 = md5_file(filepath)
    if meta is None or meta['md5Checksum'] != md5:
        print('ProfileManager: Updating user settings because they changed for profile "{}"'.format(profile_name))
        gd.upload_file(**{
            'title': filename,
            'content': filepath,
            'mimeType': 'application/zip',
            'parents': [{'id': 'appDataFolder'}],
        })
    else:
        print('ProfileManager: User settings are up to date for profile "{}"'.format(profile_name))

    os.remove(filepath)
    pop_cwd()

def upload_local_packages_to(gd, profile_info):
    packages = set()
    profile_name = profile_info['name']

    for package in profile_info['local_packages']:
        packages.add(package)

    for name in packages:
        packageName = name
        name = profile_name + "_" + packageName
        meta = gd.file_info(name)
        filepath = os.path.join(sublime.packages_path(), packageName + ".zip")
        if os.path.isfile(filepath):
            os.remove(filepath)

        zip_local_package(packageName)
        upload_reason = ''
        if meta is None:
            upload_reason = '{} was not uploaded'.format(name)
        elif meta['md5Checksum'] != md5_file(filepath):
            upload_reason = '{} is out of date'.format(name)
            # gd.download_file(**{
            #     'title': name,
            #     'filepath': filepath + '.cloud.zip',
            # })

        else:
            print('ProfileManager:  Skipping {} because it is up to date!'.format(name))
            os.remove(filepath)
            continue

        print('ProfileManager: Uploading local package because {}'.format(upload_reason))
        gd.upload_file(**{
            'title': name,
            'content': filepath,
            'mimeType': 'application/zip',
            'parents': [{'id': 'appDataFolder'}],
        })
        os.remove(filepath)

# sublime.active_window().run_command("advanced_install_package", {"packages": "package1,package2"})
def on_login(result):
    if result is not True:
        content = 'ProfileManager: Failed to login, please try again manually using the "ProfileManager: Login" command to activate the functionality.'
        sublime.error_message(content)
    else:
        # download profile metadata
        data = gdrive.get_file_contents('profiles_info')

        # no profile data stored on this account, this must be the first login
        # store the current state as "default" profile
        if data is None:
            data = {
                'profiles': [create_active_state_data('default')]
            }
            print('ProfileManager: No profile found, creating a default profile!', data)
            gdrive.upload_file(**{
                'title': 'profiles_info',
                'content': json.dumps(data),
                'mimeType': 'text/json',
                'parents': [{'id': 'appDataFolder'}],
            })
            upload_local_packages(gdrive, data)
            upload_settings_to(gdrive, 'default')
            print('ProfileManager: Profiles synced!', data)
        # new sublime instance, activate the default profile
        elif get_meta('active_profile', None) is None:
            print('ProfileManager: No profile selected, activating default profile!', data)
            switch_profile('default')
        else:
            print('ProfileManager: Loaded user profile!')


gdrive.login_async(onDone = on_login)

####################################################################################
###                         SUBLIME COMMANDS                                     ###
####################################################################################
class ProfilesLogin(sublime_plugin.ApplicationCommand):
    def run(self):
        gdrive.login()

class ProfilesList(sublime_plugin.ApplicationCommand):
    def run(self):
        if gdrive.logged_in() == False:
            content = 'ProfileManager: You are not logged in, please try to log in manually using the "ProfileManager: Login" command'
            sublime.error_message(content)
        else:
            data = gdrive.get_file_contents('profiles_info')
            data = json.loads(data)
            profiles = [x['name'] for x in data['profiles']]
            profiles.remove(get_active_profile())
            profiles = [get_active_profile()] + profiles
            sublime.active_window().show_quick_panel(profiles, lambda x: None)

class ProfilesSwitch(sublime_plugin.ApplicationCommand):
    def run(self):
        if gdrive.logged_in() == False:
            content = 'ProfileManager: You are not logged in, please try to log in manually using the "ProfileManager: Login" command'
            sublime.error_message(content)
        else:
            data = gdrive.get_file_contents('profiles_info')
            data = json.loads(data)
            profile_names = [x['name'] for x in data['profiles']]
            profile_names.remove(get_active_profile())
            def fun(x):
                if x < 0:
                    return

                t = threading.Thread(target=lambda : switch_profile(profile_names[x]) )
                t.start()
            sublime.active_window().show_quick_panel(profile_names, fun)

class ProfilesDelete(sublime_plugin.ApplicationCommand):
    def run(self):
        if gdrive.logged_in() == False:
            content = 'ProfileManager: You are not logged in, please try to log in manually using the "ProfileManager: Login" command'
            sublime.error_message(content)
        else:
            data = gdrive.get_file_contents('profiles_info')
            data = json.loads(data)
            profile_names = [x['name'] for x in data['profiles']]
            profile_names.remove('default')
            def fun(x):
                if x < 0:
                    return

                t = threading.Thread(target=lambda : delete_profile(profile_names[x]) )
                t.start()
            sublime.active_window().show_quick_panel(profile_names, fun)

class ProfilesSync(sublime_plugin.ApplicationCommand):
    def run(self):
        if gdrive.logged_in() == False:
            content = 'ProfileManager: You are not logged in, please try to log in manually using the "ProfileManager: Login" command'
            sublime.error_message(content)
        else:
            t = threading.Thread(target=sync_active_profile)
            t.start()


class ProfilesCreate(sublime_plugin.ApplicationCommand):
    def run(self):
        if gdrive.logged_in() == False:
            content = 'ProfileManager: You are not logged in, please try to log in manually using the "ProfileManager: Login" command'
            sublime.error_message(content)
        else:
            sublime.active_window().show_input_panel('Profile name', '', lambda x: create_profile(x), None, None)

keep_syncing = True
syncing = True
sync_time = get_setting('sync_time', 5 * 60)
sync_thread = None

def sync_active_profile_thread():
    global keep_syncing
    global syncing
    last_time = time.time()

    try:
        while keep_syncing:
            elapsed_time = time.time() - last_time
            if elapsed_time >= sync_time:
                last_time = time.time()
                sync_active_profile()
                print('ProfileManager: Syncing complete!')
            time.sleep(0.1)
    except Exception as e:
        traceback.print_exc(e)
        print('ProfileManager: sync thread exception caught!', e)

    syncing = False
    # print('ProfileManager: sync thread stopped!')

def update_profile_status():
    profile = get_active_profile()
    for w in sublime.windows():
        for v in w.views():
            v.set_status('user_profile', profile)

def plugin_loaded():
    global sync_thread
    # print('ProfileManager: sync thread started!')
    sync_thread = threading.Thread(target=sync_active_profile_thread)
    sync_thread.start()
    update_profile_status()

def plugin_unloaded():
    # print('ProfileManager: plugin_unloaded!')
    global sync_thread
    global keep_syncing
    keep_syncing = False
    while syncing:
        # print('ProfileManager: waiting for sync thread to settle!')
        time.sleep(0.1)
    if sync_thread is not None:
        sync_thread.join()
    sync_thread = None

