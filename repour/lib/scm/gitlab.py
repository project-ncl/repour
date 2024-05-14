# GitLab utility functions

import gitlab


def client(gitlab_config):
    gitlab_url = gitlab_config.get("url")
    gitlab_token = read_token(gitlab_config.get("token_path"))
    return gitlab.Gitlab(url=gitlab_url, private_token=gitlab_token)


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
            return None
        else:
            raise Exception(
                f"Could not load group with ID {group_id}! Response code {ex.response_code}, "
                + f"response body: {ex.response_body}"
            )


def get_or_create_subgroup(gl, parent_group, subgroup_name):
    """
    Tries to find the subgroup under given parent group by name. If not found it creates a new one.

    Output is the found/created subgroup.
    """

    subgroup = None
    for s in parent_group.subgroups.list(iterator=True):
        if s.name == subgroup_name:
            subgroup = s
    if subgroup is None:
        try:
            # [NCL-8683] default_branch_protection: 0: do not set it
            subgroup = gl.groups.create(
                {
                    "name": subgroup_name,
                    "path": subgroup_name,
                    "parent_id": parent_group.id,
                    "default_branch_protection": 0,
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
    return subgroup


def get_project(gl, project_path):
    project = None
    try:
        project = gl.projects.get(project_path)
    except Exception as ex:
        if ex.response_code != 404:
            raise Exception(
                f"Retrieval of project {project_path} failed! Response code {ex.response_code}, "
                + f"response body: {ex.response_body}"
            )
    return project


def create_project(gl, parent_id, project_name):
    try:
        project = gl.projects.create({"name": project_name, "namespace_id": parent_id})
    except Exception as ex:
        if (ex.response_code == 400) and (
            ex.args[0]["name"][0] == "has already been taken"
        ):
            raise Exception(
                "Creation of project repository failed because it already exists even though it "
                + f"could not be retrieved before! Response code {ex.response_code}, response "
                + f"body: {ex.response_body}"
            )
        else:
            raise Exception(
                f"Creation failed! Response code {ex.response_code}, response body: {ex.response_body}"
            )
    return project


def check_protected_tags(gitlab_config, project=None, gl=None, project_path=None):
    if not project:
        if gl and project_path:
            project = get_project(gl, project_path)
        else:
            raise Exception(
                "Unable to check protected tags setup. Either project or project "
                + "path along with GitLab client (gl) must be passed."
            )

    if not project:
        raise Exception(
            "Unable to check protected tags setup, because the "
            + f"GitLab project {project_path} cannot be loaded"
        )

    prot_tags_pattern = gitlab_config.get("protected_tags_pattern")
    accepted_patterns = gitlab_config.get("protected_tags_accepted_patterns")
    if not accepted_patterns:
        accepted_patterns = []
    if prot_tags_pattern and (prot_tags_pattern not in accepted_patterns):
        accepted_patterns.append(prot_tags_pattern)

    found = False
    prot_tags = project.protectedtags.list()
    if accepted_patterns and prot_tags:
        for prot_tag in prot_tags:
            if prot_tag.name in accepted_patterns:
                found = True
                break
    return found
