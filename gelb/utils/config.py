#!/usr/bin/env python3

# Although global variables are not nice, it is convenient to use a few
# inside the compiler, as follows:
#   easy access to the original source-code (for error-messages)
GELB_SRC_RAW = None

GELB_FILE_NAME = None

GELB_ERROR_CONTEXT = 2
# Default mode is normal compilation, which makes any GeLB exceptions fatal (
# causing the compiler to abort ASAP). However, we don't want this behavior
# when testing -- in that case, this global variable will be set to True.
GELB_PRODUCTION_MODE = True  # make GeLB exceptions fatal

GELB_RESERVED_KEYWORDS = None  # will be filled-in as needed
