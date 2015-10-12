import asyncio

class DescribedError(Exception):
    def __init__(self, desc):
        super().__init__(desc)
        self.desc = desc

class CommandError(DescribedError):
    def __init__(self, desc, cmd, exit_code, stdout=None, stderr=None):
        super().__init__(desc)
        self.cmd = cmd
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

class HttpClientError(DescribedError):
    @classmethod
    @asyncio.coroutine
    def from_response(cls, desc, response):
        if response.content and not response.content.at_eof():
            body = yield from response.text()
        else:
            body = None
        return cls(desc, response.status, body)

    def __init__(self, desc, status, body):
        super().__init__(desc)
        self.status = status
        self.body = body

class PullError(DescribedError):
    pass

class PullCommandError(PullError, CommandError):
    pass

class RepoError(DescribedError):
    pass

class RepoCommandError(RepoError, CommandError):
    pass

class RepoHttpClientError(RepoError, HttpClientError):
    pass

class AdjustError(DescribedError):
    pass

class AdjustCommandError(AdjustError, CommandError):
    pass
