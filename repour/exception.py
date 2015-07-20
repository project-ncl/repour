class DescribedError(Exception):
    def __init__(self, desc):
        super().__init__(desc)
        self.desc = desc

class CommandError(DescribedError):
    def __init__(self, desc, cmd, exit_code):
        super().__init__(desc)
        self.cmd = cmd
        self.exit_code = exit_code

class PullError(DescribedError):
    pass

class PullCommandError(PullError, CommandError):
    pass

class RepoError(DescribedError):
    pass

class RepoCommandError(RepoError, CommandError):
    pass

class AdjustError(DescribedError):
    pass

class AdjustCommandError(AdjustError, CommandError):
    pass
