# Copyright (c) 2016-present, Facebook, Inc.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# pyre-unsafe

import builtins  # noqa
import json
import os
import subprocess
import unittest
from unittest.mock import MagicMock, mock_open, patch

from ... import commands  # noqa
from ...analysis_directory import AnalysisDirectory, SharedAnalysisDirectory
from ...error import Error  # noqa
from ..command import __name__ as client_name
from .command_test import mock_arguments, mock_configuration


class ReportingTest(unittest.TestCase):
    @patch.object(os.path, "realpath", side_effect=lambda path: path)
    @patch.object(os.path, "isdir", side_effect=lambda path: True)
    @patch.object(os.path, "exists", side_effect=lambda path: True)
    @patch("os.getcwd", return_value="/test")
    @patch("{}.find_project_root".format(client_name), return_value="/")
    @patch("{}.find_local_root".format(client_name), return_value=None)
    def test_get_errors(
        self, find_local_root, find_project_root, get_cwd, exists, isdir, realpath
    ) -> None:
        arguments = mock_arguments()
        configuration = mock_configuration()
        result = MagicMock()

        json_errors = {
            "errors": [
                {
                    "line": 1,
                    "column": 2,
                    "path": "test/path.py",
                    "code": 3,
                    "name": "Error",
                    "description": "description",
                    "inference": "inference",
                }
            ]
        }

        handler = commands.Reporting(
            arguments, configuration, AnalysisDirectory("/test/f/g")
        )
        with patch.object(json, "loads", return_value=json_errors):
            errors = handler._get_errors(result)
            self.assertEqual(len(errors), 1)
            [error] = errors
            self.assertFalse(error.ignore_error)
            self.assertFalse(error.external_to_global_root)

        arguments.targets = ["//f/g:target"]
        configuration.targets = []
        handler = commands.Reporting(
            arguments, configuration, AnalysisDirectory("/test/f/g")
        )
        with patch.object(json, "loads", return_value=json_errors):
            errors = handler._get_errors(result)
            self.assertEqual(len(errors), 1)
            [error] = errors
            self.assertFalse(error.ignore_error)
            self.assertFalse(error.external_to_global_root)

        get_cwd.return_value = "/f/g/target"
        arguments.targets = ["//f/g:target"]
        configuration.targets = []
        handler = commands.Reporting(
            arguments, configuration, AnalysisDirectory("/test/h/i")
        )
        with patch.object(json, "loads", return_value=json_errors):
            errors = handler._get_errors(result)
            self.assertEqual(len(errors), 1)
            [error] = errors
            self.assertFalse(error.ignore_error)
            self.assertFalse(error.external_to_global_root)

        # Called from root with local configuration command line argument
        get_cwd.return_value = "/"  # called from
        find_project_root.return_value = "/"  # project root
        find_local_root.return_value = "/test"  # local configuration
        handler = commands.Reporting(
            arguments, configuration, AnalysisDirectory("/shared")
        )
        with patch.object(json, "loads", return_value=json_errors):
            errors = handler._get_errors(result)
            self.assertEqual(len(errors), 1)
            [error] = errors
            self.assertFalse(error.ignore_error)
            self.assertFalse(error.external_to_global_root)

        return

        # Test wildcard in do not check
        get_cwd.return_value = "/"  # called from
        find_project_root.return_value = "/"  # project root
        find_local_root.return_value = None
        configuration.ignore_all_errors = ["*/b"]
        handler = commands.Reporting(arguments, configuration, AnalysisDirectory("/a"))
        json_errors["errors"][0]["path"] = "b/c.py"
        with patch.object(json, "loads", return_value=json_errors):
            errors = handler._get_errors(result)
            self.assertEqual(len(errors), 1)
            [error] = errors
            self.assertTrue(error.ignore_error)
            self.assertFalse(error.external_to_global_root)

    @patch.object(subprocess, "run")
    @patch("os.getcwd", return_value="/")
    @patch("{}.find_project_root".format(client_name), return_value="/")
    @patch("{}.find_local_root".format(client_name), return_value=None)
    def test_get_directories_to_analyze(
        self, find_local_root, find_project_root, getcwd, run
    ) -> None:
        arguments = mock_arguments()
        find_project_root.return_value = "base"
        arguments.source_directories = ["base"]
        configuration = mock_configuration()
        handler = commands.Reporting(
            arguments, configuration, AnalysisDirectory("base")
        )
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="\n".join(
                [
                    "external/a/.pyre_configuration.local",
                    "external/b/c/.pyre_configuration.local",
                ]
            ).encode("utf-8"),
        )
        with patch("builtins.open", mock_open(read_data='{"push_blocking": false}')):
            self.assertEqual(handler._get_directories_to_analyze(), {"base"})

        with patch("builtins.open", mock_open(read_data='{"push_blocking": true}')):
            self.assertEqual(handler._get_directories_to_analyze(), {"base"})

        with patch("builtins.open", mock_open(read_data='{"continuous": true}')):
            self.assertEqual(handler._get_directories_to_analyze(), {"base"})

        configuration.local_configuration = "a/b/.pyre_configuration.local"
        handler = commands.Reporting(
            arguments, configuration, AnalysisDirectory("base")
        )
        self.assertEqual(handler._get_directories_to_analyze(), {"base"})

        configuration.local_configuration = "a/b/.pyre_configuration.local"
        arguments.source_directories = None
        handler = commands.Reporting(
            arguments, configuration, AnalysisDirectory("base", filter_paths=["a/b"])
        )
        self.assertEqual(handler._get_directories_to_analyze(), {"a/b"})

        # With no local configuration, no filter paths, and a shared analysis
        # directory, fall back on the pyre root (current directory).
        configuration.local_configuration = None
        handler = commands.Reporting(
            arguments,
            configuration,
            SharedAnalysisDirectory([], ["//target/name"], filter_paths=[]),
        )
        with patch.object(os, "getcwd", return_value="source_directory"):
            self.assertEqual(
                handler._get_directories_to_analyze(), {"source_directory"}
            )