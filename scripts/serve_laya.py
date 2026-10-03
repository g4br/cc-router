'''
Serves the fine-tuned Laya checkpoint over the same HTTP contract as laya-serve (POST /v1/systemone).

laya-serve only knows the three public checkpoints (english, multilingual, typed-decisions):
an unknown value in the request's 'model' field is ignored and the request falls back to
language routing, with no error. This script puts the fine-tuned checkpoint in place of one
of those names (laya_checkpoint in ladder.json), and route.py asks for that name in every request.

Requires: pip install "laya[serve]"
Usage:    python serve_laya.py <local folder or Hugging Face repo of the checkpoint>
'''
import os
import sys
from urllib.parse import urlparse

import uvicorn
from laya import Router
from laya.serve import create_app

from common import load_config

#-----------------------------------------------------------
# Input and paths
#-----------------------------------------------------------
if len(sys.argv) != 2: raise ValueError('usage: python serve_laya.py <folder or repo of the fine-tuned checkpoint>')

checkpoint = sys.argv[1]
config     = load_config()
name       = config['laya_checkpoint']
address    = urlparse(config['laya_url'])
#-----------------------------------------------------------
# Load and serve
#-----------------------------------------------------------
print(f'Loading {checkpoint} in place of {name}')

# LAYA_API_KEY, when set, is read by create_app and then requires Authorization: Bearer
router = Router(models={name: checkpoint}, device=os.environ.get('LAYA_DEVICE'), default=name)
router.preload([name])

uvicorn.run(create_app(router), host=address.hostname, port=address.port)
