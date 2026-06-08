"""jupyter-sidekick: Jupyter-native access to coding agents over the Agent Client Protocol."""

__version__ = "0.3.0"


def _jupyter_server_extension_points():
    from .extension import AcpExtension

    return [{"module": "jupyter_sidekick.extension", "app": AcpExtension}]


def _jupyter_labextension_paths():
    return [{"src": "labextension", "dest": "jupyter-sidekick"}]
