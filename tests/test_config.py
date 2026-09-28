import os
import runpy
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cheatsheet.config import ROOT


EXPECTED_PREFIXES = (
    "atuin,awk,gawk,bash,curl,egrep,grep,jq,jqlang,mongo,mongodb,mongosh,mysql,"
    "neovim,nvim,vim,pg,postgres,postgresql,psql,sed,gunzip,gzip,tar,unzip,zip,xargs"
)


class ConfigDefaultsTest(unittest.TestCase):
    def test_missing_env_uses_search_defaults(self):
        with TemporaryDirectory() as directory:
            module_dir = Path(directory) / "cheatsheet"
            module_dir.mkdir()
            module = module_dir / "config.py"
            shutil.copyfile(ROOT / "cheatsheet" / "config.py", module)
            with patch.dict(os.environ, {}, clear=True):
                values = runpy.run_path(str(module))

        self.assertEqual(values["SEARCH_COLON_FREE_PREFIXES"], frozenset(EXPECTED_PREFIXES.split(",")))
        self.assertEqual(values["SEARCH_MIN_SIMILARITY"], 0.40)
        self.assertEqual(values["SEARCH_MAX_AVERAGE_MS"], 200)
