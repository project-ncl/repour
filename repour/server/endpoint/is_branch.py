import asyncio
import json
import logging
import voluptuous

from aiohttp import web
from . import validation
from ...scm import git_provider

logger = logging.getLogger(__name__)
git = git_provider.git_provider()

class ResultDto:
    def __init__(self, value):
        self.result = value

class IsBranchErrorDto:
    def __init__(self, message, exception):
        self.error = message
        self.detail = str(exception)

@asyncio.coroutine
def is_branch(request):
    try:
        dto = yield from request.json()        
    except ValueError:
        logger.error("Rejected {method} {path}: body is not parsable as json".format(
            method=request.method,
            path=request.path,
        ))
        return web.Response(
            status=400,
            content_type="application/json",
            text=json.dumps(
                obj=[{
                    "error_message": "expected json",
                    "error_type": "json parsability",
                    "path": [],
                }],
                ensure_ascii=False,
            ),
        )
    try:
        validation.is_branch(dto)
    except voluptuous.MultipleInvalid as x:
        logger.error("Rejected {method} {path}: body failed input validation".format(
            method=request.method,
            path=request.path,
        ))
        return web.Response(
            status=400,
            content_type="application/json",
            text=json.dumps(
                obj=[e.__dict__ for e in x.errors],
                ensure_ascii=False,
            ),
        )

    url = dto["url"]
    ref = dto["ref"]

    try:
        res = yield from git["rev_parse"](url, ref)
    except BaseException as x:
        logger.error("Invalid repository or branch " + str(x))
        return web.Response(
            status=400,
            content_type="application/json",
            text=json.dumps(
                obj=IsBranchErrorDto("Invalid repository or revision", x).__dict__,
                ensure_ascii=False,
            ),
        )
    logger.info("Accepted {method} {path}: {params}".format(
        method=request.method,
        path=request.path,
        params=dto,
    ))

    isBranch = yield from git["is_branch"](url, ref)

    response = web.Response(
        status=200,
        content_type="application/json",
        text=json.dumps(
            obj=ResultDto(isBranch).__dict__,
            ensure_ascii=False,
        )
    )
    return response
