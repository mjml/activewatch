import os
import os.path
import sys
import inotify
import inotify.adapters
import re
import itertools
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
        return "WatchPattern(\"{}\",\"{}\",\"{}\")".format(self.rootdir, self.re.pattern, self.target)

class WatchResponder:

    rootdir = ""
    filename = ""
    target = ""

    def __init__(self, root, fn, target):
        self.rootdir = root
        self.filename = fn
        self.target = target
    
    def __str__(self):
        fn = self.filename[len(self.rootdir):]
        return "WatchResponder(\"{}\",\"{}\",\"{}\")".format(self.rootdir,fn, self.target)


avoidhidden=True
avoidgit=True
recursive = False
recurseUnconditional = False
patterns = []
responders = {}
manifests = []
verbosity = 1
mfre = re.compile('(.*)/\.activewatch/manifest')
rulepat = re.compile("(\S+?)\:\s+(\S+)")
escape = re.compile('\.')
ino = None


def dprint(level, str, *args):
    if level <= verbosity:
        print(str.format(*args))


def escape(str):
    return escape.sub('\.', str)


def line_to_pattern_pair(elem):
    if elem == None: return None
    if len(elem)==0: return None
    m = rulepat.match(elem)
    if m==None: return None
    if m==0: return None
    return (m[1].strip(),m[2].strip())


def open_manifest(dir, mode):
    if not dir.endswith('/'):
        dir = dir + '/'
    awdir = dir + ".activewatch/"
    if not os.path.exists(awdir):
        if 'w' in mode:
            os.makedirs(dir + '.activewatch')
        else:
            return None
    if not os.path.isdir(awdir):
        print("Error: .activewatch is not a directory.")
        exit(3)
    mfn = awdir + 'manifest'
    
    if 'r' in mode and not os.path.isfile(mfn):
        print("Error: manifest under {} doesn't exist.".format(awdir))
        return None
    
    mfile = open(mfn, mode)
    return mfile


def read_manifest(dir):
    mfest = open_manifest(dir, 'r')
    if mfest:
        lines = mfest.readlines()
        mfest.close()
        return lines
    else:
        print("No manifest file found.")
        return []


def write_manifest(dir,lines):
    mfest = open_manifest(dir, "w+")
    mfest.write("\n".join(lines))
    mfest.close()


def copy_file(srcpath,tgturi):
    import subprocess
    cmd = ["/usr/bin/scp", "-o", "ControlPath=/home/joya/.ssh/controlmasters/%r@%h", "-o", "ControlMaster=auto", "-o", "ControlPersist=15m", srcpath, tgturi]
    dprint(1, "running command {}".format(" ".join(cmd)))
    subprocess.run(cmd)


def add_responder(wr):
    global responders
    #old method:
    responders[wr.filename] = wr


def remove_responder(filename):
    del responders[filename]


def purge_patterns(dir):
    global patterns
    dprint(3, "Purging patterns for " + dir)
    savedpatterns = list(filter(lambda elem: elem.rootdir == dir, patterns))
    patterns = list(filter(lambda elem: elem.rootdir != dir, patterns))
    dprint(5, "Purged patterns are: ", str(savedpatterns))


def purge_responders(dir):
    global responders
    dprint(3, "Purging watches for " + dir)
    savedwatches = { k:v for k,v in responders.items() if v.rootdir == dir }
    responders = { k:v for k,v in responders.items() if v.rootdir != dir }
    dprint(5, "Purged watches are: ", str(savedwatches))
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
    removed = purge_responders(dir)

    # remove inotify watches that were rooted here
    for wr in removed.values():
        dprint(5, "Removing file watch for {}", wr.filename)
        ino.remove_watch(wr.filename)

    # Parse the manifest
    parse_manifest(dir)

    # Now scan for files
    scan_for_files(dir)

    # Re-add inotify watches for this directory
    rooted = { k:v for k,v in responders.items() if v.rootdir == dir }
    for wr in rooted.values():
        dprint(5, "Adding file watch for {}", str(wr))
        ino.add_watch(wr.filename)
    

def scan_for_files(dir):
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
                    wr = WatchResponder(wp.rootdir, path, tgt)
                    dprint(4, "Created {}", str(wr))
                    #responders[path] = wr
                    add_responder(wr)
                    break
        
        if ent.is_dir() and \
            recursive and \
            (not ent.name.startswith('.activewatch')) and \
            (not ent.name=='.') and \
            (not ent.name=='.git' or not avoidgit) and\
            (not ent.name.startswith('.') or not avoidhidden):
            scan_for_files(dir + ent.name)


def parse_manifest(dir):
    import os.path as path

    if not dir.endswith('/'):
        dir = dir + '/'

    scan_curdir=True
    
    if not scan_curdir and not recurseUnconditional:
        return

    fn = dir + ".activewatch/manifest"

    addedpatterns=0

    try:
        mfest = open_manifest(dir, "r") 
        if mfest == None:
            scan_curdir=False
    except OSError as e:
        print("Couldn't open {}: {}".format(fn,e.strerror))
        scan_curdir=False
    
    if scan_curdir:
        dprint(5, "Parsing manifest in {}", dir)

        manifests.append(fn)

        linenum=0
        lines = mfest.readlines()
        for line in lines:
            linenum=linenum+1
            m = rulepat.match(line)
            if m==None or m.lastindex != 2:
                print("{0}:{1}: improperly formatted line".format(fn,linenum))
                continue
            (pat,tgt) = (m[1], m[2])
            if pat.startswith('/'):
                pat = pat[1:]
                r = re.compile(escape(dir) + pat)
            else:
                r = re.compile(pat)
            
            #dprint(5, "Watching {}: {} -> {}", dir, r.pattern, tgt)
            wp = WatchPattern(dir,r,tgt)
            dprint(5, "Created {}", str(wp) )
            patterns.append(wp)
            addedpatterns=addedpatterns+1
        
    if not recursive:
        return

    for ent in os.scandir(dir):
        if ent.is_dir():
            if ent.name == '.' or \
                ent.name == '..' or \
                ent.name == '.activewatch' or \
                (avoidhidden and ent.name.startswith('.')) or \
                (avoidgit and ent.name=='.git'):
                continue
            cdir = dir + ent.name
            dprint(3, "Recursing into {}", cdir)
            parse_manifest(cdir)
    


def monitor_loop(dirs):

    # Parse all manifests to create WatchPatterns
    for dir in dirs:
        parse_manifest(dir)
    
    # Scan directories for files to create WatchResponders
    for dir in dirs:
        scan_for_files(dir)

    # Create inotify watches for manifests and WatchResponders
    global ino
    ino = inotify.adapters.Inotify()

    # Prepare manifest watchers
    for m in manifests:
        dprint(2, "Added manifest watch: {}", m)
        ino.add_watch(m)

    # Prepare inotify watchers for each found file
    for w in responders.values():
        dprint(2, "Added file watch: {} -> {}", w.filename, w.target)
        ino.add_watch(w.filename)

    # Main loop
    while True:
        try:
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
                    if path not in responders:
                        continue
                    wr = responders[path]
                    tgt = wr.target
                    dprint(4, "Event IN_CLOSE_WRITE: {} -> {}", path, tgt)
                    copy_file(path,tgt)
        except KeyboardInterrupt as ki:
            print("Shutdown.")
            exit(0)
        except Exception as e:
            print("Error: {}".format(e))


def add_pattern(pattern, targetspec):
    dir = os.getcwd()
    lines = read_manifest(dir)
    newline="{}: {}".format(pattern, targetspec)
    lines.append(newline)
    write_manifest(dir,lines)
    if (verbosity >= 2):
        list_patterns()
    else:
        print(newline)


def remove_pattern(pattern, targetspec=''):
    dir = os.getcwd()
    lines = read_manifest(dir)
    records = list(filter(lambda elem: elem != None, map(line_to_pattern_pair,lines)))
    lines = [ elem[0] + ": " + elem[1] for elem in records if not (elem[0]==pattern and (targetspec=='' or targetspec==elem[1])) ]
    write_manifest(dir,lines)
    if (len(targetspec)>0):
        print("{}: {}".format(pattern,targetspec))
    else:
        print(pattern)


def str_patterns():
    lines = read_manifest(os.getcwd());
    records = list(filter(lambda elem: elem != None, map(line_to_pattern_pair,lines)))
    if len(records)==0:
        return ""
    z = list(zip(*records))
    maxlength = max( [ len(elem) for elem in z[0] ])
    maxlength=min(40,maxlength)
    
    return "\n".join([ "{pat:{width}}: {target}".format(pat=r[0], width=max(len(r[0])+1,maxlength+1), target=r[1].strip()) for r in records ])


def list_patterns():
    s = str_patterns()
    if len(s) > 0:
        print(s)


def print_usage():
    print("Usage: aw [-d <directory>] [-r] <command ...>".format(sys.argv[0]))
    print("    Options:")
    print("        -d, --dir <directory>    starting directory in which to look for .activewatch")
    print("        --gittoo                 recurse into .git directories also (off by default)")
    print("        --help                   this message")
    print("        --hidden                 recurse into .hidden directories also (off by default)")
    print("        -r                       recurse into subdirectories while scanning for files")
    print("        -R                       recurse through directories that don't contain .activewatch while searching for manifests")
    print("    <command ...> can be:")
    print("        list")
    print("        add      <pattern> <targetspec>")
    print("        rm       <pattern>")
    print("        monitor")
    print()


if __name__ == "__main__":
    
    # Grab command-line arguments
    (pairs, vargs) = getopt.getopt(sys.argv[1:],"d:rRv",["dir", "help", "gittoo", "hidden"])
    dirs=[]
    for (k,v) in pairs:
        if k=="-d" or k=="--dir":
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
        if k=='--gittoo':
            avoidgit=False
        if k=='--hidden':
            avoidhidden=False
        if k=="--help":
            print_usage()
            exit(0)
    
    if len(vargs) < 1:
        print_usage()
        exit(1)
    
    if len(dirs)==0:
        dirs.append('.')
    
    cmd = vargs[0]

    if (cmd == 'monitor'):
        monitor_loop(dirs)
    elif (cmd == 'add'):
        args = vargs[1:]
        if len(args) != 2:
            print_usage()
            exit
        add_pattern(*args)
    elif (cmd == 'rm'):
        args = vargs[1:]
        if len(args) != 1:
            print_usage()
            exit
        remove_pattern(*args)
    elif cmd=='list':
        list_patterns()
    else:
        print_usage()



    


