######################################################################
# BioSimSpace: Making biomolecular simulation a breeze!
#
# Copyright: 2017-2023
#
# Authors: Lester Hedges <lester.hedges@gmail.com>
#
# BioSimSpace is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
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

"""Functionality for running simulations using AMBER."""

__author__ = "Lester Hedges"
__email__ = "lester.hedges@gmail.com"

__all__ = ["Amber"]

from .._Utils import _try_import

_pygtail = _try_import("pygtail")

import os as _os
import re as _re
import time as _time
import shutil as _shutil
import timeit as _timeit
import warnings as _warnings

from sire.legacy import Base as _SireBase
from sire.legacy import IO as _SireIO
from sire.legacy import Mol as _SireMol

from .. import _amber_home, _isVerbose
from ..Align._squash import _squash, _unsquash
from .._Exceptions import IncompatibleError as _IncompatibleError
from .._Exceptions import MissingSoftwareError as _MissingSoftwareError
from .._SireWrappers import System as _System
from ..Types._type import Type as _Type

from .. import IO as _IO
from .. import Protocol as _Protocol
from .. import Trajectory as _Trajectory
from .. import Units as _Units
from .. import _Utils

from . import _process

from ._plumed import Plumed as _Plumed


class Amber(_process.Process):
    """A class for running simulations using AMBER."""

    def __init__(
        self,
        system,
        protocol,
        exe=None,
        name="amber",
        work_dir=None,
        seed=None,
        extra_options=None,
        extra_lines=None,
        reference_system=None,
        property_map={},
    ):
        """
        Constructor.

        Parameters
        ----------

        system : :class:`System <BioSimSpace._SireWrappers.System>`
            The molecular system.

        protocol : :class:`Protocol <BioSimSpace.Protocol>`
            The protocol for the AMBER process.

        exe : str
            The full path to the AMBER executable.

        name : str
            The name of the process.

        work_dir :
            The working directory for the process.

        seed : int
            A random number seed.

        extra_options : dict
            A dictionary containing extra options. Overrides the ones generated from the protocol.

        extra_lines : list
            A list of extra lines to be put at the end of the script.

        reference_system : :class:`System <BioSimSpace._SireWrappers.System>` or None
               An optional system to use as a source of reference coordinates, if applicable.
               It is assumed that this system has the same topology as "system". If this is
               None, then "system" is used as a reference.

           property_map : dict
               A dictionary that maps system "properties" to their user defined
               values. This allows the user to refer to properties with their
               own naming scheme, e.g. { "charge" : "my-charge" }
        """

        # Call the base class constructor.
        super().__init__(
            system,
            protocol,
            name,
            work_dir,
            seed,
            extra_options,
            extra_lines,
            property_map,
        )

        # Set the package name.
        self._package_name = "AMBER"

        # This process can generate trajectory data.
        self._has_trajectory = True

        # If the path to the executable wasn't specified, then search
        # for it in $PATH. For now, we'll just search for 'sander', which
        # is available free as part of AmberTools. In future, we will
        # look for all possible executables in order of preference: pmemd.cuda,
        # pmemd, sander, etc., as well as their variants, e.g. pmemd.MPI.
        if exe is None:
            # Search AMBERHOME, if set.
            if _amber_home is not None:
                exe = "%s/bin/sander" % _amber_home
                if _os.path.isfile(exe):
                    self._exe = exe
                else:
                    raise _MissingSoftwareError(
                        "'BioSimSpace.Process.Amber' is not supported. "
                        "Please install AMBER (http://ambermd.org)."
                    )
        else:
            # Make sure executable exists.
            if _os.path.isfile(exe):
                self._exe = exe
            else:
                raise IOError("AMBER executable doesn't exist: '%s'" % exe)

        # Initialise dictionaries to hold stdout records for all possible
        # degrees of freedom. For regular simulations there will be one,
        # for free-energy simulations there will be three, i.e. one for
        # each of the TI regions and one for the soft-core part of the system.
        self._stdout_dict = [
            _process._MultiDict(),
            _process._MultiDict(),
            _process._MultiDict(),
        ]

        # Initialise mappings between "universal" stdout keys, and the actual
        # record key used for the different degrees of freedom in the AMBER
        # output.
        self._stdout_key = [{}, {}, {}]

        # Initialise log file parsing flags.
        self._has_results = False
        self._finished_results = False
        self._is_header = False

        # The names of the input files.
        self._rst_file = "%s/%s.rst7" % (self._work_dir, name)
        self._top_file = "%s/%s.prm7" % (self._work_dir, name)

        # The name of the trajectory file.
        self._traj_file = "%s/%s.nc" % (self._work_dir, name)

        # Set the path for the AMBER configuration file.
        self._config_file = "%s/%s.cfg" % (self._work_dir, name)

        # Set the reference system
        self._ref_file = f"{self._work_dir}/{name}_ref.rst7"
        self._ref_system = reference_system

        # Create the list of input files.
        self._input_files = [self._config_file, self._rst_file, self._top_file]

        # Now set up the working directory for the process.
        self._setup()

    def _setup(self):
        """Setup the input files and working directory ready for simulation."""

        # Create the input files...
        self._squashed_system, self._mapping = self._write_system(
            self._system, coord_file=self._rst_file, topol_file=self._top_file
        )

        # Create the reference file
        if self._ref_system is not None and self._protocol.getRestraint() is not None:
            self._write_system(self._ref_system, ref_file=self._ref_file)
        else:
            _shutil.copy(self._rst_file, self._ref_file)

        # Generate the AMBER configuration file.
        # Skip if the user has passed a custom config.
        if isinstance(self._protocol, _Protocol.Custom):
            self.setConfig(self._protocol.getConfig())
        else:
            self._generate_config()
        self.writeConfig(self._config_file)

        # Generate the dictionary of command-line arguments.
        self._generate_args()

        # Return the list of input files.
        return self._input_files

    def _write_system(self, system, coord_file=None, topol_file=None, ref_file=None):
        """Validates an input system and makes some internal modifications to it,
        if needed, before writing it out to a coordinate and/or a topology file.

        Parameters
        ----------

        system : :class:`System <BioSimSpace._SireWrappers.System>`
            The molecular system.

        coord_file : str or None
            The coordinate file to which to write out the system.

        topol_file : str or None
            The topology file to which to write out the system.

        ref_file : str or None
            The coordinate file for the reference system used for position restraints.

        Returns
        -------

        system : BioSimSpace._SireWrappers.System
             The system used for writing out the topologies.

        mapping : dict(Sire.Mol.MolIdx, Sire.Mol.MolIdx)
             The corresponding molecule-to-molecule mapping.
        """
        # Create a copy of the system.
        system = system.copy()

        # Convert the water model topology so that it matches the AMBER naming convention.
        system._set_water_topology("AMBER", self._property_map)

        # Check for perturbable molecules and convert to the chosen end state.
        if isinstance(self._protocol, _Protocol._FreeEnergyMixin):
            # Represent the perturbed system in an AMBER-friendly format.
            system, mapping = _squash(system)
        else:
            system = self._checkPerturbable(system)
            mapping = {
                _SireMol.MolIdx(x): _SireMol.MolIdx(x)
                for x in range(0, system.nMolecules())
            }

        # RST file (coordinates).
        if coord_file is not None:
            try:
                file = _os.path.splitext(coord_file)[0]
                _IO.saveMolecules(file, system, "rst7", property_map=self._property_map)
            except Exception as e:
                msg = "Failed to write system to 'RST7' format."
                if _isVerbose():
                    raise IOError(msg) from e
                else:
                    raise IOError(msg) from None

        # RST file (reference for position restraints).
        if ref_file is not None:
            try:
                file = _os.path.splitext(ref_file)[0]
                _IO.saveMolecules(file, system, "rst7", property_map=self._property_map)
            except Exception as e:
                msg = "Failed to write system to 'RST7' format."
                if _isVerbose():
                    raise IOError(msg) from e
                else:
                    raise IOError(msg) from None

        # PRM file (topology).
        if topol_file is not None:
            try:
                file = _os.path.splitext(topol_file)[0]
                _IO.saveMolecules(file, system, "prm7", property_map=self._property_map)
            except Exception as e:
                msg = "Failed to write system to 'PRM7' format."
                if _isVerbose():
                    raise IOError(msg) from e
                else:
                    raise IOError(msg) from None

        return system, mapping

    def _generate_config(self):
        """Generate AMBER configuration file strings."""

        # Clear the existing configuration list.
        self._config = []

        config_options = {}
        if not isinstance(
            self._protocol,
            (
                _Protocol.Minimisation,
                _Protocol.Equilibration,
                _Protocol.Steering,
                _Protocol.Metadynamics,
                _Protocol.Production,
            ),
        ):
            raise _IncompatibleError(
                "Unsupported protocol: '%s'" % self._protocol.__class__.__name__
            )

        if not isinstance(self._protocol, _Protocol.Minimisation):
            # Set the random number seed.
            if self._is_seeded:
                seed = self._seed
            else:
                seed = -1
            config_options["ig"] = seed

        if isinstance(self._protocol, _Protocol.Metadynamics):
            config_options["plumed"] = 1
            config_options["plumedfile"] = "plumed.dat"

            # Create the PLUMED input file and copy auxiliary files to the working directory.
            self._plumed = _Plumed(str(self._work_dir))
            plumed_config, auxiliary_files = self._plumed.createConfig(
                self._system, self._protocol, self._property_map
            )
            self._setPlumedConfig(plumed_config)
            if auxiliary_files is not None:
                for file in auxiliary_files:
                    file_name = _os.path.basename(file)
                    _shutil.copyfile(file, self._work_dir + f"/{file_name}")
            self._input_files.append(self._plumed_config_file)

            # Expose the PLUMED specific member functions.
            setattr(self, "getPlumedConfig", self._getPlumedConfig)
            setattr(self, "getPlumedConfigFile", self._getPlumedConfigFile)
            setattr(self, "setPlumedConfig", self._setPlumedConfig)
            setattr(self, "getFreeEnergy", self._getFreeEnergy)
            setattr(self, "getCollectiveVariable", self._getCollectiveVariable)
            setattr(self, "sampleConfigurations", self._sampleConfigurations)
            setattr(self, "getTime", self._getTime)

        elif isinstance(self._protocol, _Protocol.Steering):
            config_options["plumed"] = 1
            config_options["plumedfile"] = "plumed.dat"

            # Work out the number of integration steps.
            steps = _math.ceil(
                self._protocol.getRunTime() / self._protocol.getTimeStep()
            )

            # Get the report and restart intervals.
            report_interval = self._protocol.getReportInterval()
            restart_interval = self._protocol.getRestartInterval()

            # Cap the intervals at the total number of steps.
            if report_interval > steps:
                report_interval = steps
            if restart_interval > steps:
                restart_interval = steps

            # Set the random number seed.
            if self._seed is None:
                seed = -1
            else:
                seed = self._seed

            # Convert the timestep to picoseconds.
            timestep = self._protocol.getTimeStep().picoseconds().value()

            self.addToConfig("Production.")
            self.addToConfig(" &cntrl")
            self.addToConfig("  ig=%d," % seed)  # Random number seed.
            self.addToConfig("  ntx=1,")  # Only read coordinates.
            self.addToConfig("  ntxo=1,")  # Output coordinates in ASCII.
            self.addToConfig(
                "  ntpr=%d," % report_interval
            )  # Interval between reporting energies.
            self.addToConfig(
                "  ntwr=%d," % restart_interval
            )  # Interval between saving restart files.
            self.addToConfig(
                "  ntwx=%d," % restart_interval
            )  # Trajectory sampling frequency.
            self.addToConfig("  irest=0,")  # Don't restart.
            self.addToConfig("  dt=%.3f," % timestep)  # Time step.
            self.addToConfig("  nstlim=%d," % steps)  # Number of integration steps.
            self.addToConfig("  ntc=2,")  # Enable SHAKE.
            self.addToConfig(
                "  ntf=2,"
            )  # Don't calculate forces for constrained bonds.
            self.addToConfig("  ntt=3,")  # Langevin dynamics.
            self.addToConfig("  gamma_ln=2,")  # Collision frequency (ps).
            if not has_box or not self._has_water:
                self.addToConfig("  ntb=0,")  # No periodic box.
                self.addToConfig("  cut=999.,")  # Non-bonded cut-off.
                if is_pmemd:
                    self.addToConfig("  igb=6,")  # Use vacuum generalised Born model.
            else:
                self.addToConfig("  cut=8.0,")  # Non-bonded cut-off.
            self.addToConfig(
                "  tempi=%.2f,"  # Initial temperature.
                % self._protocol.getTemperature().kelvin().value()
            )
            self.addToConfig(
                "  temp0=%.2f,"  # Target temperature.
                % self._protocol.getTemperature().kelvin().value()
            )

            # Constant pressure control.
            if self._protocol.getPressure() is not None:
                # Don't use barostat for vacuum simulations.
                if has_box and self._has_water:
                    self.addToConfig("  ntp=1,")  # Isotropic pressure scaling.
                    self.addToConfig(
                        "  pres0=%.5f,"  # Pressure in bar.
                        % self._protocol.getPressure().bar().value()
                    )
                else:
                    _warnings.warn(
                        "Cannot use a barostat for a vacuum or non-periodic simulation"
                    )

            # Activate PLUMED and locate the plumed.dat file.
            self.addToConfig("  plumed=1,")
            self.addToConfig("  plumedfile='plumed.dat',")

            self.addToConfig(" /")

            # Create the PLUMED input file and copy auxiliary files to the working directory.
            self._plumed = _Plumed(self._work_dir)
            plumed_config, auxiliary_files = self._plumed.createConfig(
                self._system, self._protocol, self._property_map
            )
            self._setPlumedConfig(plumed_config)
            if auxiliary_files is not None:
                for file in auxiliary_files:
                    file_name = _os.path.basename(file)
                    _shutil.copyfile(file, self._work_dir + f"/{file_name}")
            self._input_files.append(self._plumed_config_file)

            # Expose the PLUMED specific member functions.
            setattr(self, "getPlumedConfig", self._getPlumedConfig)
            setattr(self, "getPlumedConfigFile", self._getPlumedConfigFile)
            setattr(self, "setPlumedConfig", self._setPlumedConfig)
            setattr(self, "getCollectiveVariable", self._getCollectiveVariable)
            setattr(self, "getTime", self._getTime)

        # Set the configuration.
        config = _Protocol.ConfigFactory(self._system, self._protocol)
        self.addToConfig(
            config.generateAmberConfig(
                extra_options={**config_options, **self._extra_options},
                extra_lines=self._extra_lines,
            )
        )

        # Flag that this isn't a custom protocol.
        self._protocol._setCustomised(False)

    def _generate_args(self):
        """Generate the dictionary of command-line arguments."""

        # Clear the existing arguments.
        self.clearArgs()

        # Add the default arguments.
        self.setArg("-O", True)  # Overwrite.
        self.setArg("-i", "%s.cfg" % self._name)  # Input file.
        self.setArg("-p", "%s.prm7" % self._name)  # Topology file.
        self.setArg("-c", "%s.rst7" % self._name)  # Coordinate file.
        self.setArg("-o", "%s.out" % self._name)  # Redirect stdout to file.
        self.setArg("-r", "%s.crd" % self._name)  # Restart file.
        self.setArg("-inf", "%s.nrg" % self._name)  # Energy info file.

        # Skip if the user has passed a custom protocol.
        if not isinstance(self._protocol, _Protocol.Custom):
            # Append a reference file if this a restrained simulation.
            if isinstance(self._protocol, _Protocol._PositionRestraintMixin):
                if self._protocol.getRestraint() is not None:
                    self.setArg("-ref", "%s_ref.rst7" % self._name)

            # Append a trajectory file if this anything other than a minimisation.
            if not isinstance(self._protocol, _Protocol.Minimisation):
                self.setArg("-x", "%s.nc" % self._name)

    def start(self):
        """
        Start the AMBER process.

        Returns
        -------

        process : :class:`Process.Amber <BioSimSpace.Process.Amber>`
            The process object.
        """

        # The process is currently queued.
        if self.isQueued():
            return

        # Process is already running.
        if self._process is not None:
            if self._process.isRunning():
                return

        # Run the process in the working directory.
        with _Utils.cd(self._work_dir):
            # Create the arguments string list.
            args = self.getArgStringList()

            # Write the command-line process to a README.txt file.
            with open("README.txt", "w") as file:
                # Set the command-line string.
                self._command = "%s " % self._exe + self.getArgString()

                # Write the command to file.
                file.write("# AMBER was run with the following command:\n")
                file.write("%s\n" % self._command)

            # Start the timer.
            self._timer = _timeit.default_timer()

            # Start the simulation. Pass a null string for the stdout file
            # since we've explicitly redirected AMBER output to file since
            # pmemd doesn't write to standard output.
            self._process = _SireBase.Process.run(
                self._exe, args, "", "%s.err" % self._name
            )

        return self

    def getSystem(self, block="AUTO"):
        """
        Get the latest molecular system.

        Parameters
        ----------

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        system : :class:`System <BioSimSpace._SireWrappers.System>`
            The latest molecular system.
        """

        # Wait for the process to finish.
        if block is True:
            self.wait()
        elif block == "AUTO" and self._is_blocked:
            self.wait()

        # Warn the user if the process has exited with an error.
        if self.isError():
            _warnings.warn("The process exited with an error!")

        # Create the name of the restart CRD file.
        restart = "%s/%s.crd" % (self._work_dir, self._name)

        # Check that the file exists.
        if _os.path.isfile(restart):
            # Do we need to get coordinates for the lambda=1 state.
            if "is_lambda1" in self._property_map:
                is_lambda1 = True
            else:
                is_lambda1 = False

            # Create a new molecular system from the restart file.
            new_system = _System(
                _SireIO.MoleculeParser.read(
                    [restart, self._top_file], self._property_map
                )
            )

            # Create a copy of the existing system object.
            old_system = self._system.copy()

            if isinstance(self._protocol, _Protocol._FreeEnergyMixin):
                # Udpate the coordinates and velocities and return a mapping between
                # the molecule indices in the two systems.
                mapping = {
                    _SireMol.MolIdx(x): _SireMol.MolIdx(x)
                    for x in range(0, self._squashed_system.nMolecules())
                }
                (
                    self._squashed_system._sire_object,
                    _,
                ) = _SireIO.updateCoordinatesAndVelocities(
                    self._squashed_system._sire_object,
                    new_system._sire_object,
                    mapping,
                    is_lambda1,
                    self._property_map,
                    self._property_map,
                )

                # Update the unsquashed system based on the updated squashed system.
                old_system = _unsquash(old_system, self._squashed_system, self._mapping)
            else:
                # Update the coordinates and velocities and return a mapping between
                # the molecule indices in the two systems.
                sire_system, mapping = _SireIO.updateCoordinatesAndVelocities(
                    old_system._sire_object,
                    new_system._sire_object,
                    self._mapping,
                    is_lambda1,
                    self._property_map,
                    self._property_map,
                )

                # Update the underlying Sire object.
                old_system._sire_object = sire_system

                # Store the mapping between the MolIdx in both systems so we don't
                # need to recompute it next time.
                self._mapping = mapping
            # Update the box information in the original system.
            if "space" in new_system._sire_object.propertyKeys():
                box = new_system._sire_object.property("space")
                old_system._sire_object.setProperty(
                    self._property_map.get("space", "space"), box
                )

            return old_system

        else:
            return None

    def getCurrentSystem(self):
        """
        Get the latest molecular system.

        Returns
        -------

        system : :class:`System <BioSimSpace._SireWrappers.System>`
            The latest molecular system.
        """
        return self.getSystem(block=False)

    def getTrajectory(self, block="AUTO"):
        """
        Return a trajectory object.

        Parameters
        ----------

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        trajectory : :class:`Trajectory <BioSimSpace.Trajectory.Trajectory>`
            The latest trajectory object.
        """

        # Wait for the process to finish.
        if block is True:
            self.wait()
        elif block == "AUTO" and self._is_blocked:
            self.wait()

        # Warn the user if the process has exited with an error.
        if self.isError():
            _warnings.warn("The process exited with an error!")

        try:
            return _Trajectory.Trajectory(process=self)

        except:
            return None

    def getFrame(self, index):
        """
        Return a specific trajectory frame.

        Parameters
        ----------

        index : int
            The index of the frame.

        Returns
        -------

        frame : :class:`System <BioSimSpace._SireWrappers.System>`
            The System object of the corresponding frame.
        """

        if not type(index) is int:
            raise TypeError("'index' must be of type 'int'")

        max_index = int(
            (self._protocol.getRunTime() / self._protocol.getTimeStep())
            / self._protocol.getRestartInterval()
        )

        if index < 0 or index > max_index:
            raise ValueError(f"'index' must be in range [0, {max_index}].")

        try:
            # Do we need to get coordinates for the lambda=1 state.
            if "is_lambda1" in self._property_map:
                is_lambda1 = True
            else:
                is_lambda1 = False

            # Get the latest trajectory frame.
            new_system = _Trajectory.getFrame(self._traj_file, self._top_file, index)

            # Create a copy of the existing system object.
            old_system = self._system.copy()

            # Update the coordinates and velocities and return a mapping between
            # the molecule indices in the two systems.
            sire_system, mapping = _SireIO.updateCoordinatesAndVelocities(
                old_system._sire_object,
                new_system._sire_object,
                self._mapping,
                is_lambda1,
                self._property_map,
                self._property_map,
            )

            # Update the underlying Sire object.
            old_system._sire_object = sire_system

            # Store the mapping between the MolIdx in both systems so we don't
            # need to recompute it next time.
            self._mapping = mapping

            # Update the box information in the original system.
            if "space" in new_system._sire_object.propertyKeys():
                box = new_system._sire_object.property("space")
                old_system._sire_object.setProperty(
                    self._property_map.get("space", "space"), box
                )

            return old_system

        except:
            return None

    def getRecordKey(self, record, dof=0):
        """
        Parameters
        ----------

        record : str
            The record used in the AMBER standard output, e.g. 'TEMP(K)'.
            Please consult the current AMBER manual for details:
            https://ambermd.org/Manuals.php

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        key : str
            The universal record key that can be used with getRecord.
        """

        # Validate the record string.
        if not isinstance(record, str):
            raise TypeError("'record' must be of type 'str'")

        # Validate the degree of freedom.
        if not isinstance(dof, int):
            raise TypeError("'dof' must be of type 'int'")
        else:
            if dof < 0 or dof > 2:
                raise ValueError("'dof' must be in range [0, 2]")

        # Strip whitespace from the beginning and end of the record and convert
        # to upper case.
        cleaned_record = record.strip().upper()

        # Make sure the record exists in the key mapping.
        if not cleaned_record in self._stdout_key[dof].values():
            raise ValueError(f"No key found for record '{record}'")

        return list(self._stdout_key[dof].keys())[
            list(self._stdout_key[dof].values()).index(cleaned_record)
        ]

    def getRecord(self, key, time_series=False, unit=None, dof=0, block="AUTO"):
        """
        Get a record from the stdout dictionary.

        Parameters
        ----------

        key : str
            A universal record key based on the key used in the AMBER standard
            output. Use 'getRecordKey(record)` to generate the key. The records
            are those used in the AMBER standard output, e.g. 'TEMP(K)'. Please
            consult the current AMBER manual for details: https://ambermd.org/Manuals.php

        time_series : bool
            Whether to return a list of time series records.

        unit : :class:`Unit <BioSimSpace.Units>`
            The unit to convert the record to.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        record : :class:`Type <BioSimSpace.Types>`
            The matching record.
        """

        # Wait for the process to finish.
        if block is True:
            self.wait()
        elif block == "AUTO" and self._is_blocked:
            self.wait()

        # Warn the user if the process has exited with an error.
        if self.isError():
            _warnings.warn("The process exited with an error!")

        return self._get_stdout_record(key.strip().upper(), time_series, unit, dof)

    def getCurrentRecord(self, key, time_series=False, unit=None, dof=0):
        """
        Get a current record from the stdout dictionary.

        Parameters
        ----------

        key : str
            A universal record key based on the key used in the AMBER standard
            output. Use 'getRecordKey(record)` to generate the key. The records
            are those used in the AMBER standard output, e.g. 'TEMP(K)'. Please
            consult the current AMBER manual for details: https://ambermd.org/Manuals.php

        time_series : bool
            Whether to return a list of time series records.

        unit : :class:`Unit <BioSimSpace.Units>`
            The unit to convert the record to.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        record : :class:`Type <BioSimSpace.Types>`
            The matching record.
        """

        # Warn the user if the process has exited with an error.
        if self.isError():
            _warnings.warn("The process exited with an error!")

        return self._get_stdout_record(key.strip().upper(), time_series, unit, dof)

    def getRecords(self, dof=0, block="AUTO"):
        """
        Return the dictionary of stdout time-series records.

        Parameters
        ----------

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        records : :class:`MultiDict <BioSimSpace.Process._process._MultiDict>`
           The dictionary of time-series records.
        """

        # Validate the degree of freedom.
        if not isinstance(dof, int):
            raise TypeError("'dof' must be of type 'int'")
        else:
            if dof < 0 or dof > 2:
                raise ValueError("'dof' must be in range [0, 2]")

        # Wait for the process to finish.
        if block is True:
            self.wait()
        elif block == "AUTO" and self._is_blocked:
            self.wait()

        # Warn the user if the process has exited with an error.
        if self.isError():
            _warnings.warn("The process exited with an error!")

        self.stdout(0)

        return self._stdout_dict[dof].copy()

    def getCurrentRecords(self, dof=0):
        """
        Return the current dictionary of stdout time-series records.

        Parameters
        ----------

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        records : :class:`MultiDict <BioSimSpace.Process._process._MultiDict>`
           The dictionary of time-series records.
        """
        return self.getRecords(dof=dof, block=False)

    def getTime(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the simulation time.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        time : :class:`Time <BioSimSpace.Types.Time>`
            The current simulation time in nanoseconds.
        """

        # No time records for minimisation protocols.
        if isinstance(self._protocol, _Protocol.Minimisation):
            return None

        # Get the list of time steps.
        time_steps = self.getRecord(
            "TIME(PS)", time_series=time_series, unit=None, dof=dof, block=block
        )

        # Convert from picoseconds to nanoseconds.
        if time_steps is not None:
            if time_series:
                return [
                    (x * _Units.Time.picosecond)._to_default_unit() for x in time_steps
                ]
            else:
                return (time_steps * _Units.Time.picosecond)._to_default_unit()

    def getCurrentTime(self, time_series=False, dof=0):
        """
        Get the current simulation time.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        time : :class:`Time <BioSimSpace.Types.Time>`
            The current simulation time in nanoseconds.
        """
        return self.getTime(time_series=time_series, dof=dof, block=False)

    def getStep(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the number of integration steps.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        step : int
            The current number of integration steps.
        """
        return self.getRecord(
            "NSTEP", time_series=time_series, unit=None, dof=dof, block=block
        )

    def getCurrentStep(self, time_series=False, dof=0):
        """
        Get the current number of integration steps.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        step : int
            The current number of integration steps.
        """
        return self.getStep(time_series=time_series, dof=dof, block=False)

    def getBondEnergy(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the bond energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The bond energy.
        """
        return self.getRecord(
            "BOND",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentBondEnergy(self, time_series=False, dof=0):
        """
        Get the current bond energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The bond energy.
        """
        return self.getBondEnergy(time_series=time_series, dof=dof, block=False)

    def getAngleEnergy(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the angle energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The angle energy.
        """
        return self.getRecord(
            "ANGLE",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentAngleEnergy(self, time_series=False, dof=0):
        """
        Get the current angle energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The angle energy.
        """
        return self.getAngleEnergy(time_series=time_series, dof=dof, block=False)

    def getDihedralEnergy(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the total dihedral energy (proper + improper).

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The total dihedral energy.
        """
        return self.getRecord(
            "DIHED",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentDihedralEnergy(self, time_series=False, dof=0):
        """
        Get the current total dihedral energy (proper + improper).

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The total dihedral energy.
        """
        return self.getDihedralEnergy(time_series=time_series, dof=dof, block=False)

    def getElectrostaticEnergy(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the electrostatic energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The electrostatic energy.
        """
        return self.getRecord(
            "EEL",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentElectrostaticEnergy(self, time_series=False, dof=0):
        """
        Get the current dihedral energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The electrostatic energy.
        """
        return self.getElectrostaticEnergy(
            time_series=time_series, dof=dof, block=False
        )

    def getElectrostaticEnergy14(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the electrostatic energy between atoms 1 and 4.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The electrostatic energy between atoms 1 and 4.
        """
        return self.getRecord(
            "14EEL",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentElectrostaticEnergy14(self, time_series=False, dof=0):
        """
        Get the current electrostatic energy between atoms 1 and 4.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The electrostatic energy between atoms 1 and 4.
        """
        return self.getElectrostaticEnergy14(
            time_series=time_series, dof=dof, block=False
        )

    def getVanDerWaalsEnergy(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the Van der Vaals energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The Van der Vaals energy.
        """
        return self.getRecord(
            "VDW",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentVanDerWaalsEnergy(self, time_series=False, dof=0):
        """
        Get the current Van der Vaals energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The Van der Vaals energy.
        """
        return self.getVanDerWaalsEnergy(time_series=time_series, block=False, dof=dof)

    def getVanDerWaalsEnergy14(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the Van der Vaals energy between atoms 1 and 4.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The Van der Vaals energy between atoms 1 and 4.
        """
        return self.getRecord(
            "14VDW",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentVanDerWaalsEnergy14(self, time_series=False, dof=0):
        """
        Get the current Van der Vaals energy between atoms 1 and 4.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The Van der Vaals energy between atoms 1 and 4.
        """
        return self.getVanDerWaalsEnergy(time_series=time_series, block=False, dof=dof)

    def getHydrogenBondEnergy(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the hydrogen bond energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The hydrogen bond energy.
        """
        return self.getRecord(
            "EHBOND",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentHydrogenBondEnergy(self, time_series=False, dof=0):
        """
        Get the current hydrogen bond energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The hydrogen bond energy.
        """
        return self.getHydrogenBondEnergy(time_series=time_series, dof=dof, block=False)

    def getRestraintEnergy(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the restraint energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The restraint energy.
        """
        return self.getRecord(
            "RESTRAINT",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentRestraintEnergy(self, time_series=False, dof=0):
        """
        Get the current restraint energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The restraint energy.
        """
        return self.getRestraintEnergy(time_series=time_series, dof=dof, block=False)

    def getPotentialEnergy(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the potential energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The potential energy.
        """
        return self.getRecord(
            "EPTOT",
            times_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentPotentialEnergy(self, time_series=False, dof=0):
        """
        Get the current potential energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The potential energy.
        """
        return self.getPotentialEnergy(time_series=time_series, dof=dof, block=False)

    def getKineticEnergy(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the kinetic energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The kinetic energy.
        """
        return self.getRecord(
            "EKTOT",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentKineticEnergy(self, time_series=False, dof=0):
        """
        Get the current kinetic energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The kinetic energy.
        """
        return self.getKineticEnergy(time_series=time_series, dof=dof, block=False)

    def getNonBondedEnergy14(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the non-bonded energy between atoms 1 and 4.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The non-bonded energy between atoms 1 and 4.
        """
        return self.getRecord(
            "14NB",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentNonBondedEnergy14(self, time_series=False, dof=0):
        """
        Get the current non-bonded energy between atoms 1 and 4.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The non-bonded energy between atoms 1 and 4.
        """
        return self.getNonBondedEnergy14(time_series=time_series, dof=dof, block=False)

    def getTotalEnergy(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the total energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The total energy.
        """

        if not isinstance(dof, int):
            raise TypeError("'dof' must be of type 'int'")
        else:
            if dof < 0 or dof > 2:
                raise ValueError("'dof' must be in range [0, 2]")

        if isinstance(self._protocol, _Protocol.Minimisation) and dof < 2:
            return self.getRecord(
                "ENERGY",
                time_series=time_series,
                unit=_Units.Energy.kcal_per_mol,
                dof=dof,
                block=block,
            )
        else:
            return self.getRecord(
                "ETOT",
                time_series=time_series,
                unit=_Units.Energy.kcal_per_mol,
                dof=dof,
                block=block,
            )

    def getCurrentTotalEnergy(self, time_series=False, dof=0):
        """
        Get the current total energy.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The total energy.
        """
        return self.getTotalEnergy(time_series=time_series, dof=dof, block=False)

    def getCentreOfMassKineticEnergy(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the kinetic energy of the centre of mass in translation.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The centre of mass kinetic energy.
        """
        return self.getRecord(
            "EKCMT",
            time_series=time_series,
            unit=_Units.Energy.kcal_per_mol,
            dof=dof,
            block=block,
        )

    def getCurrentCentreOfMassKineticEnergy(self, time_series=False, dof=0):
        """
        Get the current kinetic energy of the centre of mass in translation.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        energy : :class:`Energy <BioSimSpace.Types.Energy>`
           The centre of mass kinetic energy.
        """
        return self.getCentreOfMassKineticEnergy(
            time_series=time_series, dof=dof, block=False
        )

    def getVirial(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the virial.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        virial : float
           The virial.
        """
        return self.getRecord("VIRIAL", time_series=time_series, dof=dof, block=block)

    def getCurrentVirial(self, time_series=False, dof=0):
        """
        Get the current virial.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        virial : float
           The virial.
        """
        return self.getVirial(time_series=time_series, dof=dof, block=False)

    def getTemperature(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the temperature.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        temperature : :class:`Temperature <BioSimSpace.Types.Temperature>`
           The temperature.
        """
        return self.getRecord(
            "TEMP(K)",
            time_series=time_series,
            unit=_Units.Temperature.kelvin,
            dof=dof,
            block=block,
        )

    def getCurrentTemperature(self, time_series=False, dof=0):
        """
        Get the current temperature.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        temperature : :class:`Temperature <BioSimSpace.Types.Temperature>`
           The temperature.
        """
        return self.getTemperature(time_series=time_series, dof=dof, block=False)

    def getPressure(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the pressure.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        pressure : :class:`Pressure <BioSimSpace.Types.Pressure>`
           The pressure.
        """
        return self.getRecord(
            "PRESS",
            time_series=time_series,
            unit=_Units.Pressure.bar,
            dof=dof,
            block=block,
        )

    def getCurrentPressure(self, time_series=False, dof=0):
        """
        Get the current pressure.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        pressure : :class:`Pressure <BioSimSpace.Types.Pressure>`
           The pressure.
        """
        return self.getPressure(time_series=time_series, dof=dof, block=False)

    def getVolume(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the volume.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        volume : :class:`Volume <BioSimSpace.Types.Volume>`
           The volume.
        """
        return self.getRecord(
            "VOLUME",
            time_series=time_series,
            unit=_Units.Volume.angstrom3,
            dof=dof,
            block=block,
        )

    def getCurrentVolume(self, time_series=False, dof=0):
        """
        Get the current volume.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        volume : :class:`Volume <BioSimSpace.Types.Volume>`
           The volume.
        """
        return self.getVolume(time_series=time_series, dof=dof, block=False)

    def getDensity(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the density.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        density : float
           The density.
        """
        return self.getRecord("DENSITY", time_series=time_series, dof=dof, block=block)

    def getCurrentDensity(self, time_series=False, dof=0):
        """
        Get the current density.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        density : float
           The density.
        """
        return self.getDensity(time_series=time_series, dof=dof, block=False)

    def getDVDL(self, time_series=False, dof=0, block="AUTO"):
        """
        Get the gradient of the total energy with respect to lambda.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        block : bool
            Whether to block until the process has finished running.

        Returns
        -------

        dv_dl : float
            The gradient of the total energy with respect to lambda.
        """
        return self.getRecord("DVDL", time_series=time_series, dof=dof, block=block)

    def getCurrentDVDL(self, time_series=False, dof=0):
        """
        Get the current gradient of the total energy with respect to lambda.

        Parameters
        ----------

        time_series : bool
            Whether to return a list of time series records.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        dv_dl : float
            The current gradient of the total energy with respect to lambda.
        """
        return self.getDVDL(time_series=time_series, dof=dof, block=False)

    def stdout(self, n=10):
        """
        Print the last n lines of the stdout buffer.

        Parameters
        ----------

        n : int
            The number of lines to print.
        """

        # Ensure that the number of lines is positive.
        if n < 0:
            raise ValueError("The number of lines must be positive!")

        # Flag that this isn't a header line.
        self._is_header = False

        # Flag for the current degree of freedom for free energy simulations.
        dof_flag = 0

        # Append any new lines to the stdout list.
        for line in _pygtail.Pygtail(self._stdout_file):
            self._stdout.append(line.rstrip())
            line = line.strip()

            # Swap dictionary based on the protocol and the degre of freedom to
            # which the next block of records correspond.
            if isinstance(self._protocol, _Protocol._FreeEnergyMixin):
                if "TI region  1" in line and dof_flag != 0:
                    stdout_dict = self._stdout_dict[0]
                    stdout_key = self._stdout_key[0]
                    dof_flag = 0
                elif "TI region  2" in line and dof_flag != 1:
                    stdout_dict = self._stdout_dict[1]
                    stdout_key = self._stdout_key[1]
                    dof_flag = 1
                elif "Softcore part" in line and dof_flag != 2:
                    stdout_dict = self._stdout_dict[2]
                    stdout_key = self._stdout_key[2]
                    dof_flag = 2
            # Default stdout dictionary.
            else:
                stdout_dict = self._stdout_dict[0]
                stdout_key = self._stdout_key[0]

            # Skip empty lines and summary reports.
            if len(line) > 0 and line[0] != "|" and line[0] != "-":
                # Flag that we've started recording results.
                if not self._has_results and line.startswith("NSTEP"):
                    self._has_results = True
                    self._finished_results = False
                # Flag that we've finished recording results.
                elif "A V E R A G E S" in line:
                    self._finished_results = True

                # Parse the results.
                if self._has_results and not self._finished_results:
                    # The first line of output has different formatting for minimisation protocols.
                    if isinstance(self._protocol, _Protocol.Minimisation):
                        # No equals sign in the line.
                        if "NSTEP" in line and "=" not in line:
                            # Split the line using whitespace.
                            data = line.upper().split()

                            # If we find a header, jump to the top of the loop.
                            if len(data) > 0:
                                if data[0] == "NSTEP":
                                    self._is_header = True
                                    continue

                        # Process the header record.
                        if self._is_header:
                            # Split the line using whitespace.
                            data = line.upper().split()

                            # The file hasn't been updated.
                            if (
                                "NSTEP" in stdout_dict
                                and data[0] == stdout_dict["NSTEP"][-1]
                            ):
                                self._finished_results = True
                                continue

                            # Add the timestep and energy records to the dictionary.
                            stdout_dict["NSTEP"] = data[0]
                            stdout_dict["ENERGY"] = data[1]

                            # Add the keys to the mapping
                            stdout_key["NSTEP"] = "NSTEP"
                            stdout_key["ENERGY"] = "ENERGY"

                            # Turn off the header flag now that the data has been recorded.
                            self._is_header = False

                    # All other records are formatted as RECORD = VALUE.

                    # Use a regex search to split the line into record names and values.
                    records = _re.findall(
                        r"([SC_]*[EEL_]*[RES_]*[VDW_]*\d*\-*\d*\s*[A-Z/]+\(*[A-Z]*\)*)\s*=\s*(\-*\d+\.?\d*)",
                        line.upper(),
                    )

                    # Append each record to the dictionary.
                    for key, value in records:
                        # Strip whitespace from beginning and end.
                        key = key.strip()

                        # Format key so it can be re-used for records corresponding to
                        # different degrees of freedom, which use different abbreviations.
                        universal_key = (
                            key.replace("SC_", "")
                            .replace(" ", "")
                            .replace("-", "")
                            .replace("EELEC", "EEL")
                            .replace("VDWAALS", "VDW")
                        )

                        # Store the record using the original key.
                        stdout_dict[key] = value

                        # Map the universal key to the original.
                        stdout_key[universal_key] = key

        # Get the current number of lines.
        num_lines = len(self._stdout)

        # Set the line from which to start printing.
        if num_lines < n:
            start = 0
        else:
            start = num_lines - n

        # Print the lines.
        for x in range(start, num_lines):
            print(self._stdout[x])

    def kill(self):
        """Kill the running process."""

        # Kill the process.
        if not self._process is None and self._process.isRunning():
            self._process.kill()

    def _get_stdout_record(self, key, time_series=False, unit=None, dof=0):
        """
        Helper function to get a stdout record from the dictionary.

        Parameters
        ----------

        key : str
            The universal record key.

        time_series : bool
            Whether to return a time series of records.

        unit : :class:`Type <BioSimSpace.Types._type.Type>`
            The unit to convert the record to.

        dof : int
            The degree of freedom to which the record corresponds. There will
            only be more than one degree of freedom for FreeEnergy protocols,
            where 1 indicates the second TI region and 2 is the softcore part
            of the system (if present).

        Returns
        -------

        record :
            The matching stdout record.
        """

        # Update the standard output dictionary.
        self.stdout(0)

        # No data!
        if len(self._stdout_dict) == 0:
            return None

        if not isinstance(time_series, bool):
            _warnings.warn("Non-boolean time-series flag. Defaulting to False!")
            time_series = False

        # Validate the unit.
        if unit is not None:
            if not isinstance(unit, _Type):
                raise TypeError("'unit' must be of type 'BioSimSpace.Types'")

        # Validate the degree of freedom.
        if not isinstance(dof, int):
            raise TypeError("'dof' must be of type 'int'")
        else:
            if dof < 0 or dof > 2:
                raise ValueError("'dof' must be in range [0, 2]")

        # Extract the dictionary of stdout records for the specified degree of freedom.
        stdout_dict = self._stdout_dict[dof]

        # Map the universal key to the original key used for this degree of freedom.
        try:
            key = self._stdout_key[dof][key]
        except:
            return None

        # Return the list of dictionary values.
        if time_series:
            try:
                if key == "NSTEP":
                    return [int(x) for x in stdout_dict[key]]
                else:
                    if unit is None:
                        return [float(x) for x in stdout_dict[key]]
                    else:
                        return [
                            (float(x) * unit)._to_default_unit()
                            for x in stdout_dict[key]
                        ]

            except KeyError:
                return None

        # Return the most recent dictionary value.
        else:
            try:
                if key == "NSTEP":
                    return int(stdout_dict[key][-1])
                else:
                    if unit is None:
                        return float(stdout_dict[key][-1])
                    else:
                        return (float(stdout_dict[key][-1]) * unit)._to_default_unit()

            except KeyError:
                return None
