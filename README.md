ActiveWatch
===========

This python script uses Linux inotify to take action on files that have been saved/modified.

This lets you manage a tree of related DevOps files destined for separate VMs/containers/machines
  under a single git repository folder.

ActiveWatch uses a manifest file contained in each directory called '.activewatch'.

The syntax is simple:
  <file pattern>: <target spec>


Usage
-----

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
    add      <pattern> <targetspec>
    rm       <pattern>
    monitor
```

The monitor command will start a user daemon. It is best run in a screen session. Its output is only interesting if something goes wrong.

In order for the user daemon to use scp, ssh must be set up for passwordless login.

You can add or remove patterns and targets while the daemon is running. It will set up watches on its own files so that added patterns
  immediately set up watches for that running daemon.


All folders beneath <directory> are scanned for manifests, and their files are added to the watch list.


