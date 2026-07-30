import re

from src.fs_parser.geometric.registry import SUPPORTED_GEOMETRIC_OPS
from src.fs_parser.params import is_query_definition
from src.fs_parser.query import rewrite_dummy_query, rewrite_makequery, rewrite_qcompressed
from src.fs_parser.values import clean_try_expression


class GeometricParser:
    """Parses geometric feature operations into cleaned FeatureScript."""

    def __init__(self, context, config):
        self.context = context
        self.config = config

    def is_empty_operation(self, text: str) -> bool:
        """Return True if the operation has empty geometry (empty entities/surfaceEntities)."""

        entities_match = re.search(r'"entities"\s*:\s*qUnion\(\s*\[\s*\]\s*\)', text)
        surface_entities_match = re.search(r'"surfaceEntities"\s*:\s*qUnion\(\s*\[\s*\]\s*\)', text)
        faces_match = re.search(r'"faces"\s*:\s*qUnion\(\s*\[\s*\]\s*\)', text)
        if entities_match and surface_entities_match:
            return True

        entities_empty = entities_match is not None
        has_surface_entities = '"surfaceEntities"' in text
        has_faces = '"faces"' in text
        faces_empty = faces_match is not None

        if entities_empty and not has_surface_entities and (not has_faces or faces_empty):
            return True
        # check empty hole
        if 'hole(' in text:
            locations_match = re.search(r'"locations"\s*:\s*qUnion\(\s*\[\s*\]\s*\)', text)
            if locations_match:
                return True
        # check empty sweep
        if 'sweep(' in text:
            profiles_match = re.search(r'"profiles"\s*:\s*qUnion\(\s*\[\s*\]\s*\)', text)
            if profiles_match:
                return True
        return False

    def parse(self, op_id: str, op_name: str, text: str) -> tuple[str, str | None]:
        """Parse one geometric feature block into its cleaned FeatureScript body.

        Returns (op_id, body) or (op_id, None) when the operation is dropped.
        """
        if self.is_empty_operation(text):
            return op_id, None
        local_query = {}
        query_to_remove = []  # this queries are redundant and will be deleted
        result = []
        lines = text.split('\n')[2:]
        num_of_lines = len(lines)
        idx = 0
        result.append('        {\n')
        while idx < num_of_lines:
            line = lines[idx].strip()
            if line == '{' or line == '}' or line == '' or line.isspace():
                idx += 1
                continue
            elif 'annotation' in line:
                idx += 1
                continue
            elif '_query;' in line:
                name = line.split('_query')[0][4:] + '_query'
                new_name = f'Q{len(local_query)}'
                local_query[name] = new_name
                line = line.replace(name, new_name)

            elif re.match(r'^\w+\s*=\s*dummyQuery\(', line):
                line = rewrite_dummy_query(line)
            # elif '=qCompressed' in line:
            elif re.match(r'^\w+\s*=\s*qCompressed\(', line):
                line = rewrite_qcompressed(line)
            elif op_name + '(' in line and not self.config.debug:
                line, estimated_op_id, new_query_to_remove = self._emit_geometric_op(line, op_name, op_id, local_query)
                if line is None:
                    return estimated_op_id, None
                if new_query_to_remove:
                    query_to_remove = new_query_to_remove
            elif op_name + '(' in line and self.config.debug:
                pass
            elif '=makeQuery' in line or '= makeQuery' in line:
                line = rewrite_makequery(line)
            elif is_query_definition(line):
                pass
            else:
                raise NotImplementedError(f'unsupported line: {line}')

            # simplify names
            for name, new_name in local_query.items():
                line = line.replace(name, new_name)

            result.append(self.config.default_space + line + '\n')
            idx += 1

        filtered_result = self._drop_removed_queries(result, query_to_remove, local_query)
        filtered_result.append('        }\n')
        return estimated_op_id, ''.join(filtered_result)

    def _emit_geometric_op(
        self, line: str, op_name: str, op_id: str, local_query: dict
    ) -> tuple[str | None, str, list | None]:
        """Reduce and format one geometric-op call.

        Returns ``(formatted_line, estimated_op_id, query_to_remove)`` on success, or
        ``(None, id_to_report, None)`` when the operation should be dropped (empty
        params or nothing left after filtering).
        """
        context_part, id_part, essential_params = SUPPORTED_GEOMETRIC_OPS[op_name].reduce(line)
        if essential_params is None:
            return None, op_id, None
        estimated_op_id = id_part.strip()
        estimated_op_id = estimated_op_id[estimated_op_id.find('"') + 1 : -1]
        if estimated_op_id != op_id:
            self.context.feature_names[estimated_op_id] = self.context.feature_names.pop(op_id)
        for key, value in essential_params.items():
            essential_params[key] = clean_try_expression(value)
        query_to_remove = []
        filtered_params = {}
        for key, value in essential_params.items():
            if value == 'qUnion([])':
                continue
            if key in ('defaultScope', 'defaultSurfaceScope'):
                continue
            if re.match(r'qUnion\(\s*\[\s*\]\s*\)', value) and ',' not in value:
                continue
            if key == 'booleanScope':
                match = re.search(r'qUnion\(\[([^\]]+)\]', value)
                args_string = match.group(1)
                query_to_remove = [arg.strip() for arg in args_string.split(',')]
                continue
            # simplify names
            for name, new_name in local_query.items():
                value = value.replace(name, new_name)
            filtered_params[key] = value

        self.context.geometric_operations[estimated_op_id] = {'type': op_name, 'params': filtered_params}
        formatted_params = [f'"{key}" : {value}' for key, value in filtered_params.items()]
        if not formatted_params:
            return None, estimated_op_id, None
        params_str = ', '.join(formatted_params)
        line = f'{op_name}({context_part}, {id_part}, {{{params_str}}});'
        return line, estimated_op_id, query_to_remove

    def _drop_removed_queries(self, result: list[str], query_to_remove: list[str], local_query: dict) -> list[str]:
        """Drop lines that define queries flagged redundant via a booleanScope."""
        if not query_to_remove:
            return result
        filtered_result = []
        for line in result:
            remove_line = False
            for q in query_to_remove:
                q = local_query[q]
                if f'var {q};' in line or re.search(rf'\s*{q}\s*=\s*', line.replace(f'sub{q}', '')):
                    remove_line = True
                    break
            if not remove_line:
                filtered_result.append(line)
        return filtered_result
