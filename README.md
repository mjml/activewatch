ActiveWatch
===========

ActiveWatch lets you manage a folder of related files for deployment to separate filesystems / VMs / containers / machines.
When a watched file is saved, it triggers automation such as secure-copy (```scp```),
  raw commands, and shell scripts.

These scripts automate your workflow so that the automation happens immediately as you work on your files on a local machine.
This allows you to manage versioning and deployment of files for several machines under a single folder.


Command Usage
-------------

In devops style, Activewatch has a monolithic tool called ```aw``` that provides a command-line interface
  to its saved state for a given folder, and allows you to start the user daemon (```aw monitor```) that
	dispatches automation responses.


```
$ aw [-r][-R][-v*][-d <directory>][--gittoo][--hidden] <command>

Options:
    -d <directory>   Specify the starting directory in which to look for .activewatch
    --gittoo         Recurse into .git directories (normally suppressed)
    --help           Shows this message
    --hidden         Recurse into .hidden directories (normally suppressed)
    -r               Recurse into subdirectories
    -R               Recurse below directories that don't contain .activewatch
    -v (multiple times) Be more verbose

<command> can be one of:
    list
    add      <pattern> [type] <targetspec>
    rm       <pattern> [targetspec]
    monitor
```

The ```monitor``` command will start a user daemon.
It is best run in a ```screen``` session.
Its output is usually only interesting if something goes wrong.

In order for the user daemon to use scp, ssh must be set up for passwordless login.

You can ```add``` or ```remove``` patterns and targets while the daemon is running.
It will set up watches on its own files so that added patterns
  immediately set up watches for that running daemon.


All folders beneath <directory> are scanned for manifests, and their files are added to the watch list.


Manifest Format
---------------

ActiveWatch uses a manifest file contained in each directory called '.activewatch'.

The syntax for ```.activewatch/manifest``` is simple:
  ``` <file spec>:<type>:<response spec> ```

...where ```<type>``` is ```scp|cmd|bash``` and tells the monitoring daemon how to respond
  to a file when it is closed after writing.

Consider the following tree:

```
mycluster
├── .activewatch
│   └── manifest        (1)
├── ca
│   ├── mycertauth.crt
│   └── mycertauth.rsa
├── host1
│   ├── host1.crt
│   └── host1.rsa
├── host2
│   ├── host2.crt
│   └── host2.rsa
├── host3
│   ├── .activewatch
│   │   └── manifest    (2)
│   ├── host3.p12
│   └── httpd
│       └── httpd.conf
├── respond.sh
├── test1.sh
└── test2.sh
```

When the monitoring daemon is started with the recursive option in the ```mycluster``` folder, it will scan all files
  beneath that folder for any patterns given in (1).
During its recursive scan, it will also find that ```mycluster/host3/``` also contains a manifest file containing patterns in (2).
When it gets to the ```httpd.conf``` file, patterns in (1) will match against the relative path ```host3/httpd/httpd.conf```
  whereas patterns in (2) will match against the relative path ```httpd/httpd.conf```.

Patterns are always specified relative to some directory containing their ```.activewatch/manifest``` file.


File Specification
------------------

The ```<file spec>``` patterns are *[Python regular expressions*](https://docs.python.org/library/re.html).

When the monitoring daemon runs, it checks each file pattern against all relative paths beneath the folder
  containing ```.activewatch/manifest``` and the pattern.

If a match is found, the ```<response spec>``` replacement is filled in with back-references to the matched pattern.
The response specification also has predefined text interpolation variables such as ```{basename}``` and ```{relpath}``` that you can use
  to compose more complex responses.


Response Type
-------------

The secondary part of a manifest entry is the type field.
This is one of ```scp|cmd|bash```.

The ```scp``` type results in an ```scp``` command from the absolute path of the matched file to the specified target.
This method will try to reuse a control socket under your $HOME/.ssh directory and leave it open for 15 minutes so that subsequent copies
  can reuse the tcp connection, resulting in faster operation.
In the current version, the user must set up passwordless ssh login to the target machine in order for this type to be viable.

The ```cmd``` type results in a spawned subprocess using the specified target as command and arguments.

The ```bash``` type is like the former, but instead of an arbitrary command it simply starts /bin/bash and passes the target string
  as a quoted using the ```-c``` switch to execute commands within the shell.


Response Specification
----------------------

The tertiary part of a manifest entry is used to compose the response.
This part is used in different ways by the different response types, but typically you are making up another destination path or filename
  that is similar to the original relative path.
Here, you may use traditional python regexp back-references (\1, \2...\n, etc.) to refer to captured groups in the original pattern,
  as well as a number of predefined interpolation variables.

The following interpolation variables are supported:
```
{relpath}:  The full relative path to the matched file, starting from the directory that contains .activewatch/manifest
{reldir}:   The full relative path to the directory containing the matched file
{basename}: The filename itself with no directory
{type}:     The type of the pattern i.e. scp|cmd|bash
```



