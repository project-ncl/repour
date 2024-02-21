import logging

import gitlab

from repour.config import config

logger = logging.getLogger(__name__)


async def internal_scm_gitlab(spec, repo_provider):
    """
    spec looks like validation.internal_scm_gitlab

    Output is:
    => success: {"status": "SUCCESS_CREATED", "readonly_url": "..", "readwrite_url": ".."} if project created
    => success: {"status": "SUCCESS_ALREADY_EXISTS", "readonly_url": "..", "readwrite_url": ".."} if project created
    => failure: Exception thrown
    """

    configuration = await config.get_configuration()
    configuration = configuration.get("gitlab")

    readonly_url = configuration.get("read_only_template")
    readwrite_url = configuration.get("read_write_template")

    project_path = spec.get("project")
    slash_count = project_path.count("/")
    if slash_count == 1:
        (subgroup_name, project_name) = project_path.split("/")
    elif slash_count == 0:
        subgroup_name = None
        project_name = project_path

    gitlab_url = configuration.get("url")
    gitlab_token = read_token(configuration.get("token_path"))
    namespace_id = configuration.get("namespace_id")

    gl = gitlab.Gitlab(url=gitlab_url, private_token=gitlab_token)

    # get the workspace group
    workspace_group = get_group(gl, namespace_id)

    # create subgroup
    if (subgroup_name is None) or (subgroup_name == workspace_group.path):
        subgroup_id = namespace_id
    else:
        subgroup_id = get_or_create_subgroup(gl, workspace_group, subgroup_name)

    # create project repository
    try:
        gl.projects.create({"name": project_name, "namespace_id": subgroup_id})
    except Exception as ex:
        if (ex.response_code == 400) and (
            ex.args[0]["name"][0] == "has already been taken"
        ):
            result = {
                "status": "SUCCESS_ALREADY_EXISTS",
                "readonly_url": readonly_url.format(REPO_NAME=project_path),
                "readwrite_url": readwrite_url.format(REPO_NAME=project_path),
            }
        else:
            raise Exception(
                "Creation failed! Response code {ex.response_code}, response body: {ex.response_body}"
            )
    else:
        result = {
            "status": "SUCCESS_CREATED",
            "readonly_url": readonly_url.format(REPO_NAME=project_path),
            "readwrite_url": readwrite_url.format(REPO_NAME=project_path),
        }
    return result


def read_token(token_filepath):
    with open(token_filepath, "r") as token_file:
        return token_file.read().strip()


def get_group(gl, group_id):
    """
    Tries to find the group with given ID. If not found throws an exception.
    """

    try:
        return gl.groups.get(group_id)
    except Exception as ex:
        if ex.response_code == 404:
            raise Exception(f"Missing PNC Workspace group with id {group_id}.")
        else:
            raise Exception(
                f"Could not load group with ID {group_id}! Response code {ex.response_code}, "
                + f"response body: {ex.response_body}"
            )


def get_or_create_subgroup(gl, parent_group, subgroup_name):
    """
    Tries to find the subgroup under given parent group by name. If not found it creates a new one.

    Output is the found/created subgroup ID.
    """

    subgroup = None
    for s in parent_group.subgroups.list(iterator=True):
        if s.name == subgroup_name:
            subgroup = s
    if subgroup is None:
        try:
            subgroup = gl.groups.create(
                {
                    "name": subgroup_name,
                    "path": subgroup_name,
                    "parent_id": parent_group.id,
                }
            )
        except Exception as ex:
            if (ex.response_code == 400) and (
                '{:name=>["has already been taken"' in ex.args[0]
            ):
                raise Exception(
                    f"Subgroup {subgroup_name} was not found, but then it was not created because it "
                    + f"already exists! Response body: {ex.response_body}"
                )
            else:
                raise Exception(
                    f"Subgroup creation of {{'name': {subgroup_name}, 'path': {subgroup_name}, "
                    + f"'parent_id': {parent_group.id}}} failed! Response code {ex.response_code}, "
                    + f"response body: {ex.response_body}"
                )
    return subgroup.id