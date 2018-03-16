"""
@package biosimspace
@author  Lester Hedges
@brief   A collection of requirement classes.
"""

from os import path

class Requirement():
    """Base class for BioSimSpace Node requirements."""

    # Set the argparse argument type.
    _arg_type = None

    # Default to single arguments.
    _is_multi = False

    def __init__(self, help=None, default=None, units=None, minimum=None,
            maximum=None, allowed=None, optional=False):
        """Constructor.

           Keyword arguments:

           help     -- The help string.
           default  -- The default value.
           units    -- The units.
           minimum  -- The minimum allowed value.
           maximum  -- The maximum allowed value.
           allowed  -- A list of allowed values.
           optional -- Whether the requirement is optional.
        """

	# Don't allow user to create an instance of this base class.
        if type(self) == Requirement:
            raise Exception("<Requirement> must be subclassed.")

        # Required keyword arguments.

        if help is None:
            raise ValueError("Missing 'help' keyword argument!")
        elif type(help) is not str:
            raise TypeError("'help' keyword argument must be of type 'str'")
        else:
            self._help = help

        # Optional keywords aguments.

        if type(optional) is not bool:
            raise TypeError("'optional' keyword argument must be of type 'bool'")

        # Set defaults.
        self._value = None

        # Set member data.
        self._default = default
        self._units = None
        self._min = minimum
        self._max = maximum
        self._allowed = allowed
        self._is_optional = optional

    def setValue(self, value):
        """Validate and set the value."""

        # Validate the value.
        value = self._validate(value)

        # Now check value against any constraints.

        # Minimum.
        if self._min is not None and value < self._min:
            raise ValueError("The value (%d) is less than the allowed "
                "minimum (%d)" % (value, self._min))

        # Maximum.
        if self._max is not None and value > self._max:
            raise ValueError("The value (%d) is less than the allowed "
                "maximum (%d)" % (value, self._max))

        # Allowed values.
        if self._allowed is not None and value not in self._allowed:
            raise ValueError("The value (%d) is not in the list of allowed values: "
                "%s" % (value, str(self._allowed)))

        # All is okay. Set the value.
        self._value = value

    def getValue(self):
        """Return the value."""
        return self._value

    def getDefault(self):
        """Return the default value."""
        return self._default

    def getUnits(self):
        """Return the units."""
        return self._units

    def getHelp(self):
        """Return the documentation string."""
        return self._help

    def isMulti(self):
        """Whether the requirement has multiple values."""
        return self._is_multi

    def isOptional(self):
        """Whether the requirement is optional."""
        return self._is_optional

    def getArgType(self):
        """The command-line argument type."""
        return self._arg_type

    def getMin(self):
        """Return the minimum allowed value."""
        return self._min

    def getMax(self):
        """Return the maximum allowed value."""
        return self._max

    def getAllowedValues(self):
        """Return the allowed values."""
        return self._allowed

class Boolean(Requirement):
    """A boolean requirement."""

    # Set the argparse argument type.
    _arg_type = bool

    def __init__(self, help=None, default=None):
        """Constructor.

           Keyword arguments:

           help    -- The help string.
           default -- The default value.
        """

        # Call the base class constructor.
        super().__init__(help=help)

        # Set the default value.
        if default is not None:
            self._default = self._validate(default)
            self._is_optional = True

    def _validate(self, value):
        """Validate the value."""

        if type(value) is bool:
            return value
        else:
            raise TypeError("The value should be of type 'bool'.")

class Integer(Requirement):
    """An integer requirement."""

    # Set the argparse argument type.
    _arg_type = int

    def __init__(self, help=None, default=None,
            minimum=None, maximum=None, allowed=None):
        """Constructor.

           Keyword arguments:

           help    -- The help string.
           default -- The default value.
           min     -- The minimum allowed value.
           max     -- The maximum allowed value.
           allowed -- A list of allowed values.
        """

        # Call the base class constructor.
        super().__init__(help=help)

        # Set the minimum value.
        if minimum is not None:
            self._min = self._validate(minimum)

        # Set the maximum value.
        if maximum is not None:
            self._max = self._validate(maximum)

        # Set the allowed values.
        if allowed is not None:
            self._allowed = [self._validate(x) for x in allowed]

        # Set the default value.
        if default is not None:
            self._default = self._validate(default)
            self._is_optional = True

    def _validate(self, value):
        """Validate that the value is of the correct type."""

        if type(value) is int:
            return value
        else:
            raise TypeError("The value should be of type 'int'.")

class Float(Requirement):
    """A floating point requirement."""

    # Set the argparse argument type.
    _arg_type = float

    def __init__(self, help=None, default=None,
            minimum=None, maximum=None, allowed=None):
        """Constructor.

           Keyword arguments:

           help    -- The help string.
           default -- The default value.
           min     -- The minimum allowed value.
           max     -- The maximum allowed value.
           allowed -- A list of allowed values.
        """

        # Call the base class constructor.
        super().__init__(help=help)

        # Set the minimum value.
        if minimum is not None:
            self._min = self._validate(minimum)

        # Set the maximum value.
        if maximum is not None:
            self._max = self._validate(maximum)

        # Set the allowed values.
        if allowed is not None:
            self._allowed = [self._validate(x) for x in allowed]

        # Set the default value.
        if default is not None:
            self._default = self._validate(default)
            self._is_optional = True

    def _validate(self, value):
        """Validate that the value is of the correct type."""

        if type(value) is float:
            return value
        elif type(value) is int:
            return float(value)
        else:
            raise TypeError("The value should be of type 'float' or 'int'.")

class String(Requirement):
    """A string requirement."""

    # Set the argparse argument type.
    _arg_type = str

    def __init__(self, help=None, default=None, allowed=None):
        """Constructor.

           Keyword arguments:

           help    -- The help string.
           default -- The default value.
           allowed -- A list of allowed values.
        """

        # Call the base class constructor.
        super().__init__(help=help)

        # Set the allowed values.
        if allowed is not None:
            self._allowed = [self._validate(x) for x in allowed]

        # Set the default value.
        if default is not None:
            self._default = self._validate(default)
            self._is_optional = True

    def _validate(self, value):
        """Validate that the value is of the correct type."""

        if type(value) is str:
            return value
        else:
            raise TypeError("The value should be of type 'str'")

class File(Requirement):
    """A file set requirement."""

    # Set the argparse argument type.
    _arg_type = str

    def __init__(self, help=None, optional=False):
        """Constructor.

           Keyword arguments:

           help     -- The help string.
           optional -- Whether the file is optional.
        """

        # Call the base class constructor.
        super().__init__(help=help, optional=optional)

    def _validate(self, value):
        """Validate that the value is of the correct type."""

        # Handle optional requirement.
        if self._is_optional and value is None:
            return None

        # Check the type.
        if type(value) is str:
            file = value
        else:
            raise TypeError("The value should be of type 'str'")

        # Make sure the file exists.
        if not path.isfile(file):
            raise IOError(('File doesn\'t exist: "{x}"').format(x=file))
        else:
            return file

class FileSet(Requirement):
    """A file requirement."""

    # Set the argparse argument type.
    _arg_type = str

    # Multiple files can be passed.
    _is_multi = True

    def __init__(self, help=None, optional=False):
        """Constructor.

           Keyword arguments:

           help     -- The help string.
           optional -- Whether the requirement is optional.
        """

        # Call the base class constructor.
        super().__init__(help=help, optional=optional)

    def _validate(self, value):
        """Validate that the value is of the correct type."""

        # Handle optional requirement.
        if self._is_optional and value is None:
            return None

        # We should receive a list of strings.
        if type(value) is list:

            # Loop over all strings.
            for file in value:

                # Check the types.
                if type(file) is str:
                    file = file
                else:
                    raise TypeError("The value should be of type 'str'")

            # Make sure the file exists.
            if not path.isfile(file):
                raise IOError(('File doesn\'t exist: "{x}"').format(x=file))

        # All is okay. Return the value.
        return value