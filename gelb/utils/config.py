#!/usr/bin/env python3

# Although global variables are not nice, it is convenient to use a few
# inside the compiler, as follows:
#   easy access to the original source-code (for error-messages)
GELB_SRC_RAW = None

GELB_FILE_NAME = None

GELB_ERROR_CONTEXT = 2

GELB_RESERVED_KEYWORDS = None  # will be filled-in as needed

# Set True by gelbc when --diagnostics-json is passed. In this mode:
# - GeLBException subclasses suppress their print(self) + os._exit(1)
#   sequence, so the exception propagates up to gelbc's top-level
#   handler that emits a structured JSON document.
# - warning_with_hint_to_term appends (message, hint, source_line) to
#   DIAGNOSTICS_WARNINGS instead of writing to stderr.
# Both are consumed by gelbc.py after compilation finishes (or fails).
DIAGNOSTICS_MODE = False
DIAGNOSTICS_WARNINGS = []
