import asyncio
import json


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
    async def from_response(cls, desc, response, body=None):
        if response.content and not response.content.at_eof():
            b = await response.text()
        else:
            if body is None:
                b = None
            elif isinstance(body, str):
                b = body
            else:
                try:
                    b = json.dumps(body)
                except Exception:
                    b = None
        return cls(desc, response.status, b)

    def __init__(self, desc, status, body):
        super().__init__(desc)
        self.status = status
        self.body = body


class PullError(DescribedError):
    pass


class CloneError(DescribedError):
    pass


class PullCommandError(PullError, CommandError):
    pass


class CloneCommandError(CloneError, CommandError):
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
