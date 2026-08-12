class ChatmeshError(Exception):
    pass


class EnvelopeError(ChatmeshError):
    pass


# The project was called agentmesh before 1.0. Kept so existing
# `except AgentmeshError` keeps working.
AgentmeshError = ChatmeshError
