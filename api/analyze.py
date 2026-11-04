import os
import sys
from wsgiref.simple_server import make_server

if not __package__:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.services.tempo import AnalysisError, analyze_wav, decode_samples, estimate_bpm


def application(environ, start_response):
    from backend.gateway import application as gateway_application
    return gateway_application(environ, start_response)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Songo API escuchando en http://127.0.0.1:{port}")
    make_server("127.0.0.1", port, application).serve_forever()
