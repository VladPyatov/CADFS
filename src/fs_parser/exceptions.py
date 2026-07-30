class ParserError(Exception):
    pass


class NotImplementedOperationError(ParserError):
    def __init__(self, message=None):
        base = 'Unsupported operation'
        full = f'{base}: {message}' if message else base
        super().__init__(full)


class NotImplementedQueryError(ParserError):
    def __init__(self, message=None):
        base = 'Unsupported query'
        full = f'{base}: {message}' if message else base
        super().__init__(full)


class ForeignGeometryError(ParserError):
    def __init__(self, message=None):
        base = 'Foreign geometry'
        full = f'{base}: {message}' if message else base
        super().__init__(full)


class EmptyGeometryError(ParserError):
    def __init__(self, message=None):
        base = 'Empty geometry'
        full = f'{base}: {message}' if message else base
        super().__init__(full)


class MissingSketchInfoError(ParserError):
    def __init__(self, message=None):
        base = 'Missing sketch-info JSON'
        full = f'{base}: {message}' if message else base
        super().__init__(full)
