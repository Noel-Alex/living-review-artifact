"""Record actual local analysis/runtime dependencies without installing anything."""
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from wpa_core import ROOT,sha
import numpy as np
from run_wpb import OUT,write,verify_freeze


def main():
    verify_freeze()
    numpy_binary=Path(np._core._multiarray_umath.__file__) if hasattr(np,'_core') else Path(np.core._multiarray_umath.__file__)
    latex=shutil.which('pdflatex')
    write('environment.json',dict(python=sys.version,executable=sys.executable,executable_sha256=sha(sys.executable),
          platform=platform.platform(),numpy_version=np.__version__,numpy_module=str(np.__file__),
          numpy_binary=str(numpy_binary),numpy_binary_sha256=sha(numpy_binary),
          git_version=subprocess.check_output(['git','--version'],text=True).strip(),
          tracker_sha256=sha(ROOT/'tools/bin/lhdiff-driver.exe'),
          latex_executable=latex,latex_sha256=sha(latex) if latex else None,
          script_sha256=sha(Path(__file__)),network_used=False,new_packages_installed=False))
    print('Environment recorded',np.__version__,latex,flush=True)


if __name__=='__main__':main()
