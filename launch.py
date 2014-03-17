#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2012-2013 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors :
#       Luis Cañas-Díaz <lcanas@bitergia.com>
#       Daniel Izquierdo Cortázar <dizquierdo@bitergia.com>
#       Alvaro del Castillo San Felix <acs@bitergia.com>
#
# launch.py
#
# This script automates the execution of some of the metrics grimoire 
# tools (Bicho, MLStats, CVSAnaly). It uses configuration files to get
# the parameters. Finally it execute R scripts in order to generate the
# JSON files

import os
import subprocess
import sys
import time
import distutils.dir_util
import json
import datetime as dt
from optparse import OptionGroup, OptionParser
from ConfigParser import SafeConfigParser

import MySQLdb

# conf variables from file(see read_main_conf)
options = {}

# global var for directories
project_dir = ''
msg_body = ''#project_dir + '/log/launch.log'
scm_dir = ''#os.getcwd() + '/../scm/'
conf_dir = ''#os.getcwd() + '/../conf/'
json_dir = ''
production_dir = ''

tools = {
    'scm' :'/usr/local/bin/cvsanaly2',
    'its': '/usr/local/bin/bicho',
    'scr': '/usr/local/bin/bicho',
    'mls': '/usr/local/bin/mlstats',
    'irc': '/usr/local/bin/irc_analysis.py',
    'mediawiki': '/usr/local/bin/mediawiki_analysis.py',
    'r': '/usr/bin/R',
    'git': '/usr/bin/git',
    'svn': '/usr/bin/svn',
    'mysqldump': '/usr/bin/mysqldump',
    'compress': '/usr/bin/7zr',
    'rm': '/bin/rm',
    'rsync': '/usr/bin/rsync'
}

def get_options():
    parser = OptionParser(usage='Usage: %prog [options]',
                          description='Update data, process it and obtain JSON files',
                          version='0.1')
    parser.add_option('-d','--dir', dest='project_dir',
                     help='Path with the configuration of the project', default=None)
    parser.add_option('-q','--quiet', action='store_true', dest='quiet_mode',
                      help='Disable messages in standard output', default=False)
    parser.add_option('-s','--section', dest='section',
                     help='Section to be executed', default=None)
    parser.add_option('-t','--subtask', dest='subtask',
                     help='Sub section to be executed (only for r)', default=None)
    parser.add_option('-g', '--debug', action='store_true', dest='debug',
                        help='Enable debug mode', default=False)
    parser.add_option('--python', dest='python', action="store_true",
                      help='Use python script for getting metrics.')

    (ops, args) = parser.parse_args()

    if ops.project_dir is None:
        parser.print_help()
        print("Project dir is required")
        sys.exit(1)
    return ops

def initialize_globals(pdir):
    global project_dir
    global msg_body
    global scm_dir
    global irc_dir
    global conf_dir
    global downs_dir
    global json_dir
    global production_dir
    global identities_dir
    global downloads_dir
    global r_dir

    project_dir = pdir
    msg_body = project_dir + '/log/launch.log'
    scm_dir = project_dir + '/scm/'
    irc_dir = project_dir + '/irc/'
    conf_dir = project_dir + '/conf/'
    downs_dir = project_dir + '/downloads/'
    json_dir = project_dir + '/json/'
    production_dir = project_dir + '/production/'
    # identities_dir = project_dir + '/tools/VizGrimoireR/misc/'
    identities_dir = project_dir + '/tools/VizGrimoireUtils/identities/'
    downloads_dir = project_dir + '/tools/VizGrimoireUtils/downloads/'
    r_dir = project_dir + '/tools/VizGrimoireR/vizGrimoireJS/'

def read_main_conf():
    parser = SafeConfigParser()
    conf_file = project_dir + '/conf/main.conf'
    fd = open(conf_file, 'r')
    parser.readfp(fd)
    fd.close()

    sec = parser.sections()
    for s in sec:
        options[s] = {}
        opti = parser.options(s)
        for o in opti:
            # first, some special cases
            if o == 'debug':
                options[s][o] = parser.getboolean(s,o)
            elif o == 'trackers':
                trackers = parser.get(s,o).split(',')
                options[s][o] = [t.replace('\n', '') for t in trackers]
            else:
                options[s][o] = parser.get(s,o)

    return options

# git specific: search all repos in a directory recursively
def get_scm_repos(dir = scm_dir):
    all_repos = []

    if (dir == ''):  dir = scm_dir
    if not os.path.isdir(dir): return all_repos

    repos = os.listdir(dir)

    for r in repos:
        repo_dir_git = os.path.join(dir,r,".git")
        repo_dir_svn = os.path.join(dir,r,".svn")
        if not os.path.isdir(repo_dir_git) and not os.path.isdir(repo_dir_svn):
            sub_repos = get_scm_repos(os.path.join(dir,r))
            for sub_repo in sub_repos:
                all_repos.append(sub_repo)
        else:
            all_repos.append(os.path.join(dir,r))
    return all_repos

def update_scm(dir = scm_dir):
    compose_msg("SCM is being updated")
    repos = get_scm_repos()
    updated = False

    for r in repos:
        os.chdir(r)
        if os.path.isdir(os.path.join(dir,r,".git")):
            os.system("git pull >> %s 2>&1" %(msg_body))
        elif os.path.isdir(os.path.join(dir,r,".svn")):
            os.system("svn update >> %s 2>&1" %(msg_body))
        else: compose_msg(r + " not git nor svn.")
        compose_msg(r + " update ended")

    if updated: compose_msg("[OK] SCM updated")

def check_tool(cmd):
    return os.path.isfile(cmd) and os.access(cmd, os.X_OK)
    return True

def check_tools():
    tools_ok = True
    for tool in tools:
        if not check_tool(tools[tool]):
            compose_msg(tools[tool]+" not found or not executable.")
            print (tools[tool]+" not found or not executable.")
            tools_ok = False
    if not tools_ok: print ("Missing tools. Some reports could not be created.")

def launch_checkdbs():
    dbs = []
    db_user = options['generic']['db_user']
    db_password = options['generic']['db_password']

    if options['generic'].has_key('db_cvsanaly'):
        dbs.append(options['generic']['db_cvsanaly'])
    if options['generic'].has_key('db_bicho'):
        dbs.append(options['generic']['db_bicho'])
    # mlstats creates the db if options['generic'].has_key('db_mlstats'): 
    if options['generic'].has_key('db_gerrit'):
        dbs.append(options['generic']['db_gerrit'])
    if options['generic'].has_key('db_irc'):
        dbs.append(options['generic']['db_irc'])
    if options['generic'].has_key('db_mediawiki'):
        dbs.append(options['generic']['db_mediawiki'])
    for dbname in dbs:
        try:
             db = MySQLdb.connect(user = db_user, passwd = db_password,  db = dbname)
             db.close()
        except:
            print ("Can't connect to " + dbname)
            db = MySQLdb.connect(user = db_user, passwd = db_password)
            cursor = db.cursor()
            query = "CREATE DATABASE " + dbname + " CHARACTER SET utf8 COLLATE utf8_unicode_ci"
            cursor.execute(query)
            db.close()
            print (dbname+" created")

def launch_cvsanaly():
    # using the conf executes cvsanaly for the repos inside scm dir
    if options.has_key('cvsanaly'):
        if not check_tool(tools['scm']):
            return
        update_scm()
        compose_msg("cvsanaly is being executed")
        launched = False
        extensions = options['cvsanaly']['extensions']
        db_name = options['generic']['db_cvsanaly']
        db_user = options['generic']['db_user']
        db_pass = options['generic']['db_password']
        if (db_pass == ""): db_pass = "''"

        # we launch cvsanaly against the repos
        repos = get_scm_repos()
        for r in repos:
            launched = True
            os.chdir(r)
            cmd = tools['scm'] + " -u %s -p %s -d %s --extensions=%s >> %s 2>&1" \
                        %(db_user, db_pass, db_name, extensions, msg_body)
            compose_msg(cmd)
            os.system(cmd)

        if launched:
            compose_msg("[OK] cvsanaly executed")
        else:
            compose_msg("[SKIPPED] cvsanaly was not executed")
    else:
        compose_msg("[SKIPPED] cvsanaly not executed, no conf available")

def launch_bicho():
    # reads a conf file with all of the information and launches bicho
    if options.has_key('bicho'):
        if not check_tool(tools['its']):
            return

        compose_msg("bicho is being executed")
        launched = False

        database = options['generic']['db_bicho']
        db_user = options['generic']['db_user']
        db_pass = options['generic']['db_password']
        delay = options['bicho']['delay']
        backend = options['bicho']['backend']
        backend_user = backend_password = None
        if options['bicho'].has_key('backend_user'):
            backend_user = options['bicho']['backend_user']
        if options['bicho'].has_key('backend_password'):
            backend_password = options['bicho']['backend_password']
        trackers = options['bicho']['trackers']
        log_table = None
        debug = options['bicho']['debug']
        if options['bicho'].has_key('log_table'):
            log_table = options['bicho']['log_table']

        # we compose some flags
        flags = ""
        if debug:
            flags = flags + " -g"

        # we'll only create the log table in the last execution
        cont = 0
        last = len(trackers)

        for t in trackers:
            launched = True
            cont = cont + 1

            if cont == last and log_table:
                flags = flags + " -l"

            user_opt = ''
            if backend_user and backend_password:
                user_opt = '--backend-user=%s --backend-password=%s' % (backend_user, backend_password)
            cmd = tools['its'] + " --db-user-out=%s --db-password-out=%s --db-database-out=%s -d %s -b %s %s -u %s %s >> %s 2>&1" \
                        % (db_user, db_pass, database, str(delay), backend, user_opt, t, flags, msg_body)
            compose_msg(cmd)
            os.system(cmd)
        if launched:
            compose_msg("[OK] bicho executed")
        else:
            compose_msg("[SKIPPED] bicho was not executed")
    else:
        compose_msg("[SKIPPED] bicho not executed, no conf available")

def launch_gerrit():
    # reads a conf file with all of the information and launches bicho
    if options.has_key('gerrit'):

        if not check_tool(tools['scr']):
            return

        compose_msg("bicho (gerrit) is being executed")
        launched = False

        database = options['generic']['db_gerrit']
        db_user = options['generic']['db_user']
        db_pass = options['generic']['db_password']
        delay = options['gerrit']['delay']
        backend = options['gerrit']['backend']
        trackers = options['gerrit']['trackers']
        projects = options['gerrit']['projects']
        debug = options['gerrit']['debug']
        log_table = None
        if options['gerrit'].has_key('log_table'):
            log_table = options['gerrit']['log_table']

        flags = ""
        if debug:
            flags = flags + " -g"

        # we'll only create the log table in the last execution
        cont = 0
        last = len(projects.split(","))

        for project in projects.split(","):
            launched = True
            cont = cont + 1

            if cont == last and log_table:
                flags = flags + " -l"

            g_user = ''
            if options['gerrit'].has_key('user'):
                g_user = '--backend-user ' + options['gerrit']['user']
            cmd = tools['scr'] + " --db-user-out=%s --db-password-out=%s --db-database-out=%s -d %s -b %s %s -u %s --gerrit-project=%s %s >> %s 2>&1" \
                            % (db_user, db_pass, database, str(delay), backend, g_user, trackers[0], project, flags, msg_body)
            compose_msg(cmd)
            os.system(cmd)


        if launched:
            compose_msg("[OK] bicho (gerrit) executed")
        else:
            compose_msg("[SKIPPED] bicho (gerrit) not executed")
    else:
        compose_msg("[SKIPPED] bicho (gerrit) not executed, no conf available")



def launch_mlstats():
    if options.has_key('mlstats'):
        if not check_tool(tools['mls']):
            return

        compose_msg("mlstats is being executed")
        launched = False
        db_admin_user = options['generic']['db_user']
        db_user = db_admin_user
        db_pass = options['generic']['db_password']
        db_name = options['generic']['db_mlstats']
        mlists = options['mlstats']['mailing_lists']
        for m in mlists.split(","):
            launched = True
            cmd = tools['mls'] + " --no-report --db-user=\"%s\" --db-password=\"%s\" --db-name=\"%s\" --db-admin-user=\"%s\" --db-admin-password=\"%s\" \"%s\" >> %s 2>&1" \
                        %(db_user, db_pass, db_name, db_admin_user, db_pass, m, msg_body)
            compose_msg(cmd)
            os.system(cmd)
        if launched:
            compose_msg("[OK] mlstats executed")
        else:
            compose_msg("[SKIPPED] mlstats not executed")
    else:
        compose_msg("[SKIPPED] mlstats was not executed, no conf available")

def launch_irc():
    if options.has_key('irc'):
        if not check_tool(tools['irc']):
            return

        compose_msg("irc_analysis is being executed")
        launched = False
        db_admin_user = options['generic']['db_user']
        db_user = db_admin_user
        db_pass = options['generic']['db_password']
        db_name = options['generic']['db_irc']
        format = 'plain'
        if options['irc'].has_key('format'):
            format = options['irc']['format']
        channels = os.listdir(irc_dir)
        os.chdir(irc_dir)
        for channel in channels:
            if not os.path.isdir(os.path.join(irc_dir,channel)): continue
            launched = True
            cmd = tools['irc'] + " --db-user=\"%s\" --db-password=\"%s\" --database=\"%s\" --dir=\"%s\" --channel=\"%s\" --format %s>> %s 2>&1" \
                        % (db_user, db_pass, db_name, channel, channel, format, msg_body)
            compose_msg(cmd)
            os.system(cmd)
        if launched:
            compose_msg("[OK] irc_analysis executed")
        else:
            compose_msg("[SKIPPED] irc_analysis not executed")
    else:
        compose_msg("[SKIPPED] irc_analysis was not executed, no conf available")

def launch_mediawiki():
    if options.has_key('mediawiki'):
        if not check_tool(tools['mediawiki']):
            return

        compose_msg("mediawiki_analysis is being executed")
        launched = False
        db_admin_user = options['generic']['db_user']
        db_user = db_admin_user
        db_pass = options['generic']['db_password']
        db_name = options['generic']['db_mediawiki']
        sites = options['mediawiki']['sites']

        for site in sites.split(","):
            launched = True
            # ./mediawiki_analysis.py --database acs_mediawiki_rdo_2478 --db-user root --url http://openstack.redhat.com
            cmd = tools['mediawiki'] + " --db-user=\"%s\" --db-password=\"%s\" --database=\"%s\" --url=\"%s\" >> %s 2>&1" \
                      %(db_user, db_pass, db_name,  sites, msg_body)
            compose_msg(cmd)
            os.system(cmd)
        if launched:
            compose_msg("[OK] mediawiki_analysis executed")
        else:
            compose_msg("[SKIPPED] mediawiki_analysis not executed")
    else:
        compose_msg("[SKIPPED] mediawiki_analysis was not executed, no conf available")

def launch_downloads():
    # check if downloads option exists. If it does, downloads are executed
    if options.has_key('downloads'):
        compose_msg("downloads analysis is being executed")
        url_user = options['downloads']['url_user']
        url_pass = options['downloads']['url_password']
        url = options['downloads']['url']
        db_name = options['generic']['db_downloads']
        db_user = options['generic']['db_user']
        db_password = options['generic']['db_password']
 
        # sh script: $1 output dir, $2 url user, $3 url pass, $4 url, $5 db user, $6 db pass
        cmd = "%s/downloads.sh %s %s %s %s %s %s" \
              % (downloads_dir, downs_dir, url_user, url_pass, url, db_user, db_name)
        compose_msg(cmd)
        os.system(cmd)
        compose_msg("[OK] downloads executed")


def launch_rscripts():
    # reads data about r scripts for a conf file and execute it
    if options.has_key('r'):
        if not check_tool(tools['r']):
            return

        compose_msg("R scripts being launched")

        conf_file = project_dir + '/conf/main.conf'

        # script = options['r']['rscript']
        script = "run-analysis.py"
        # path = options['r']['rscripts_path']
        path = r_dir

        params = get_options()

        r_section = ''
        if params.subtask:
            r_section = "-s " + params.subtask
        if params.debug:
            r_section += " -g "
        python_scripts = ""
        if params.python:
            python_scripts = "--python"

        os.chdir(path)
        cmd = "./%s -f %s %s %s >> %s 2>&1" % (script, conf_file, r_section, python_scripts, msg_body)
        compose_msg(cmd)
        os.system(cmd)

        compose_msg("[OK] R scripts executed")
    else:
        compose_msg("[SKIPPED] R scripts were not executed, no conf available")

def get_ds_identities_cmd(db, type):
    idir = identities_dir
    db_user = options['generic']['db_user']
    db_pass = options['generic']['db_password']
    if (db_pass == ""): db_pass="''"
    db_scm = options['generic']['db_cvsanaly']
    db_ids = db_scm
    cmd = "%s/datasource2identities.py -u %s -p %s --db-name-ds=%s --db-name-ids=%s --data-source=%s>> %s 2>&1" \
            % (idir, db_user, db_pass, db, db_ids, type, msg_body)
    return cmd

def launch_identity_scripts():
    # using the conf executes cvsanaly for the repos inside scm dir
    if options.has_key('identities'):
        compose_msg("Unify identity scripts are being executed")
        # idir = options['identities']['iscripts_path']
        idir = identities_dir
        db_user = options['generic']['db_user']
        db_pass = options['generic']['db_password']
        if (db_pass == ""): db_pass="''"

        if options['generic'].has_key('db_cvsanaly'):
            # TODO: -i no is needed in first execution
            db_scm = options['generic']['db_cvsanaly']
            cmd = "%s/unifypeople.py -u %s -p %s -d %s >> %s 2>&1" % (idir, db_user, db_pass, db_scm, msg_body)
            compose_msg(cmd)
            os.system(cmd)
            # Companies are needed in Top because bots are included in a company
            cmd = "%s/domains_analysis.py -u %s -p %s -d %s >> %s 2>&1" % (idir, db_user, db_pass, db_scm, msg_body)
            compose_msg(cmd)
            os.system(cmd)

        if options['generic'].has_key('db_bicho'):
            db_its = options['generic']['db_bicho']
            cmd = get_ds_identities_cmd(db_its, 'its')
            compose_msg(cmd)
            os.system(cmd)

        # Gerrit use the same schema than its: both use bicho tool              
        if options['generic'].has_key('db_gerrit'):
            db_gerrit = options['generic']['db_gerrit']
            cmd = get_ds_identities_cmd(db_gerrit, 'scr')
            compose_msg(cmd)
            os.system(cmd)

        if options['generic'].has_key('db_mlstats'):
            db_mls = options['generic']['db_mlstats']
            cmd = get_ds_identities_cmd(db_mls, 'mls')
            compose_msg(cmd)
            os.system(cmd)

        if options['generic'].has_key('db_irc'):
            db_irc = options['generic']['db_irc']
            cmd = get_ds_identities_cmd(db_irc, 'irc')
            compose_msg(cmd)
            os.system(cmd)
        if options['generic'].has_key('db_mediawiki'):
            db_mediawiki = options['generic']['db_mediawiki']
            cmd = get_ds_identities_cmd(db_mediawiki, 'mediawiki')
            compose_msg(cmd)
            os.system(cmd)
        if options['identities'].has_key('countries'):
            cmd = "%s/load_ids_mapping.py -m countries -t true -u %s -p %s --database %s >> %s 2>&1" \
                        % (idir, db_user, db_pass, db_scm, msg_body)
            compose_msg(cmd)
            os.system(cmd)
        if options['identities'].has_key('companies'):
            cmd = "%s/load_ids_mapping.py -m companies -t true -u %s -p %s --database %s >> %s 2>&1" \
                        % (idir, db_user, db_pass, db_scm, msg_body)
            compose_msg(cmd)
            os.system(cmd)

        compose_msg("[OK] Identity scripts executed")
    else:
        compose_msg("[SKIPPED] Unify identity scripts not executed, no conf available")

def compose_msg(text):
    # append text to log file
    fd = open(msg_body, 'a')
    time_tag = '[' + time.strftime('%H:%M:%S') + ']'
    fd.write(time_tag + ' ' + text)
    fd.write('\n')
    fd.close()

def reset_log():
    # remove log file
    try:
        os.remove(msg_body)
    except OSError:
        fd = open(msg_body, 'w')
        fd.write('')
        fd.close()

def launch_copy_json():
    # copy JSON files to other directories
    # This option helps when having more than one automator, but all of the
    # json files should be moved to a centralized directory
    if options.has_key('copy-json'):
        compose_msg("Copying JSON files to another directory")
        destination = os.path.join(project_dir,options['copy-json']['destination_json'])
        distutils.dir_util.copy_tree(json_dir, destination)

def launch_commit_jsones():
    # copy JSON files and commit + push them
    if options.has_key('git-production'):

        if not check_tool(tools['git']):
            return

        compose_msg("Commiting new JSON files with git")

        destination = os.path.join(project_dir,options['git-production']['destination_json'])
        distutils.dir_util.copy_tree(json_dir, destination)

        fd = open(msg_body, 'a')

        pr = subprocess.Popen(['/usr/bin/git', 'pull'],
                              cwd=os.path.dirname(destination),
                              stdout=fd, 
                              stderr=fd, 
                              shell=False)
        (out, error) = pr.communicate()

        pr = subprocess.Popen(['/usr/bin/git', 'add', './*'],
                              cwd=os.path.dirname(destination),
                              stdout=fd, 
                              stderr=fd, 
                              shell=False)
        (out, error) = pr.communicate()

        pr = subprocess.Popen(['/usr/bin/git', 'commit', '-m', 'JSON updated by the Owl Bot'],
                              cwd=os.path.dirname(destination),
                              stdout=fd, 
                              stderr=fd, 
                              shell=False)
        (out, error) = pr.communicate()

        pr = subprocess.Popen(['/usr/bin/git', 'push', 'origin', 'master'],
                              cwd=os.path.dirname(destination),
                              stdout=fd, 
                              stderr=fd, 
                              shell=False)
        (out, error) = pr.communicate()

        fd.close()

def launch_database_dump():
    # copy and compression of database to be rsync with customers
    if options.has_key('db-dump'):

        if not check_tool(tools['mysqldump']) or not check_tool(tools['compress']) or not check_tool(tools['rm']):
            return

        compose_msg("Dumping databases")

        dbs = []

        # databases
        # this may fail if any of the four is not found
        db_user = options['generic']['db_user']

        if options['generic'].has_key('db_bicho'):
            dbs.append([options['generic']['db_bicho'], 'tickets']);
        if options['generic'].has_key('db_cvsanaly'):
            dbs.append([options['generic']['db_cvsanaly'],'source_code']);
        if options['generic'].has_key('db_mlstats'):
            dbs.append([options['generic']['db_mlstats'],'mailing_lists']);
        if options['generic'].has_key('db_gerrit'):
            dbs.append([options['generic']['db_gerrit'],'reviews']);
        if options['generic'].has_key('db_irc'):
            dbs.append([options['generic']['db_irc'],'irc']);
        if options['generic'].has_key('db_mediawiki'):
            dbs.append([options['generic']['db_mediawiki'],'mediawiki']);

        fd = open(msg_body, 'a')
        destination = os.path.join(project_dir,options['db-dump']['destination_db_dump'])


        # it's supposed to have db_user as root user
        for db in dbs:
            dest_mysql_file = destination + db[1] + '.mysql'
            dest_7z_file = dest_mysql_file + '.7z'

            fd_dump = open(dest_mysql_file, 'w')
            # Creation of dump file
            pr = subprocess.Popen([tools['mysqldump'], '-u', db_user, db[0]],
                     stdout = fd_dump,
                     stderr = fd,
                     shell = False)
            (out, error) = pr.communicate()
            fd_dump.close()

            # Creation of compressed dump file
            pr = subprocess.Popen([tools['compress'], 'a', dest_7z_file, dest_mysql_file],
                     stdout = fd,
                     stderr = fd,
                     shell = False)
            (out, error) = pr.communicate()

            # Remove not compressed file
            pr = subprocess.Popen([tools['rm'], dest_mysql_file],
                     stdout = fd,
                     stderr = fd,
                     shell = False)
            (out, error) = pr.communicate()

        fd.close()

def launch_json_dump():
    # copy and compression of json files to be rsync with customers
    if options.has_key('json-dump'):

        origin = options['json-dump']['origin_json_dump']
        origin = origin + '*json'
        dest = options['json-dump']['destination_json_dump']

        fd = open(msg_body, 'a')

        pr = subprocess.Popen([tools['compress'], 'a', dest, origin],
                 stdout = fd,
                 stderr = fd,
                 shell = False)
        (out, error) = pr.communicate()

def launch_rsync():
    # copy JSON files and commit + push them
    if options.has_key('rsync'):

        if not check_tool(tools['rsync']):
            return

        compose_msg("rsync to production server")

        fd = open(msg_body, 'a')

        destination = options['rsync']['destination']
        pr = subprocess.Popen([tools['rsync'],'--rsh', 'ssh', '-zva', '--stats', '--progress', '--update' ,'--delete', production_dir, destination],
                              stdout=fd, 
                              stderr=fd, 
                              shell=False)
        (out, error) = pr.communicate()

        fd.close()
    else:
        compose_msg("[SKIPPED] rsync scripts not executed, no conf available")

def write_json_config(data, filename):
    # The file should be created in project_dir
    # TODO: if file exists create a backup
    jsonfile = open(os.path.join(production_dir, filename), 'w')
    # jsonfile.write(json.dumps(data, indent=4, separators=(',', ': ')))
    jsonfile.write(json.dumps(data, indent=4, sort_keys=True))
    jsonfile.close()

def launch_vizjs_config():
    config = {}
    active_ds = []
    # All data source with database configured are active
    dbs_to_ds = {
           'db_cvsanaly': 'scm',
           'db_bicho': 'its',
           'db_gerrit':'gerrit',
           'db_mlstats':'mlstats',
           'db_irc':'irc',
           'db_mediawiki':'mediawiki'
    }
    for db in dbs_to_ds:
        if options['generic'].has_key(db):
            active_ds.append(dbs_to_ds[db])
    if options['generic'].has_key('markers'):
        config['markers'] = options['generic']['markers'];

    if not ('end_date' in options['r']):
        options['r']['end_date'] = time.strftime('%Y-%m-%d')

    config['data-sources'] = active_ds
    config['reports'] = options['r']['reports'].split(",")
    config['period'] = options['r']['period']
    config['start_date'] = options['r']['start_date']
    config['end_date'] = options['r']['end_date']
    config['project_info'] = get_project_info()

    compose_msg("Writing config file for VizGrimoireJS: " + production_dir + "config.json")

    write_json_config(config, 'config.json')

# create the project-info.json file
def get_project_info():
    project_info = {
        "date":"",
        "project_name" : options['generic']['project'],
        "project_url" :"",
        "scm_url":"",
        "scm_name":"",
        "scm_type":"git",
        "its_url":"",
        "its_name":"Tickets",
        "its_type":"",
        "mls_url":"",
        "mls_name":"",
        "mls_type":"",
        "scr_url":"",
        "scr_name":"",
        "scr_type":"",
        "irc_url":"",
        "irc_name":"",
        "irc_type":"",
        "mediawiki_url":"",
        "mediawiki_name":"",
        "mediawiki_type":"",
        "producer":"Automator",
        "blog_url":""
    }
    # ITS URL
    if options.has_key('bicho'):
        its_url = options['bicho']['trackers'][0]
        aux = its_url.split("//",1)
        its_url = aux[0]+"//"+aux[1].split("/")[0]
        project_info['its_url'] = its_url
    # SCM URL: not possible until automator download gits
    scm_url = ""
    # MLS URL
    if options.has_key('mlstats'):
        aux = options['mlstats']['mailing_lists']
        mls_url = aux.split(",")[0]
        aux = mls_url.split("//",1)
        if (len(aux) > 1):
            mls_url = aux[0]+"//"+aux[1].split("/")[0]
        project_info['mls_url'] = mls_url
        project_info['mls_name'] = "Mailing lists"
    # SCR URL
    if options.has_key('gerrit'):
        scr_url = "http://"+options['gerrit']['trackers'][0]
        project_info['scr_url'] = scr_url
    # Mediawiki URL
    if options.has_key('mediawiki'):
        mediawiki_url = options['mediawiki']['sites']
        project_info['mediawiki_url'] = mediawiki_url

    return project_info

def print_std(string, new_line=True):
    # Send string to standard input if quiet mode is disabled
    if not opt.quiet_mode:
        if new_line:
            print(string)
        else:
            print(string),

tasks_section = {
    'check-dbs':launch_checkdbs,
    'cvsanaly':launch_cvsanaly,
    'bicho':launch_bicho,
    'gerrit':launch_gerrit,
    'mlstats':launch_mlstats,
    'irc': launch_irc,
    'mediawiki': launch_mediawiki,
    'downloads': launch_downloads,
    'identities': launch_identity_scripts,
    'r':launch_rscripts,
    'copy-json': launch_copy_json,
    'git-production':launch_commit_jsones,
    'db-dump':launch_database_dump,
    'json-dump':launch_json_dump,
    'rsync':launch_rsync,
    'vizjs':launch_vizjs_config
}
tasks_order = ['check-dbs','cvsanaly','bicho','gerrit','mlstats','irc','mediawiki', 'downloads',
               'identities','r','copy-json', 'vizjs','git-production','db-dump','json-dump','rsync']

if __name__ == '__main__':
    opt = get_options()   
    initialize_globals(opt.project_dir)

    reset_log()
    compose_msg("Starting ..") 

    read_main_conf()

    check_tools()

    if opt.section is not None:
        tasks_section[opt.section]()
    else:
        for section in tasks_order:
            t0 = dt.datetime.now()
            print_std("Executing %s ...." % (section), new_line=False)
            sys.stdout.flush()
            tasks_section[section]()
            t1 = dt.datetime.now()
            print_std(" %s minutes" % ((t1-t0).seconds/60))
    print_std("Finished.")

    compose_msg("Process finished correctly ...")

    # done, we sent the result
    project = options['generic']['project']
    mail = options['generic']['mail']
    os.system("mail -s \"[%s] data updated\" %s < %s" % (project, mail, msg_body))
