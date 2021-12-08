#!/usr/bin/python3
import os
import sys
import inotify
import inotify.adapters
import re
import getopt

class WatchPattern:

    rootdir = ""
    re = ""
    target = ""

    def __init__(self, root, re, tgt):
        self.rootdir = root
        self.re = re
        self.target = tgt

    def __str__(self):
        return "WatchPattern(\"{}\",\"{}\")".format(self.rootdir, self.re.pattern)

class WatchResponder:

    rootdir = ""
    filename = ""
    target = ""

    def __init__(self, root, fn, target):
        self.rootdir = root
        self.filename = fn
        self.target = target
    
    def __str__(self):
        return "WatchResponder(\"{}\",\"{}\")".format(self.filename, self.target)

recursive = False
recurseUnconditional = False
patterns = []
watches = {}
manifests = []
verbosity = 1
mfre = re.compile('(.*)/\.activewatch/manifest')
escape = re.compile('\.')
ino = None


def dprint(level, str, *args):
    if level <= verbosity:
        print(str.format(*args))

def escape(str):
    return escape.sub('\.', str)

def print_usage():
    print("Usage: {} [-d <directory>] [-r] <command>".format(sys.argv[0]))
    print("  Options:")
    print("    -d <directory>   Specify the starting directory in which to look for .activewatch")    
    print("    -r               Recurse into subdirectories")
    print("    -R               Recurse below directories that don't contain .activewatch")
    print("  <command> can be one of:")
    print("    add    <pattern> <targetspec>")
    print("    rm     <pattern>")
    print("    monitor")

def copy_file(srcpath,tgturi):
    import subprocess
    cmd = ["/usr/bin/scp", "-o", "ControlPath=/home/joya/.ssh/controlmasters/%r@%h", "-o", "ControlMaster=auto", "-o", "ControlPersist=15m", srcpath, tgturi]
    dprint(2, "running command {}".format(" ".join(cmd)))
    subprocess.run(cmd)


def purge_patterns(dir):
    global patterns
    dprint(3, "Purging patterns for " + dir)
    patterns = list(filter(lambda elem: elem.rootdir != dir, patterns))

def purge_watches(dir):
    global watches
    dprint(3, "Purging watches for " + dir)
    savedwatches = { k:v for k,v in watches.items() if v.rootdir == dir }
    watches = { k:v for k,v in watches.items() if v.rootdir != dir }
    return savedwatches


def update_manifest(mfile,dir):
    global patterns
    global ino
    
    if not dir.endswith("/"):
        dir = dir + '/'

    # scan through the patterns and look for ones that start at the given directory
    dprint(3, "Updating watched files under {}", dir)
    
    # filter out any patterns that may exist
    purge_patterns(dir)

    # remove watches that were rooted at this manifest
    removed = purge_watches(dir)

    # remove inotify watches that were rooted here
    for wr in removed.values():
        dprint(5, "Removing file watch for {}", wr.filename)
        ino.remove_watch(wr.filename)

    # Scan the manifest and let it add files, recursively if necessary
    parse_manifest(dir, recursive)

    # Re-add inotify watches for this directory
    rooted = { k:v for k,v in watches.items() if v.rootdir == dir }
    for wr in rooted.values():
        dprint(5, "Adding file watch for {}", wr.filename)
        ino.add_watch(wr.filename)

                

def scan_for_files(dir, recurse_files):
    if not dir.endswith('/'):
        dir = dir + '/'
    dprint(5, "Scanning for files in {}", dir)
    for ent in os.scandir(dir):            
        if ent.is_file():
            for wp in patterns:
                r = wp.re
                pattern = r.pattern
                path = dir + ent.name

                if path.startswith(wp.rootdir):
                    relpath = path[len(wp.rootdir):]
                else:
                    relpath = ent.name
                
                if pattern.startswith('/'):
                    relativepattern = True
                    match = r.fullmatch(relpath)
                else:
                    relativepattern = False
                    match = r.match(relpath)
                
                if match:
                    path=dir + ent.name
                    dprint(3, "File {} matches {}", path, pattern)

                    tgt = r.sub(wp.target, relpath)

                    watch = WatchResponder(dir, path, tgt)
                    watches[path] = watch
                    break
        
        if ent.is_dir() and recurse_files and not ent.name.startswith('.activewatch') and not ent.name=='.':
            scan_for_files(dir + ent.name, recurse_files)



def parse_manifest(dir,recurse_files=False):
    import os.path as path

    if not dir.endswith('/'):
        dir = dir + '/'

    scan_curdir=True
    
    if not path.exists(dir + ".activewatch"):
        scan_curdir=False

    fn = dir + ".activewatch/manifest"
    if not path.exists(fn):
        scan_curdir=False

    if not scan_curdir and not recurseUnconditional:
        return

    addedpatterns=0
    
    if scan_curdir:
        dprint(5, "Parsing manifest in {}", dir)
        manifests.append(fn)

        try:
            mfest = open(fn, "r") 
        except OSError as e:
            print("Couldn't open {}: {}".format(fn,e.strerror))
            scan_curdir=False

        linenum=0
        lines = mfest.readlines()
        lpat = re.compile("(\S+?)\:\s+(\S+)")
        for line in lines:
            linenum=linenum+1
            m = lpat.match(line)
            if m.lastindex != 2:
                print("{0}:{1}: improperly formatted line\n".format(fn,linenum))
                continue
            (pat,tgt) = (m[1], m[2])
            if pat.startswith('/'):
                pat = pat[1:]
                r = re.compile(escape(dir) + pat)
            else:
                r = re.compile(pat)
            
            dprint(5, "Watching {}: {} -> {}", dir, r.pattern, tgt)
            wp = WatchPattern(dir,r,tgt)
            patterns.append(wp)
            addedpatterns=addedpatterns+1
        
        scan_for_files(dir,recurse_files)

    if not recursive:
        return

    for ent in os.scandir(dir):
        if ent.is_dir():
            if ent.name == '.' or ent.name == '..' or ent.name == '.activewatch':
                continue
            cdir = dir + ent.name
            dprint(3, "Recursing into {}", cdir)
            parse_manifest(cdir)
    
    # pop off the patterns added before returning
    if addedpatterns > 0:
        del patterns[-addedpatterns:]


def monitor_loop(dirs):
    # Scan directories for manifests that will give details for each file
    for dir in dirs:
        parse_manifest(dir)

    global ino
    ino = inotify.adapters.Inotify()

    # Prepare manifest watchers
    for m in manifests:
        dprint(2, "Added manifest watch: {}", m)
        ino.add_watch(m)

    # Prepare inotify watchers for each found file
    for w in watches.values():
        dprint(2, "Added file watch: {}", w)
        ino.add_watch(w.filename)

    # Main loop
    try:
        while True:
            event = ino.event_gen(yield_nones=True)
            for e in event:
                if e == None:
                    break
                try:
                    (_, etypes, path, filename) = e
                except ValueError as ve:
                    dprint(4, "Event received: [{}]", ve)
                    break
                
                if 'IN_CLOSE_WRITE' in etypes:
                    m = mfre.fullmatch(path)
                    if m and os.path.exists(m[1]) and os.path.isdir(m[1]):
                        update_manifest(path, m[1])
                    if path not in watches:
                        continue
                    wr = watches[path]
                    tgt = wr.target
                    dprint(4, "Event IN_CLOSE_WRITE: {} -> {}", path, tgt)
                    copy_file(path,tgt)

    except KeyboardInterrupt as ki:
        print("Shutdown.")
        exit(0)



if __name__ == "__main__":
    
    # Grab command-line arguments
    (pairs, vargs) = getopt.getopt(sys.argv[1:],"d:rRv")
    dirs=[]
    for (k,v) in pairs:
        if k=="-d":
            dirname = os.path.abspath(v)
            if not os.path.exists(dirname):
                print("Path does not exist: " + v)
                exit(2)
            dirs.append(dirname)
        if k=="-r":
            recursive=True
        if k=='-R':
            recursive=True
            recurseUnconditional=True
        if k=='-v':
            verbosity = verbosity + 1
    
    if len(vargs) < 1:
        print_usage()
        exit(1)
    
    if len(dirs)==0:
        dirs.append('.')
    
    cmd = vargs[0]

    if (cmd == 'monitor'):
        monitor_loop(dirs)
    if (cmd == 'add'):
        pass
    if (cmd == 'rm'):
        pass



    


