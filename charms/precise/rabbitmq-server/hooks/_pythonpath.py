import sys
import os
import os.path

# Make sure that charmhelpers is importable, or bail out.
local_copy = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "lib")
if os.path.exists(local_copy) and os.path.isdir(local_copy):
    sys.path.insert(0, local_copy)
try:
    import charmhelpers
    _ = charmhelpers
except ImportError:
    sys.exit("Could not find required 'charmhelpers' library.")
