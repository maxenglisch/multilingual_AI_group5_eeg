from __future__ import annotations
import argparse
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote,urlsplit


def handler_for(output_dir):
    root=Path(output_dir).resolve()
    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self,path):
            request=unquote(urlsplit(path).path)
            if request.startswith("/media/videos/"): relative=Path("videos")/request.removeprefix("/media/videos/")
            elif request.startswith("/reports/"):
                rest=request.removeprefix("/reports/");parts=Path(rest).parts
                relative=Path("reports")/rest if not(parts and parts[0].upper().startswith("SUBJECT")) else Path(rest)
            else: relative=Path(request.lstrip("/"))
            candidate=(root/relative).resolve()
            try:candidate.relative_to(root)
            except ValueError:return str(root/"__forbidden__")
            return str(candidate)
    return Handler


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output-dir",default="outputs")
    parser.add_argument("--host",default="127.0.0.1");parser.add_argument("--port",type=int,default=8000);args=parser.parse_args(argv)
    server=ThreadingHTTPServer((args.host,args.port),handler_for(args.output_dir));print(f"Reports: http://{args.host}:{args.port}/reports/index.html")
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0


if __name__=="__main__": raise SystemExit(main())
