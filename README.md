ActiveWatch
===========

This python script uses inotify to detect when files in a subtree have been modified,
   then it uses scp to copy them to a predefined remote folder.
The calling user's ssh identity and configuration needs to be set up beforehand for passwordless login.

ActiveWatch uses a manifest file contained in each directory called '.activewatch'.

The syntax is simple:
  <file pattern>: <target spec>


Usage
-----

$ aw [-r][-R][-v*][-d <directory>] <command>

Options:
    -d <directory>   Specify the starting directory in which to look for .activewatch
    -r               Recurse into subdirectories
    -R               Recurse below directories that don't contain .activewatch

<command> can be one of:
    add    <pattern> <targetspec>
    rm     <pattern>
    monitor

The monitor command will start a user daemon. It is best run in a screen session. Its output is only interesting if something goes wrong.

You can add or remove patterns and targets while the daemon is running. It will set up watches on its own files so that added patterns
  immediately set up watches for that running daemon.


All folders beneath <directory> are scanned for manifests, and their files are added to the watch list.


