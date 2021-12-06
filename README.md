ActiveWatch
===========

This python script uses inotify to detect when files in a subtree have been modified,
   then it uses scp to copy them to a predefined remote folder.
The calling user's ssh identity and configuration needs to be set up beforehand for passwordless login.

ActiveWatch uses a manifest file contained in each directory called '.activewatch'.

The syntax is simple:
  <filename>: <remote spec>


Usage
-----

  activewatch <directory>

All folders beneath <directory> are scanned for manifests, and their files are added to the watch list.

