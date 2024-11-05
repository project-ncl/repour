import logging

import gitlab

from repour.config import config
from repour.lib.scm import gitlab as scm_gitlab

logger = logging.getLogger(__name__)


def sanitize_gitlab_name(name):
    """
    gitlab doesn't like the start or end of a project or subgroup to be something other than
    alpha numeric. If this happens, let's just replace the non-alpha-numeric character with an underscore
    """

    list_name = list(name)
    if not list_name[0].isalnum():
        list_name[0] = "_"
    if not list_name[-1].isalnum():
        list_name[-1] = "_"

    return "".join(list_name)


def sanitize_gitlab_project_path(project_path):
    (subgroup_name, project_name) = project_path.split("/", 1)

    sanitized_subgroup_name = sanitize_gitlab_name(subgroup_name)
    sanitized_project_name = sanitize_gitlab_name(project_name)

    return sanitized_subgroup_name + "/" + sanitized_project_name


async def internal_scm_gitlab(spec, repo_provider):
    """
    spec looks like validation.internal_scm_gitlab

    Output is:
    => success: {"status": "SUCCESS_CREATED", "readonly_url": "..", "readwrite_url": ".."} if project created
    => success: {"status": "SUCCESS_ALREADY_EXISTS", "readonly_url": "..", "readwrite_url": ".."} if project created
    => failure: Exception thrown
    """

    configuration = await config.get_configuration()
    gitlab_config = configuration.get("gitlab")

    readonly_url = gitlab_config.get("read_only_template")
    readwrite_url = gitlab_config.get("read_write_template")

    project_path = sanitize_gitlab_project_path(spec.get("project"))
    if "/" in project_path:
        (subgroup_name, project_name) = project_path.split("/", 1)
        if "/" in project_name:
            raise Exception(
                f"More than one slash in project path is not supported: {project_path}"
            )
    else:
        subgroup_name = None
        project_name = project_path

    namespace_id = gitlab_config.get("namespace_id")

    gl = scm_gitlab.client(gitlab_config)

    # get the workspace group
    workspace_group = scm_gitlab.get_group(gl, namespace_id)
    if workspace_group is None:
        raise Exception(f"Missing PNC Workspace group with id {namespace_id}.")

    # create subgroup
    if (subgroup_name is None) or (subgroup_name == workspace_group.path):
        parent_id = namespace_id
        complete_path = workspace_group.path + "/" + project_name
    else:
        subgroup = scm_gitlab.get_or_create_subgroup(gl, workspace_group, subgroup_name)
        parent_id = subgroup.id
        complete_path = workspace_group.path + "/" + project_path

    # get or create project repository
    (result, project) = get_or_create_project(
        gl, parent_id, complete_path, project_path, readonly_url, readwrite_url
    )

    # set the protected tags to configured pattern
    prot_tags_pattern = gitlab_config.get("protected_tags_pattern")
    # perform the check/configuration only if the protected tags pattern is configured
    if prot_tags_pattern:
        found = False
        if result.get("status") == "SUCCESS_ALREADY_EXISTS":
            # check if the protected tags are configured already (only if the repo already existed)
            found = scm_gitlab.check_protected_tags(gitlab_config, project=project)
        if not found:
            project.protectedtags.create(
                {
                    "name": prot_tags_pattern,
                    "create_access_level": gitlab.const.AccessLevel.DEVELOPER,
                }
            )

    return result


def get_or_create_project(
    gl, parent_id, complete_path, project_path, readonly_url, readwrite_url
):
    project = scm_gitlab.get_project(gl, complete_path)
    if project:
        result = {
            "status": "SUCCESS_ALREADY_EXISTS",
            "readonly_url": readonly_url.format(REPO_NAME=project_path),
            "readwrite_url": readwrite_url.format(REPO_NAME=project_path),
        }
    else:
        project_name = complete_path.split("/")[complete_path.count("/")]
        project = scm_gitlab.create_project(gl, parent_id, project_name)
        result = {
            "status": "SUCCESS_CREATED",
            "readonly_url": readonly_url.format(REPO_NAME=project_path),
            "readwrite_url": readwrite_url.format(REPO_NAME=project_path),
        }

    return (result, project)
