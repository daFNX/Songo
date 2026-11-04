def enabled_features():
    from backend.gateway import _configured_features
    return _configured_features()["features"]


def application(environ, start_response):
    from backend.gateway import application as gateway_application
    return gateway_application(environ, start_response)
