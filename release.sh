#!/bin/bash

while getopts r:b: option
do
case "${option}"
in
r) RELEASE=${OPTARG};;
b) BRANCH=${OPTARG};;
esac
done

mkdir tmprelease
cd tmprelease

git clone git@github.com:project-ncl/repour.git

echo "branch: $BRANCH , releae: $RELEASE"

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

read -p "Push changes? (y/n)" -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    git --git-dir=repour/.git push
    git --git-dir=repour.wiki/.git push
fi
