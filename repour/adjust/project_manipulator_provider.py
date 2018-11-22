
def get_project_manipulator_provider(execution_name, jar_path, default_parameters):

    # TODO rewrite
    async def get_result_data(work_dir, group_id=None, artifact_id=None):

        raw_result_data = "{}"
        result_file_path = work_dir + "/target/pom-manip-ext-result.json"

        if os.path.isfile(result_file_path):
            with open(result_file_path, "r") as file:
                raw_result_data = file.read()

        logger.info('Got PME result data "{raw_result_data}".'.format(**locals()))
        pme_result = json.loads(raw_result_data)

        if group_id is not None and artifact_id is not None:
            logger.warn("Overriding the groupId of the result to: " + group_id)
            pme_result['VersioningState']['executionRootModified']['groupId'] = group_id

            logger.warn("Overriding the artifactId of the result to: " + artifact_id)
            pme_result['VersioningState']['executionRootModified']['artifactId'] =  artifact_id

        try:
            pme_result["RemovedRepositories"] = get_removed_repos(work_dir, pme_parameters)
        except FileNotFoundError as e:
            logger.error('File for removed repositories could not be found')
            logger.error(str(e))

        return pme_result

    async def adjust(work_dir, adjust_result):
        nonlocal execution_name

        cmd = ["java", "-jar", jar_path] + default_parameters

        # TODO: read from Orch
        extra_adjust_parameters = []

        # TODO: figure out how to get the correct path
        package_json = 'package.json'

        cmd += ['-f', package_json]

        logger.info('Executing "' + execution_name + '" Command is "{cmd}".'.format(**locals()))

        res = await process_provider.get_process_provider(execution_name,
                                                     cmd,
                                                     get_result_data=get_result_data,
                                                     send_log=True) \
            (work_dir, extra_adjust_parameters, adjust_result)

    return adjust


async def get_version_from_result(data):
    # TODO
    pass
