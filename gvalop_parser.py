#!/usr/bin/env python

"""gvalop_parser.py parses a string of Grouped VALues and OPerators into
a group tree of values, operators, and subgroups, which can then be evaluated.

A group is represented by a grouping object, identified by a start and an end string,
and stores its child objects in a list.
An operators is identified by a representation string and an operator function.
The parser is initialized with a list of operators and a list of groupings.

Starting with a root group, the parser parses a string from left to right, building up a tree of groups,
operators and values, with the last two constituting tree leaves. The parsing returns the populated
root group.
Evaluating a group, usually the root group, with an optional evaluation
function for each value, collapses the tree into a single result by consuming each contained item
recursively into a result object.

The consumption of any item turn itself into and replaces itself with a result object:
A group consumes itself by consuming each contained item recursively.
An operator consumes itself by consuming its involved operand(s) and applying the operator function on
the result operand(s).
A value consumes itself by applying its evaluation function on itself.
A result is already consumed and thus does not change.

In order to be able reevaluate a group tree more than once (for different evaluation functions),
since consumption collapses the tree, the evaluation of a group happens on a copy of that group.


Example:

    # A list of songs we want to filter by artists through a parsed string
    songs_list = [
        "Bob Marley - Jammin",
        "Stephen Marley - Break Us Apart",
        "Stephen & Damian Marley - Medication",
        "Ziggy Marley - Dragonfly",
        "Duane Stephenson - Exhale",
        "Tanya Stephens - It's a Pity"
    ]

    # The string to be parsed. Here we want to filter for songs that must contain a
    # 'marley' in any case, while also containing a 'stephen' with neither
    # a 'ziggy' nor a 'damian', or a 'bob'
    artists_filter = "marley && (stephen && !(ziggy || damian) || bob)"

    # Creating a set of operators. Here we use the three logical operators AND, OR, and NOT
    import operator

    opAnd = OperatorBinary(representation="&&", func=operator.and_)
    opOr = OperatorBinary(representation="||", func=operator.or_)
    opNot = OperatorUnary(representation="!", func=operator.not_)

    # Creating a grouping
    grouping = Grouping("(", ")")

    # Creating the parser with the just created operators and grouping
    parser = Parser(operators=[opAnd, opOr, opNot], groupings=[grouping])

    # Parse the filter string and fetch the returned root group
    root = parser.parse(artists_filter)

    # Setup a filter function that (re)evaluates the parsed root
    # for each song
    def songInFilterValue(song):
        result = root.evaluate(
            lambda parser_value: parser_value in song.lower()
        )
        return result.value

    # Filter the songs list
    filtered_list = [
        song for song in songs_list if songInFilterValue(song)

    ]

    print(filtered_list)
    # >>> ['Bob Marley - Jammin', 'Stephen Marley - Break Us Apart']

"""

from copy import deepcopy


__author__ = "Kevin Hambrecht"
__copyright__ = "Non of that crap"
__license__ = "Non of that crap"
__version__ = "0.0.1"
__maintainer__ = "Kevin Hambrecht"
__email__ = "kev.hambrecht@gmail.com"
__status__ = "Production"



class Consumable:
    """Provides a default consume method intended to be overwritten to consume itself"""
    def consume(self, items, index, func=None):
        """Consumes itself at items[index] and updates the items list with a Result.
        This process may consume other items of the list as well.
        Returns (<modified items>, <modified current index>)"""
        return (items, index)


class Group(Consumable):
    """A Group stores contained, nested items as its children to be consumed together. It holds
    a reference to its parent group and is framed by the given grouping"""
    def __init__(self, parent=None, grouping=None):
        self.parent = parent
        self.grouping = grouping
        self.children = []

    def __repr__(self):
        return "Group(%s)" %(",".join((repr(c) for c in self.children)))

    def __len__(self):
        return sum(len(child) for child in self.children)

    def __deepcopy__(self, memodict={}):
        id_self = id(self)
        _copy = memodict.get(id_self)
        if _copy is None:
            _copy = type(self)(
                parent = self.parent,
                grouping = deepcopy(self.grouping)
            )
            _copy.children = deepcopy(self.children)
            memodict[id_self] = _copy
        return _copy

    @property
    def consumed_length(self):
        """Returns the character count of the parsed string that has been consumed up to this point"""
        try:
            consumed_length = self.children[0].consumed_length
        except AttributeError:
            consumed_length = 0
        if self.parent is None:
            return consumed_length
        if self.parent.children[0] is self:
            return consumed_length + len(self.grouping.start)
        for parent_child in self.parent.children:
            if parent_child is self:
                break
            try:
                consumed_length += parent_child.consumed_length
            except AttributeError:
                consumed_length += len(parent_child)

        return consumed_length +1

    def consume(self, items=None, index=None, func=None):
        child_i = 0
        while child_i<len(self.children):
            try:
                self.children, child_i = self.children[child_i].consume(self.children, child_i, func)
            except InvalidOperandError as e:
                if e.index is None:
                    raise InvalidOperandError(f"An operator at index {self.consumed_length+1} "
                                              f"encountered an invalid operand", self.consumed_length+1) from e
                raise e
            if child_i != 0:
                raise MissingOperatorError(f"An operator is missing after index {self.consumed_length+1}",
                                           self.consumed_length+1)
            child_i += 1

        result = self.children[0]
        if self.grouping is not None:
            result.consumed_length += len(self.grouping)
        if items is None or index is None:
            return result
        items[index] = result
        return items, index

    def evaluate(self, func=None):
        """Evaluates itself on a copy, as to not consume the source group, optionally supplying an
        evaluation function. If no evaluation function is supplied, the default one supplied by the parser
        is used"""
        copy_self = deepcopy(self)
        return copy_self.consume(func=func)


class Grouping:
    def __init__(self, start, end):
        self.start = start
        self.end = end

    def __len__(self):
        return len(self.start) + len(self.end)

    def __deepcopy__(self, memodict={}):
        id_self = id(self)
        _copy = memodict.get(id_self)
        if _copy is None:
            _copy = type(self)(
                start = self.start,
                end = self.end
            )
            memodict[id_self] = _copy
        return _copy


class Operator(Consumable):
    """An Operator is identified by a representation string and consumes items as operands
    through the given operator function"""
    def __init__(self, representation, func):
        self.representation = representation
        self.func = func

    def __str__(self):
        return self.representation

    def __repr__(self):
        return f"Op({self.representation})"

    def __len__(self):
        return len(str(self))

    def __deepcopy__(self, memodict={}):
        id_self = id(self)
        _copy = memodict.get(id_self)
        if _copy is None:
            _copy = type(self)(
                representation = self.representation,
                func = self.func
            )
            memodict[id_self] = _copy
        return _copy


class OperatorBinary(Operator):
    """A binary operator that consumes its neighboring items to the left and right as an operand"""
    def consume(self, items, index, func=None):
        try:
            left = items[index-1]
            right = items[index+1]
        except IndexError:
            raise InvalidOperandError('Left or right operand is missing')
        if not isinstance(left, Result):
            raise InvalidOperandError('Left operand is not a Result object')
        items, _ = right.consume(items, index+1, func)
        consumed_length = left.consumed_length + len(self) + items[index+1].consumed_length
        result_value = self.func(left.value, items[index+1].value)
        items[index] = Result(value=result_value, consumed_length=consumed_length)
        del items[index+1]
        del items[index-1]
        return items, index-1

        
class OperatorUnary(Operator):
    """A unary operator that consumes its right neighboring item as an operand"""
    def consume(self, items, index, func=None):
        try:
            right = items[index+1]
        except IndexError:
            raise InvalidOperandError('Right operand is missing')
        items, _ = right.consume(items, index+1, func)
        consumed_length = len(self) + items[index+1].consumed_length
        result = Result(value=self.func(items[index+1].value), consumed_length=consumed_length)
        items[index] = result
        del items[index+1]
        return items, index
        
        
class Value(Consumable):
    """A Value contains the continuous characters of the parsed string between groups and operators.
    It takes an evaluation function that gets executed on its value during consumption"""
    def __init__(self, func, value=""):
        self.func = func
        self.value = value

    def __str__(self):
        return self.value

    def __repr__(self):
        return "Value(%s)"%self.value

    def __len__(self):
        return len(self.value)

    def __bool__(self):
        return len(self) > 0

    def __deepcopy__(self, memodict={}):
        id_self = id(self)
        _copy = memodict.get(id_self)
        if _copy is None:
            _copy = type(self)(
                func = self.func,
            )
            _copy.value = self.value
            memodict[id_self] = _copy
        return _copy

    def consume(self, items, index, func=None):
        if func is not None:
            self.func = func
        result = Result(value=self.func(self.value), consumed_length=len(self))
        items[index] = result
        return items, index


class Result(Consumable):
    """A Result is the result of an item being consumed. It contains its final value and the
    character count of the parsed string that has been consumed for this object"""

    def __init__(self, value, consumed_length):
        self.value = value
        self.consumed_length = consumed_length

    def __repr__(self):
        return "Result(%s)" % self.value

    def __deepcopy__(self, memodict={}):
        id_self = id(self)
        _copy = memodict.get(id_self)
        if _copy is None:
            _copy = type(self)(
                value=deepcopy(self.value),
                consumed_length=self.consumed_length
            )
            memodict[id_self] = _copy
        return _copy



class ParserError(RuntimeError):
    """Base class for all parsing related error.
    It optionally takes an index, indicating the index of the parsed string at which the error was raised"""
    def __init__(self, msg=None, index=None):
        self.index = index
        if msg is None:
            msg = "An error occured while parsing. This is probably due to invalid syntax."
        super().__init__(msg)


class MissingOperatorError(ParserError):
    """Error indicating that an operator was expected. This may happen, for example, when a value directly
    follows a group, or when a unary operator follows a value"""
    pass


class InvalidOperandError(ParserError):
    """Error indicating that an operator was passed an invalid operand. This may happen, for example, when
    a parsed string ends with a unary operator and is thus missing its right operand, or for two
    consecutive binary operators"""
    pass


class Parser:
    """The Parser parses a string from left to right into a Group tree, taking a list of Operators
    and a list of Groupings"""
    def __init__(self, operators, groupings, ValueClass=Value, GroupClass=Group):
        self.operators = operators
        self.groupings = groupings
        self.ValueClass = ValueClass
        self.GroupClass = GroupClass
        self.evaluation_func = None
        
    def _tryConsumeGroupStart(self, data):
        for grouping in self.groupings:
            if self._isSubstringAtIndex(data["string"], data["index"], grouping.start):
                data["current_value"] = self._pushValue(data["current_group"], data["current_value"])
                new_group = self.GroupClass(parent=data["current_group"], grouping=grouping)
                data["current_group"].children.append(new_group)
                data["current_group"] = new_group
                data["index"] += len(grouping.start)
                return True
        return False
        
    def _tryConsumeGroupEnd(self, data):
        if data["current_group"].grouping is None:
            return False
        if self._isSubstringAtIndex(data["string"], data["index"], data["current_group"].grouping.end):
            grouping_end_len = len(data["current_group"].grouping.end)
            data["current_value"] = self._pushValue(data["current_group"], data["current_value"])
            data["current_group"] = data["current_group"].parent
            data["index"] += grouping_end_len
            return True
        return False
        
    def _tryConsumeOperator(self, data):
        for op in self.operators:
            if self._isSubstringAtIndex(data["string"], data["index"], str(op)):
                data["current_value"] = self._pushValue(data["current_group"], data["current_value"])
                data["current_group"].children.append(op)
                data["index"] += len(op)
                return True
        return False

    def _consumeValue(self, data):
        data["current_value"].value += data["string"][data["index"]]
        data["index"] += 1

    def _isSubstringAtIndex(self, string, index, sub):
        return string[index:index+len(sub)] == sub

    def _getNewValue(self):
        return self.ValueClass(self.evaluation_func)

    def _pushValue(self, group, value):
        value.value = value.value.strip()
        if value.value:
            group.children.append(value)
            value = self.ValueClass(self.evaluation_func)
        return value

    def parse(self, string, evaluation_func=lambda x:x):
        """Parses a string into a Group tree and returns the root group.
        The evalutation function is used as a default for all created Values, but
        other evaluation functions may be passed and used when evaluation a group"""
        self.evaluation_func = evaluation_func
        root = Group()

        data = {
            "string" : string,
            "index": 0,
            "current_group": root,
            "current_value": self._getNewValue()
        }

        while data["index"] < len(data["string"]):
            if self._tryConsumeGroupStart(data):
                continue
            if self._tryConsumeGroupEnd(data):
                continue
            if self._tryConsumeOperator(data):
                continue
            self._consumeValue(data)

        self._pushValue(data["current_group"], data["current_value"])
        return root



if __name__ == "__main__":
    from os.path import basename

    self_module = __import__(__name__)
    self_module.__name__ = basename(__file__)

    help(self_module)

