"""Allow ``python -m ai_response_eval`` as an alternative to the ``ai-eval`` script."""

import sys

from ai_response_eval.cli import main

sys.exit(main())
