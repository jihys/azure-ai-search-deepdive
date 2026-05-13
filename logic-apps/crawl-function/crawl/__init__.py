import logging
import os
import sys

import azure.functions as func

# Allow importing from function app root (for shared crawl logic).
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from function_app import crawl as crawl_handler


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("v1 wrapper: forwarding request to crawl handler")
    return crawl_handler(req)
