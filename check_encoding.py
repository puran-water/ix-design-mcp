#!/usr/bin/env python3
import locale
import sys
print(f"Python version: {sys.version}")
print(f"Default encoding: {sys.getdefaultencoding()}")
print(f"Preferred encoding: {locale.getpreferredencoding()}")
print(f"Filesystem encoding: {sys.getfilesystemencoding()}")