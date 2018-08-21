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
Functionality for solvating molecular systems.
Author: Lester Hedges <lester.hedges@gmail.com>
"""

from BioSimSpace import _gmx_exe, _gromacs_path

from .._Exceptions import MissingSoftwareError as _MissingSoftwareError
from .._SireWrappers import System as _System
from .._SireWrappers import Molecule as _Molecule
from ..Types import Length as _Length

import BioSimSpace.IO as _IO

import os as _os
import re as _re
import shutil as _shutil
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import warnings as _warnings

__all__ = ["solvate", "spc", "spce", "tip3p", "tip4p", "tip5p", "waterModels"]

def solvate(model, molecule=None, box=None, shell=None,
        ion_conc=0, is_neutral=True, work_dir=None, map={}):
    """Add SPC solvent.

       Positional arguments
       --------------------

       model : str
           The name of the water model.

       Keyword arguments
       -----------------

       molecule : BioSimSpace._SireWrappers.Molecule, BioSimSpace._SireWrappers.System
           A molecule, or system of molecules.

       box : [ BioSimSpace.Types.Length ]
           A list containing the box size in each dimension (in nm).

       shell : BioSimSpace.Types.Length
           Thickness of the water shell around the solute.

       ion_conc : float
           The ion concentration in (mol per litre).

       is_neutral : bool
           Whether to neutralise the system.

       work_dir : str
           The working directory for the process.

       map : dict
           A dictionary that maps system "properties" to their user defined
           values. This allows the user to refer to properties with their
           own naming scheme, e.g. { "charge" : "my-charge" }


       Returns
       -------

       system : BioSimSpace._SireWrappers.System
           The solvated molecular system.
    """

    if type(model) is not str:
        raise TypeError("'model' must be of type 'str'")
    else:
        if model not in waterModels():
            raise ValueError("Supported water models are: %s" % waterModels())

    return _model_dict[model](molecule, box, shell, ion_conc, is_neutral, work_dir, map)

def spc(molecule=None, box=None, shell=None, ion_conc=0,
        is_neutral=True, work_dir=None, map={}):
    """Add SPC solvent.

       Keyword arguments
       -----------------

       molecule : BioSimSpace._SireWrappers.Molecule, BioSimSpace._SireWrappers.System
           A molecule, or system of molecules.

       box : [ BioSimSpace.Types.Length ]
           A list containing the box size in each dimension (in nm).

       shell : BioSimSpace.Types.Length
           Thickness of the water shell around the solute.

       ion_conc : float
           The ion concentration in (mol per litre).

       is_neutral : bool
           Whether to neutralise the system.

       work_dir : str
           The working directory for the process.

       map : dict
           A dictionary that maps system "properties" to their user defined
           values. This allows the user to refer to properties with their
           own naming scheme, e.g. { "charge" : "my-charge" }


       Returns
       -------

       system : BioSimSpace._SireWrappers.System
           The solvated molecular system.
    """

    if _gmx_exe is None or _gromacs_path is None:
        raise _MissingSoftwareError("'BioSimSpace.Solvent.spc' is not supported. "
            + "Please install GROMACS (http://www.gromacs.org).")

    # Validate arguments.
    molecule, box, shell, work_dir, map = \
        _validate_input(molecule, box, shell, ion_conc, is_neutral, work_dir, map)

    # Create the solvated system.
    return _solvate(molecule, box, shell, "spc", 3, ion_conc,
            is_neutral, work_dir=work_dir, map=map)

def spce(molecule=None, box=None, shell=None, ion_conc=0, is_neutral=True,
        work_dir=None, map={}):
    """Add SPC/E solvent.

       Keyword arguments
       -----------------

       molecule : BioSimSpace._SireWrappers.Molecule, BioSimSpace._SireWrappers.System
           A molecule, or system of molecules.

       box : [ BioSimSpace.Types.Length ]
           A list containing the box size in each dimension (in nm).

       shell : BioSimSpace.Types.Length
           Thickness of the water shell around the solute.

       ion_conc : float
           The ion concentration in (mol per litre).

       is_neutral : bool
           Whether to neutralise the system.

       work_dir : str
           The working directory for the process.

       map : dict
           A dictionary that maps system "properties" to their user defined
           values. This allows the user to refer to properties with their
           own naming scheme, e.g. { "charge" : "my-charge" }


       Returns
       -------

       system : BioSimSpace._SireWrappers.System
           The solvated molecular system.
    """

    if _gmx_exe is None:
        raise _MissingSoftwareError("'BioSimSpace.Solvent.spce' is not supported. "
            + "Please install GROMACS (http://www.gromacs.org).")

    # Validate arguments.
    molecule, box, shell, work_dir, map = \
        _validate_input(molecule, box, shell, ion_conc, is_neutral, work_dir, map)

    # Create the solvated system.
    return _solvate(molecule, box, shell, "spce", 3, ion_conc,
            is_neutral, work_dir=work_dir, map=map)

def tip3p(molecule=None, box=None, shell=None, ion_conc=0,
        is_neutral=True, work_dir=None, map={}):
    """Add TIP3P solvent.

       Keyword arguments
       -----------------

       molecule : BioSimSpace._SireWrappers.Molecule, BioSimSpace._SireWrappers.System
           A molecule, or system of molecules.

       box : [ BioSimSpace.Types.Length ]
           A list containing the box size in each dimension (in nm).

       shell : BioSimSpace.Types.Length
           Thickness of the water shell around the solute.

       ion_conc : float
           The ion concentration in (mol per litre).

       is_neutral : bool
           Whether to neutralise the system.

       work_dir : str
           The working directory for the process.

       map : dict
           A dictionary that maps system "properties" to their user defined
           values. This allows the user to refer to properties with their
           own naming scheme, e.g. { "charge" : "my-charge" }


       Returns
       -------

       system : BioSimSpace._SireWrappers.System
           The solvated molecular system.
    """

    if _gmx_exe is None:
        raise _MissingSoftwareError("'BioSimSpace.Solvent.tip3p' is not supported. "
            + "Please install GROMACS (http://www.gromacs.org).")

    # Validate arguments.
    molecule, box, shell, work_dir, map = \
        _validate_input(molecule, box, shell, ion_conc, is_neutral, work_dir, map)

    # Create the solvated system.
    return _solvate(molecule, box, shell, "tip3p", 3, ion_conc,
            is_neutral, work_dir=work_dir, map=map)

def tip4p(molecule=None, box=None, shell=None, ion_conc=0,
        is_neutral=True, work_dir=None, map={}):
    """Add TIP4P solvent.

       Keyword arguments
       -----------------

       molecule : BioSimSpace._SireWrappers.Molecule, BioSimSpace._SireWrappers.System
           A molecule, or system of molecules.

       box : [ BioSimSpace.Types.Length ]
           A list containing the box size in each dimension (in nm).

       shell : BioSimSpace.Types.Length
           Thickness of the water shell around the solute.

       ion_conc : float
           The ion concentration in (mol per litre).

       is_neutral : bool
           Whether to neutralise the system.

       work_dir : str
           The working directory for the process.

       map : dict
           A dictionary that maps system "properties" to their user defined
           values. This allows the user to refer to properties with their
           own naming scheme, e.g. { "charge" : "my-charge" }


       Returns
       -------

       system : BioSimSpace._SireWrappers.System
           The solvated molecular system.
    """

    if _gmx_exe is None:
        raise _MissingSoftwareError("'BioSimSpace.Solvent.tip4p' is not supported. "
            + "Please install GROMACS (http://www.gromacs.org).")

    # Validate arguments.
    molecule, box, shell, work_dir, map = \
        _validate_input(molecule, box, shell, ion_conc, is_neutral, work_dir, map)

    # Return the solvated system.
    return _solvate(molecule, box, shell, "tip4p", 4, ion_conc,
            is_neutral, work_dir=work_dir, map=map)

def tip5p(molecule=None, box=None, shell=None, ion_conc=0,
        is_neutral=True, work_dir=None, map={}):
    """Add TIP5P solvent.

       Keyword arguments
       -----------------

       molecule : BioSimSpace._SireWrappers.Molecule, BioSimSpace._SireWrappers.System
           A molecule, or system of molecules.

       box : [ BioSimSpace.Types.Length ]
           A list containing the box size in each dimension (in nm).

       shell : BioSimSpace.Types.Length
           Thickness of the water shell around the solute.

       ion_conc : float
           The ion concentration in (mol per litre).

       is_neutral : bool
           Whether to neutralise the system.

       work_dir : str
           The working directory for the process.

       map : dict
           A dictionary that maps system "properties" to their user defined
           values. This allows the user to refer to properties with their
           own naming scheme, e.g. { "charge" : "my-charge" }


       Returns
       -------

       system : BioSimSpace._SireWrappers.System
           The solvated molecular system.
    """

    if _gmx_exe is None:
        raise _MissingSoftwareError("'BioSimSpace.Solvent.tip5p' is not supported. "
            + "Please install GROMACS (http://www.gromacs.org).")

    # Validate arguments.
    molecule, box, shell, work_dir, map = \
        _validate_input(molecule, box, shell, ion_conc, is_neutral, work_dir, map)

    # Return the solvated system.
    return _solvate(molecule, box, shell, "tip5p", 5, ion_conc,
            is_neutral, work_dir=work_dir, map=map)

def _validate_input(molecule, box, shell, ion_conc, is_neutral, work_dir, map):
    """Internal function to validate function arguments.

       Positional arguments
       --------------------

       molecule : BioSimSpace._SireWrappers.Molecule, BioSimSpace._SireWrappers.System
           A molecule, or system of molecules.

       box : [ BioSimSpace.Types.Length ]
           A list containing the box size in each dimension (in nm).

       shell : BioSimSpace.Types.Length
           Thickness of the water shell around the solute.

       ion_conc : float
           The ion concentration in (mol per litre).

       is_neutral : bool
           Whether to neutralise the system.

       work_dir : str
           The working directory for the process.

       map : dict
           A dictionary that maps system "properties" to their user defined
           values. This allows the user to refer to properties with their
           own naming scheme, e.g. { "charge" : "my-charge" }


       Returns
       -------

       (molecule, box, shell, work_dir, map) : tuple
           The validated input arguments.
    """

    if molecule is not None:
        if type(molecule) is not _Molecule and type(molecule) is not _System:
            raise TypeError("'molecule' must be of type 'BioSimSpace._SireWrappers.Molecule' "
                + "or 'BioSimSpace._SireWrappers.System'")

        # Try to extract the box dimensions from the system.
        if type(molecule) is _System and box is None:
            try:
                if "space" in map:
                    prop = map["space"]
                else:
                    prop = "space"
                box = system.property(prop).dimensions()
                # Convert to a list of Length objects.
                box = [_Length(box[0], "A"), _Length(box[1], "A"), _Length(box[2], "A")]
            except:
                raise ValueError("The system has no box information. Please use "
                    + "the 'box' keyword argument.")
        else:
            if box is None:
                raise ValueError("Missing 'box' keyword argument!")
    else:
        if box is None:
            raise ValueError("Missing 'box' keyword argument!")

        if shell is not None:
            _warnings.warn("Ignoring 'shell' keyword argument as solute is missing.")
            shell = None

    if box is not None:
        if len(box) != 3:
            raise ValueError("The 'box' must have x, y, and z size information.")
        else:
            if not all(isinstance(x, _Length) for x in box):
                raise ValueError("The box dimensions must be of type 'BioSimSpace.Types.Length'")

    if shell is not None:
        if type(shell) is not _Length:
            raise ValueError("'shell' must must be of type 'BioSimSpace.Types.Length'")

    if type(map) is not dict:
        raise TypeError("'map' must be of type 'dict'")

    # Check that the working directory is valid.
    if work_dir is not None and type(work_dir) is not str:
        raise TypeError("'work_dir' must be of type 'str'")

    # If the molecule is merged, make sure the user has remapped the coordinates
    # property.
    if molecule.isMerged():
        # No mapping is present. Default to solvating using the coordinates
        # at lambda = 0.
        if not "coordinates" in map:
            map["coordinates"] = "coordinates0"
        # The mapping is wrong, again use lambda = 0 default.
        else:
            if map["coordinates"] != "coordinates0" and \
               map["coordinates"] != "coordinates1":
                   _warnings.warn("Incorrect coordinate mapping for merged molecule. "
                        + "Using coordiantes from lambda = 0.")
                   map["coordinates"] = "coordinates0"

    if type(ion_conc) is not float and type(ion_conc) is not int:
        raise TypeError("'ion_conc' must be of type 'int' or 'float'.")
    elif ion_conc < 0:
        raise ValueError("'ion_conc' cannot be negative!")

    if type(is_neutral) is not bool:
        raise TypeError("'is_neutral' must be of type 'bool'.")

    # Check that the box is large enough to hold the molecule.
    if molecule is not None and not _check_box_size(molecule, box, map):
        raise ValueError("The 'box' is not large enough to hold the 'molecule'")

    return (molecule, box, shell, work_dir, map)

def _solvate(molecule, box, shell, model, num_point,
        ion_conc, is_neutral, work_dir=None, map={}):
    """Internal function to add solvent using 'gmx solvate'.

       Positional arguments
       --------------------

       molecule : BioSimSpace._SireWrappers.Molecule, BioSimSpace._SireWrappers.System
           A molecule, or system of molecules.

       box : [ BioSimSpace.Types.Length ]
           A list containing the box size in each dimension (in nm).

       shell : BioSimSpace.Types.Length
           Thickness of the water shell around the solute.

       ion_conc : float
           The ion concentration in (mol per litre).

       is_neutral : bool
           Whether to neutralise the system.


       Keyword arguments
       -----------------

       work_dir : str
           The working directory for the process.

       map : dict
           A dictionary that maps system "properties" to their user defined
           values. This allows the user to refer to properties with their
           own naming scheme, e.g. { "charge" : "my-charge" }
    """

    if molecule is not None:
        # Store the centre of the molecule.
        center = molecule._getAABox(map).center()

        # Work out the vector from the centre of the molecule to the centre of the
        # water box, converting the distance in each direction to Angstroms.
        vec = []
        for x, y in zip(box, center):
            vec.append(0.5*x.angstroms().magnitude() - y)

        # Translate the molecule. This allows us to create a water box
        # around the molecule.
        molecule.translate(vec, map)

    # Store the current working directory.
    dir = _os.getcwd()

    # Create a temporary working directory and store the directory name.
    if work_dir is None:
        tmp_dir = _tempfile.TemporaryDirectory()
        work_dir = tmp_dir.name

    # User specified working directory.
    else:
        # Create the directory if it doesn't already exist.
        if not _os.path.isdir(work_dir):
            _os.makedirs(work_dir, exist_ok=True)

    # Change to the working directory for the process.
    # This avoid problems with relative paths.
    _os.chdir(work_dir)

    # Create the gmx command.
    if num_point == 3:
        mod = "spc216"
    else:
        mod = model
    command = "%s solvate -cs %s" % (_gmx_exe, mod)

    if molecule is not None:
        # Write the molecule/system to a GRO files.
        _IO.saveMolecules("input", molecule, "gro87")
        _shutil.copyfile("input.gro87", "input.gro")

        # Update the command.
        command += " -cp input.gro"

        # Add the box information.
        if box is not None:
            command += " -box %f %f %f" % (box[0].nanometers().magnitude(),
                                           box[1].nanometers().magnitude(),
                                           box[2].nanometers().magnitude())

        # Add the shell information.
        if shell is not None:
            command += " -shell %f" % shell.nanometers().magnitude()

    # Just add box information.
    else:
        command += " -box %f %f %f" % (box[0].nanometers().magnitude(),
                                       box[1].nanometers().magnitude(),
                                       box[2].nanometers().magnitude())

    # Add the output file.
    command += " -o output.gro"

    with open("README.txt", "w") as file:
        # Write the command to file.
        file.write("# gmx solvate was run with the following command:\n")
        file.write("%s\n" % command)

    # Create files for stdout/stderr.
    stdout = open("solvate.out", "w")
    stderr = open("solvate.err", "w")

    # Run gmx solvate as a subprocess.
    proc = _subprocess.run(command, shell=True, stdout=stdout, stderr=stderr)
    stdout.close()
    stderr.close()

    # gmx doesn't return sensible error codes, so we need to check that
    # the expected output was generated.
    if not _os.path.isfile("output.gro"):
        _os.chdir(dir)
        raise RuntimeError("'gmx solvate failed to generate output!")

    # Extract the water lines from the GRO file.
    water_lines = []
    water_nums = []
    with open("output.gro", "r") as file:
        for line in file:
            if _re.search("SOL", line):
                # Store the SOL atom record.
                water_lines.append(line)

                # Now match the atom number of the SOL atom.
                match = _re.search("(^[0-9]+)[A-Z]", line.strip())

                # Store the number of the water atom.
                water_nums.append(match.groups()[0])

        # Add any box information. This is the last line in the GRO file.
        water_lines.append(line)

    # Write a GRO file that contains only the water atoms.
    if len(water_lines) - 1 > 0:
        with open("water.gro", "w") as file:
            file.write("BioSimSpace %s water box\n" % model.upper())
            file.write("%d\n" % (len(water_lines)-1))

            for line in water_lines:
                file.write("%s" % line)
    else:
        _os.chdir(dir)
        raise ValueError("No water molecules were generated. Try increasing "
            + "the 'box' size or 'shell' thickness.")

    # Create a TOP file for the water model. By default we use the Amber03
    # force field to generate a dummy topology for the water model.
    with open("water_ions.top", "w") as file:
        file.write("#define FLEXIBLE 1\n\n")
        file.write("; Include AmberO3 force field\n")
        file.write('#include "amber03.ff/forcefield.itp"\n\n')
        file.write("; Include %s water topology\n" % model.upper())
        file.write('#include "amber03.ff/%s.itp"\n\n' % model)
        file.write("; Include ions\n")
        file.write('#include "amber03.ff/ions.itp"\n\n')
        file.write("[ system ] \n")
        file.write("BioSimSpace %s water box\n\n" % model.upper())
        file.write("[ molecules ] \n")
        file.write(";molecule name    nr.\n")
        file.write("SOL               %d\n" % ((len(water_lines)-1) / num_point))

    # Load the water box.
    water = _IO.readMolecules(["water.gro", "water_ions.top"])

    # Create a new system by adding the water to the original molecule.
    if molecule is not None:
        # Translate the molecule and water back to the original position.
        vec = [-x for x in vec]
        molecule.translate(vec, map)
        water.translate(vec)

        if type(molecule) is _System:
            system = _System(molecule + water.getMolecules())
        else:
            system = molecule + water.getMolecules()

        # Add all of the water box properties to the new system.
        for prop in water._sire_system.propertyKeys():
            if prop in map:
                prop = map[prop]

            # Add the space property from the water system.
            system._sire_system.setProperty(prop, water._sire_system.property(prop))
    else:
        system = water

    # Now we add ions to the system and neutralise the charge.
    if ion_conc > 0 or is_neutral:

        # Write the molecule + water system to file.
        _IO.saveMolecules("solvated", system, "gro87")
        _IO.saveMolecules("solvated", system, "grotop")
        _shutil.copyfile("solvated.gro87", "solvated.gro")
        _shutil.copyfile("solvated.grotop", "solvated.top")

        # First write an mdp file.
        with open("ions.mdp", "w") as file:
            file.write("; Neighbour searching\n")
            file.write("cutoff-scheme           = Verlet\n")
            file.write("rlist                   = 1.1\n")
            file.write("pbc                     = xyz\n")
            file.write("verlet-buffer-tolerance = -1\n")
            file.write("\n; Electrostatics\n")
            file.write("coulombtype             = cut-off\n")
            file.write("\n; VdW\n")
            file.write("rvdw                    = 1.0\n")

        # Create the grompp command.
        command = "gmx grompp -f ions.mdp -po ions.out.mdp -c solvated.gro -p solvated.top -o ions.tpr"

        with open("README.txt", "a") as file:
            # Write the command to file.
            file.write("\n# gmx grompp was run with the following command:\n")
            file.write("%s\n" % command)

        # Create files for stdout/stderr.
        stdout = open("grommp.out", "w")
        stderr = open("grommp.err", "w")

        # Run grompp as a subprocess.
        proc = _subprocess.run(command, shell=True, stdout=stdout, stderr=stderr)
        stdout.close()
        stderr.close()

        # Check for the tpr output file.
        if not _os.path.isfile("ions.tpr"):
            _os.chdir(dir)
            raise RuntimeError("'gmx grommp' failed to generate output! "
                + "Perhaps your box is too small?")

        # The ion concentration is unset.
        if ion_conc == 0:
            # Get the current molecular charge.
            charge = system.charge()

            # Round to the nearest integer value.
            charge = round(charge.magnitude())

            # Create the genion command.
            command = "echo SOL | gmx genion -s ions.tpr -o solvated_ions.gro -p solvated.top -neutral"

            # Add enough counter ions to neutralise the charge.
            if charge > 0:
                command += " -nn %d" % abs(charge)
            else:
                command += " -np %d" % abs(charge)
        else:
            # Create the genion command.
            command = "echo SOL | gmx genion -s ions.tpr -o solvated_ions.gro -p solvated.top -%s -conc %f" \
                % ("neutral" if is_neutral else "noneutral", ion_conc)

        with open("README.txt", "a") as file:
            # Write the command to file.
            file.write("\n# gmx genion was run with the following command:\n")
            file.write("%s\n" % command)

        # Create files for stdout/stderr.
        stdout = open("genion.out", "w")
        stderr = open("genion.err", "w")

        # Run genion as a subprocess.
        proc = _subprocess.run(command, shell=True, stdout=stdout, stderr=stderr)
        stdout.close()
        stderr.close()

        # Check for the tpr output file.
        if not _os.path.isfile("solvated_ions.gro"):
            _os.chdir(dir)
            raise RuntimeError("'gmx genion' failed to add ions! Perhaps your box is too small?")

        # Counters for the number of SOL, NA, and CL atoms.
        num_sol = 0
        num_na = 0
        num_cl = 0

        # We now need to loop through the GRO file to work out which water
        # atoms have been replace by ions.
        water_ion_lines = []

        with open("solvated_ions.gro", "r") as file:
            for line in file:
                # This is a Sodium atom.
                if _re.search("NA", line):
                    # Get the atom number.
                    match = _re.search("(^[0-9]+)[A-Z]", line.strip())

                    # This ion has replaced a water atom.
                    if match.groups()[0] in water_nums:
                        water_ion_lines.append(line)
                        num_na += 1

                # This is a Chlorine atom.
                if _re.search("CL", line):
                    # Get the atom number.
                    match = _re.search("(^[0-9]+)[A-Z]", line.strip())

                    # This ion has replaced a water atom.
                    if match.groups()[0] in water_nums:
                        water_ion_lines.append(line)
                        num_cl += 1

                # This is a water atom.
                elif _re.search("SOL", line):
                    water_ion_lines.append(line)
                    num_sol += 1

        # Add any box information. This is the last line in the GRO file.
        water_ion_lines.append(line)

        # Write a GRO file that contains only the water and ion atoms.
        if len(water_ion_lines) - 1 > 0:
            with open("water_ions.gro", "w") as file:
                file.write("BioSimSpace %s water box\n" % model.upper())
                file.write("%d\n" % (len(water_ion_lines)-1))

                for line in water_ion_lines:
                    file.write("%s" % line)

        # Ions have been added. Update the TOP file fo the water model
        # with the new atom counts.
        if num_na > 0 or num_cl > 0:
            with open("water_ions.top", "w") as file:
                file.write("#define FLEXIBLE 1\n\n")
                file.write("; Include AmberO3 force field\n")
                file.write('#include "amber03.ff/forcefield.itp"\n\n')
                file.write("; Include %s water topology\n" % model.upper())
                file.write('#include "amber03.ff/%s.itp"\n\n' % model)
                file.write("; Include ions\n")
                file.write('#include "amber03.ff/ions.itp"\n\n')
                file.write("[ system ] \n")
                file.write("BioSimSpace %s water box\n\n" % model.upper())
                file.write("[ molecules ] \n")
                file.write(";molecule name    nr.\n")
                file.write("SOL               %d\n" % (num_sol / num_point))
                file.write("NA                %d\n" % num_na)
                file.write("CL                %d\n" % num_cl)

        # Load the water/ion box.
        water_ions = _IO.readMolecules(["water_ions.gro", "water_ions.top"])

        # Create a new system by adding the water to the original molecule.
        if molecule is not None:

            if type(molecule) is _System:
                system = _System(molecule + water_ions.getMolecules())
            else:
                system = molecule + water_ions.getMolecules()

            # Add all of the water box properties to the new system.
            for prop in water_ions._sire_system.propertyKeys():
                if prop in map:
                    prop = map[prop]

                # Add the space property from the water system.
                system._sire_system.setProperty(prop, water_ions._sire_system.property(prop))
        else:
            system = water_ions

    # Change back to the original directory.
    _os.chdir(dir)

    return system

def _check_box_size(molecule, box, map={}):
    """Internal function to check that box is big enough for the molecule.

       Positional arguments
       --------------------

       molecule : BioSimSpace._SireWrappers.Molecule, BioSimSpace._SireWrappers.System
           A molecule, or system of molecules.

       box : [ BioSimSpace.Types.Length ]
           A list containing the box size in each dimension (in nm).


       Keyword arguments
       -----------------

       map : dict
           A dictionary that maps system "properties" to their user defined
           values. This allows the user to refer to properties with their
           own naming scheme, e.g. { "charge" : "my-charge" }
    """

    # Get the axis-aligned bounding box of the molecule/system.
    aabox = molecule._getAABox(map)

    # Calculate the box size in each dimension, storing each component as a
    # length in Angstroms.
    mol_box = [_Length(2*x," A") for x in aabox.halfExtents()]

    # Make sure the box is big enough in each dimension.
    for len1, len2 in zip(box, mol_box):
        if len1 < len2:
            return False

    # We made it this far, all dimensions are large enough.
    return True

# Create a list of the water models names.
# This needs to come after all of the solvation functions.
_models = []
_model_dict = {}
import sys as _sys
_namespace = _sys.modules[__name__]
for _var in dir():
    if _var[0] != "_" and _var != "solvate" and _var[0] != "M":
        _models.append(_var)
        _model_dict[_var] = getattr(_namespace, _var)
del(_namespace)
del(_sys)
del(_var)

def waterModels():
    "Return a list of the supported water models"
    return _models
