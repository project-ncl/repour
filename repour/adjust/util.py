import logging
import os
import re

from xml.dom import minidom

logger = logging.getLogger(__name__)


def get_removed_repos(work_dir, parameters):
    """
    Parses the filename of the removed repos backup file from the parameters list and if there
    is one, it reads the list of repos and returns it.
    """
    result = []

    pattern = re.compile("-DrepoRemovalBackup[ =](.+)")
    for parameter in parameters:
        m = pattern.match(parameter)
        if m is not None:
            filepath = os.path.join(work_dir, m.group(1))
            logger.debug(
                'Files and folders in the work directory:\n  %s', os.listdir(work_dir))

            if os.path.exists(filepath):
                tree = minidom.parse(filepath)
                for repo_elem in tree.getElementsByTagName("repository"):
                    repo = {"releases": True, "snapshots": True,
                            "name": "", "id": "", "url": ""}
                    for enabled_elem in repo_elem.getElementsByTagName("enabled"):
                        if enabled_elem.parentNode.localName in ["releases", "snapshots"]:
                            bool_value = enabled_elem.childNodes[0].data == "true"
                            repo[enabled_elem.parentNode.localName] = bool_value
                    for tag in ["id", "name", "url"]:
                        for elem in repo_elem.getElementsByTagName(tag):
                            if elem.childNodes:
                                repo[tag] = elem.childNodes[0].data
                    result.append(repo)
                break
            else:
                logger.info(
                    'File %s does not exist. It seems no repositories were removed', filepath)

    return result
