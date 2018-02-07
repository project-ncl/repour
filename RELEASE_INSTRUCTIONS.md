# Naming convention

Our naming convention is as follows:
```
<major>.<minor>.<micro>.<qualifier>
```


# Branching

All of our development occurs in the master branch. Once our features are
mature enough, we create a maintenance branch with the format
'pnc-<major>.<minor>.x'. When this is done, the repour version in the master
branch in file `repour/__init__.py` should be bumped to the next major/minor
release.


# Release Instructions
When we are ready to release Repour, the following instructions have to be
followed:

1. Update the file `repour/__init__.py` inside our git maintenance branch for
   the version. The qualifier should be set to 'FINAL' and not 'SNAPSHOT'.

2. Commit the changes and push to upstream git repository

3. Create a tag with format 'pnc-<major>.<minor>.<micro>' and push to upstream
   git repository

4. Change the file `repour/__init__.py` again to increase the micro version by
   one, and change the qualifier to 'SNAPSHOT'. Don't forget to commit and push
   those changes


# Version
When we do a release, the version changes from qualifier 'SNAPSHOT' to 'FINAL'

While developing for the next version, the version qualifier should be
'SNAPSHOT'
