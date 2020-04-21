#!/bin/bash

# USAGE: ./release.sh -r $release_number (release version) -b $branch (release branch) -p (push)

PUSH=false
while getopts "r:b:p" option
do
case "${option}"
in
r) RELEASE=${OPTARG};;
b) BRANCH=${OPTARG};;
p) PUSH=true;;
esac
done

echo "branch: $BRANCH , release: $RELEASE, push: $PUSH"

mkdir tmprelease
cd tmprelease

git clone git@github.com:project-ncl/repour.git

cd repour

git checkout $BRANCH

sed -i 's/SNAPSHOT/FINAL/g' repour/__init__.py

git add . && git commit -m "Release $RELEASE" && git tag "pnc-$RELEASE"

sed -i 's/FINAL/SNAPSHOT/g' repour/__init__.py

v=$(grep -Eo "([0-9]{1,}\.)+[0-9]{1,}" repour/__init__.py)
updatev=$(echo "${v%.*}.$((${v##*.}+1))")

sed -i "s/$v/$updatev/g" repour/__init__.py

git add . && git commit -m 'Continue with developement'

##changelog update

cd ..

git clone git@github.com:project-ncl/repour.wiki.git

#get changes for changelog

tags=($(grep '^## ' repour.wiki/Changelog.md | grep -v 'UNRELEASED' | grep -m 2 -Eo '\[.*]' | sed 's/[][]//g'))

gitchanges=$(git --git-dir=repour/.git log --pretty=format:"%s"  pnc-${tags[1]}..pnc-${tags[0]} | sed 's/^/- /')

changes="\n## [$RELEASE] - $(date +"%Y-%m-%d") \n### Changed\n$gitchanges\n"

echo "$changes"

lastreleaseline=($(grep -n '^## ' repour.wiki/Changelog.md | grep -v 'UNRELEASED' | grep -m 1 -Eo '^[^:]+') - 1)

oldstart=$(head -n $((lastreleaseline - 1)) repour.wiki/Changelog.md)

oldend=$(tail -n +$lastreleaseline repour.wiki/Changelog.md)

printf "$oldstart\n$changes\n$oldend" > repour.wiki/Changelog.md

git --git-dir=repour.wiki/.git add repour.wiki/Changelog.md && git --git-dir=repour.wiki/.git commit -m "[auto] Updated Changelog (markdown)"

if [ $PUSH = true ]
then
    git --git-dir=repour/.git push
    git --git-dir=repour.wiki/.git push
fi
