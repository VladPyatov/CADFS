from src.fs_parser.exceptions import NotImplementedQueryError

_DEFAULT_PLANES = ['Front.planeOp', 'Top.planeOp', 'Right.planeOp', 'Origin.pointOp']


def rewrite_dummy_query(line: str) -> str:
    """Rewrite a dummyQuery(...) into the equivalent qCreatedBy(...) call."""
    # TODO: use regular expression to catch args
    first, second = line.split('dummyQuery')
    f_position = second.find('"')
    s_position = second.find('"', f_position + 1)
    feature_name = second[f_position : s_position + 1]
    if feature_name[1:-1] in _DEFAULT_PLANES:
        feature_name = 'makeId(' + feature_name + ')'
    else:
        feature_name = 'id+' + feature_name
    line = first + 'qCreatedBy(' + feature_name + second[s_position + 1 :]
    return line


def rewrite_qcompressed(line: str) -> str:
    """Rewrite a qCompressed(...) default-plane reference into qCreatedBy(...)."""
    if 'DUMMY' in line:
        if 'FrontplaneOp' in line:
            op = 'Front.planeOp'
        elif 'TopplaneOp' in line:
            op = 'Top.planeOp'
        elif 'RightplaneOp' in line:
            op = 'Right.planeOp'
        else:
            raise NotImplementedQueryError(f'{line}')
        line = line.split('qCompressed')[0] + f'qCreatedBy(makeId("{op}"), EntityType.FACE);'
    else:
        raise NotImplementedQueryError(f'{line}')
    return line


def rewrite_makequery(line: str) -> str:
    """Pass-through hook for makeQuery lines (currently returns the line unchanged)."""
    return line
