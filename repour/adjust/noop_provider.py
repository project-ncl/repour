# flake8: noqa
import logging

logger = logging.getLogger(__name__)


def get_noop_provider(execution_name):
    async def adjust(repo_dir, extra_adjust_parameters, adjust_result):
        nonlocal execution_name
        logger.info(
            'Executing "{execution_name}" using "noop" adjust provider.'.format(
                **locals()
            )
        )
        return adjust_result

    return adjust
