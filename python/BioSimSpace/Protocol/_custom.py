######################################################################
# BioSimSpace: Making biomolecular simulation a breeze!
#
# Copyright: 2017-2018
#
# Authors: Lester Hedges <lester.hedges@gmail.com>
#
# BioSimSpace is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# BioSimSpace is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BioSimSpace. If not, see <http://www.gnu.org/licenses/>.
#####################################################################

"""
Functionality for storing custom simulation protocols.
Author: Lester Hedges <lester.hedges@gmail.com>
"""

from ._protocol import Protocol as _Protocol

import os as _os

__all__ = ["Custom"]

class Custom(_Protocol):
    """A class for storing custom protocols."""

    def __init__(self, config):
        """Constructor.

           Keyword arguments:

           config -- The custom protocol configuration.
        """

        # Set the protocol configuration.
        self.setConfig(config)

    def getConfig(self):
        """Return the custom configuration."""
        return self._config.copy()

    def setConfig(self, config):
        """Set the custom configuration."""

        # Check that the passed configuration is a list of strings.
        if _is_list_of_strings(config):
            self._config = config

        # The user has passed a path to a file.
        elif _os.path.isfile(config):

            # Clear the existing config.
            self._config = []

            # Read the contents of the file.
            with open(config, "r") as file:
                for line in file:
                    self._config.append(line.rstrip())
        else:
            raise ValueError("'config' must be a list of strings, or a file path.")

def _is_list_of_strings(lst):
    """Check whether the passed argument is a list of strings."""
    if lst and isinstance(lst, list):
        return all(isinstance(elem, str) for elem in lst)
    else:
        return False
