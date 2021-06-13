#!/usr/bin/env python3

GELB_SRC_RAW = None
GELB_ERROR_CONTEXT = 2
# Default mode is normal compilation, which makes any GeLB exceptions fatal (
# causing the compiler to abort ASAP). However, we don't want this behavior
# when testing -- in that case, this global variable will be set to True.
GELB_PRODUCTION_MODE = True  # make GeLB exceptions fatal
