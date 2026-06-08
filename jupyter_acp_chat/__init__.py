"""jupyter-acp-chat: Jupyter-native access to coding agents over the Agent Client Protocol."""

__version__ = "0.0.1"


def _jupyter_server_extension_points():
    from .extension import AcpExtension

    return [{"module": "jupyter_acp_chat.extension", "app": AcpExtension}]


def _jupyter_labextension_paths():
    return [{"src": "labextension", "dest": "jupyter-acp-chat"}]
