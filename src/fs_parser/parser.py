import json
import os
import re

from src.fs_parser.config import ParseConfig
from src.fs_parser.context import ParseContext
from src.fs_parser.exceptions import (
    EmptyGeometryError,
    ForeignGeometryError,
    MissingSketchInfoError,
    NotImplementedOperationError,
)
from src.fs_parser.geometric.parser import GeometricParser
from src.fs_parser.geometric.registry import SUPPORTED_GEOMETRIC_OPS
from src.fs_parser.operation import Operation
from src.fs_parser.params import parse_param_block
from src.fs_parser.sketch.elements import Sketch
from src.fs_parser.sketch.parser import SketchParser

ENTITY_TYPES = ['VERTEX', 'EDGE', 'FACE', 'BODY']


class Parser:
    """Orchestrates a document parse: owns the shared context and composes the sub-parsers."""

    def __init__(self, data_path: str, sketch_info: str = None, operation_limit: int = -1, debug: bool = False):
        """Load the FeatureScript source and its companion sketch-info JSON, and wire up
        the parse context + sub-parsers."""
        with open(data_path) as f:
            self.data = f.readlines()
        if sketch_info is None or not os.path.exists(sketch_info):
            raise MissingSketchInfoError(sketch_info)
        with open(sketch_info) as f:
            sketch_data = json.load(f)
            sketch_list = sketch_data['sketches']
        self.context = ParseContext(unreported_sketches=sketch_data.get('unreportedSketches', []))
        for sketch in sketch_list:
            self.context.sketches[sketch['featureId']] = Sketch(sketch)
        self.config = ParseConfig(operation_limit=operation_limit, debug=debug)
        self.sketch_parser = SketchParser(self.context, self.config)
        self.geometric_parser = GeometricParser(self.context, self.config)

    def is_relevant_document(self, text: str) -> bool:
        """True unless the document imports foreign geometry we cannot reconstruct."""
        if 'importForeign(' in text or '::import' in text and 'skImage' not in text:
            return False
        return True

    def contains_broken_geometry(self, op_name: str, text: str) -> bool:
        """True if the op references an unreported/broken sketch, propagating brokenness."""
        for sketch_name in self.context.unreported_sketches:
            if f'"{sketch_name}"' in text:
                self.context.broken_geometry.append(op_name)
                return True
        broken_geometry = self.context.broken_geometry.copy()
        for operation_name in broken_geometry:
            if f'"{operation_name}"' in text:
                self.context.broken_geometry.append(op_name)
                return True
        return False

    def get_operation_type(self, text: str) -> str | None:
        """Classify an operation block as 'sketch' or a geometric op keyword, else None."""
        if 'newSketch' in text:
            return 'sketch'
        for geometric_op in SUPPORTED_GEOMETRIC_OPS.keys():
            if geometric_op + '(' in text:
                return geometric_op

    def _op_call_count(self, text_op: str, text_op_name: str, full_text: str, marker: str) -> int:
        """Count references to an op, folding in the alternate id declared on the
        `marker` line (`cPlane(`/`newSketch(`) when it differs from text_op_name."""
        for line in text_op.split('\n'):
            if marker in line:
                break
        alt_op_id = line.split(',')[1].strip()
        alt_op_id = alt_op_id[alt_op_id.find('"') + 1 :]
        alt_op_id = alt_op_id[: alt_op_id.find('"')]
        if alt_op_id != text_op_name:
            return full_text.count(text_op_name) + full_text.count(alt_op_id)
        return full_text.count(text_op_name)

    def check_redundant_operation(self, op: Operation, full_text: str) -> bool:
        """True if an operation is redundant/no-op and should be dropped from the output."""
        if op.type == 'mateConnector':
            is_redundant = True
        elif op.type == 'booleanBodies':
            is_redundant = 'BooleanOperationType.UNION' in op.text and full_text.count(op.name) < 4
        elif op.type == 'cPlane':
            is_redundant = self._op_call_count(op.text, op.name, full_text, 'cPlane(') < 4
        elif op.type == 'cPoint':
            # TODO: implement qCompressed -> remove this
            is_redundant = 'qCompressed' in op.text
        elif op.type == 'sketch':
            is_redundant = self._op_call_count(op.text, op.name, full_text, 'newSketch(') < 6
        else:
            is_redundant = False
        return is_redundant

    def _find_block_end(self, text: str, start: int) -> int:
        """Find the end of 'features.X = function(id){...}; try(features.X(id));' starting at start."""
        i = text.find('{', start)
        brackets = 0
        while i < len(text):
            if text[i] == '{':
                brackets += 1
            elif text[i] == '}':
                brackets -= 1
                if brackets == 0:
                    break
            i += 1
        # Skip past the try(...) call that follows
        try_pos = text.find('try(', i)
        end = text.find('\n', try_pos)
        return end + 1 if end != -1 else len(text)

    def extract_ops(self, full_text: str) -> list[Operation]:
        """Split the feature body into Operations (name + text), recursing into nested
        feature definitions and registering short feature names."""
        full_text = full_text.replace("Special Chars !@#$%^&*(){{|<>?/.,\\';=-", '')
        text_ops = []
        i = 0

        while i < len(full_text):
            i = full_text.find('if (true)\n', i)
            if i == -1:
                break

            start_position = i
            open_bracket = False
            brackets = 0
            inner_start = None

            while brackets > 0 or not open_bracket:
                i += 1
                if i >= len(full_text):
                    raise ValueError(f'Unmatched bracket at position {start_position}')
                if full_text[i] == '{':
                    if not open_bracket:
                        open_bracket = True
                        inner_start = i + 1
                    brackets += 1
                elif full_text[i] == '}':
                    brackets -= 1

            inner_text = full_text[inner_start:i]
            # Find all nested function definitions, recurse, and stitch cleaned_inner from the gaps
            cleaned_parts = []
            last_end = 0
            for match in re.finditer(r'features\.\w+ = function\(id\)', inner_text):
                nested_start = match.start()
                nested_end = self._find_block_end(inner_text, nested_start)
                text_ops.extend(self.extract_ops(inner_text[nested_start:nested_end]))
                cleaned_parts.append(inner_text[last_end:nested_start])
                last_end = nested_end
            cleaned_parts.append(inner_text[last_end:])
            cleaned_inner = ''.join(cleaned_parts)

            block_text = full_text[start_position:inner_start] + cleaned_inner + '}'

            feature_name_position = full_text.find('try', i)
            feature_name_line = full_text[feature_name_position : full_text.find('\n', feature_name_position)]
            feature_name = feature_name_line.split('features.')[1].split('(id)')[0]
            text_ops.append(Operation(name=feature_name, text=block_text))
            self.context.feature_names[feature_name] = f'F{len(text_ops) - 1}'

        return text_ops

    def postprocess_output(self, operations: list[Operation], parsed_ops: list[str]) -> list[str]:
        """Drop dangling cPoint/assignVariable operations whose result is never used."""
        op_types = [op.type for op in operations]
        if 'cPoint' in op_types:
            full_text = ''.join(parsed_ops)
            variables_to_remove = set()
            for operation_index, parsed_op in enumerate(parsed_ops):
                if 'cPoint(' in parsed_op:
                    for op_line in parsed_op.split('\n'):
                        if 'cPoint(' in op_line:
                            op_name = op_line.strip().split(',')[1]
                            op_name = op_name.split(' + ')[-1].strip()[1:-1]
                            if full_text.count(f'"{op_name}"') == 1:
                                self.context.feature_names.pop(op_name)
                                variables_to_remove.add(operation_index)
                            break
            parsed_ops = [parsed_ops[i] for i in range(len(parsed_ops)) if i not in variables_to_remove]

        if 'assignVariable' in op_types:
            variable_names = {}
            # extract variable names
            for operation_index, parsed_op in enumerate(parsed_ops):
                if 'assignVariable(' in parsed_op:
                    for op_line in parsed_op.split('\n'):
                        if 'assignVariable(' in op_line:
                            op_name = op_line.strip().split(',')[1]
                            op_name = op_name.split(' + ')[-1].strip()[1:-1]
                            op_params = self.context.geometric_operations[op_name]['params']
                            variable_names[operation_index] = (op_name, op_params['name'][1:-1])
                            break
            # go through variables in reverse order and remove them
            variables_to_remove = set()
            for var_operation_index, (op_name, var_name) in list(variable_names.items())[::-1]:
                for j, parsed_op in enumerate(parsed_ops[::-1]):
                    operation_index = len(parsed_ops) - 1 - j
                    if operation_index in variables_to_remove:
                        continue
                    if f"lookup('{var_name}')" in parsed_op:
                        break
                else:
                    self.context.feature_names.pop(op_name)
                    variables_to_remove.add(var_operation_index)

            parsed_ops = [parsed_ops[i] for i in range(len(parsed_ops)) if i not in variables_to_remove]
        return parsed_ops

    def extract_extra_vars(self, text: list) -> dict:
        """Parse the trailing configuration map (if any) that supplies lookup() values."""
        for line in text[::-1]:
            line = line.strip()
            if line.endswith('});'):
                var_line = line
                break
            else:
                return {}
        match = re.search(r'\{[^{}]*\}', var_line)
        if match:
            params = match.group()
        else:
            return {}
        if params.strip() == '{}':
            return {}
        try:
            parsed_params = parse_param_block(params, clean_values=True)
        except Exception:
            return {}
        return parsed_params

    def process_text(self) -> tuple[str, list[str]]:
        """Parse the loaded FeatureScript document into cleaned code and its op-type list."""
        text = self.data
        extra_variables: dict = self.extract_extra_vars(text)
        full_text = ''.join(text)
        if not self.is_relevant_document(full_text):
            raise ForeignGeometryError
        operations = self.extract_ops(full_text)
        # classify each operation in the sequence
        for op in operations:
            op.type = self.get_operation_type(op.text)
            if op.type is None:
                raise NotImplementedOperationError(f'{op.text}')
        # remove sketch in the end
        last_op_index = len(operations) - 1
        while operations[last_op_index].type == 'sketch':
            last_op_index -= 1
            if last_op_index < 0:
                raise EmptyGeometryError(full_text)
        operations = operations[: last_op_index + 1]
        preambula = self._build_preamble(text)
        limit = len(operations) if self.config.operation_limit == -1 else self.config.operation_limit
        output = self._emit_operations(operations, full_text, limit)
        output = self.postprocess_output(operations, output)
        processed_text = ''.join(output)
        processed_text = self._shorten_names(processed_text)
        processed_text = self._replace_function_shorthands(processed_text, extra_variables)
        return preambula + processed_text, [op.type for op in operations[:limit]]

    def _build_preamble(self, text: list) -> str:
        """Emit the FeatureScript header: version, imports, and unit/query shorthands."""
        preambula = []
        # 1. version
        if 'FeatureScript' in text[0]:
            preambula.append(text[0])
        else:
            raise NotImplementedError('document should start with FeatureScript version')
        # 2. imports
        cursor = 1
        while 'import' in text[cursor]:
            if '::import' not in text[cursor]:
                preambula.append(text[cursor])
            if 'geometry.fs' in text[cursor]:
                preambula.append(text[cursor].replace('geometry.fs', 'common.fs'))
            cursor += 1
        # 3. short definitions for units, entity types and query helpers
        preambula.append('const mm = millimeter;\n')
        for ent in ENTITY_TYPES:
            preambula.append(f'const {ent} = EntityType.{ent};\n')
        preambula.append('function v(x, y){return vector(x, y);}\n')
        preambula.append('function OD(order){return orderDisambiguation(order);}\n')
        preambula.append('function OSD(set){return originalSetDisambiguation(set);}\n')
        preambula.append('function TD(topology){return topologyDisambiguation(topology);}\n')
        preambula.append('function TDD(query){return trueDependencyDisambiguation(query);}\n')
        preambula.append('function sQuery(a, b, c) {return sketchEntityQuery(a, b, c);}\n')
        return ''.join(preambula)

    def _emit_operations(self, operations: list[Operation], full_text: str, limit: int) -> list[str]:
        """Parse each operation and collect the emitted feature-definition body lines."""
        output = []
        output.append("""
annotation { "Feature Type Name" : "Feature", "Feature Type Description" : "" }
export const myFeature = defineFeature(function(context is Context, id is Id, definition is map)
    precondition{}
    {\n""")
        for op in operations[:limit]:
            is_redundant = self.check_redundant_operation(op, full_text)
            if is_redundant:
                parsed_op_id, parsed_operation = op.name, None
            elif op.type == 'sketch':
                parsed_op_id, parsed_operation = self.sketch_parser.parse(op.name, op.text)
            else:
                parsed_op_id, parsed_operation = self.geometric_parser.parse(op.name, op.type, op.text)
            if parsed_operation is None:
                self.context.feature_names.pop(parsed_op_id)
            elif not self.contains_broken_geometry(parsed_op_id, parsed_operation):
                output.append(parsed_operation)
        output.append('    });')
        return output

    def _shorten_names(self, processed_text: str) -> str:
        """Renumber feature names to F0.. and replace entity names with short forms."""
        new_feature_names = {}
        for k, v in self.context.feature_names.items():
            new_feature_names[k] = f'F{len(new_feature_names)}'
        self.context.feature_names = new_feature_names
        # replace by descending original-name length so longer names win first
        self.context.duplicated_entities = dict(
            sorted(self.context.duplicated_entities.items(), key=lambda x: len(x[0]), reverse=True)
        )
        self.context.entities = dict(sorted(self.context.entities.items(), key=lambda x: len(x[0]), reverse=True))
        for old_name, new_name in self.context.feature_names.items():
            processed_text = processed_text.replace(old_name, new_name)
        # each entity may be referenced bare ("E0") or with a topological suffix
        # ("E0.center"); the last suffix is intentionally unterminated (no closing ")
        duplicate_suffixes = (
            '"',
            '.center"',
            '.bottom"',
            '.top"',
            '.left"',
            '.right"',
            '.start"',
            '.end"',
            '.sketch_text',
        )
        for old_name, new_name in self.context.duplicated_entities.items():
            for suffix in duplicate_suffixes:
                processed_text = processed_text.replace('"' + old_name + suffix, '"' + new_name + suffix)
        for old_name, new_name in self.context.entities.items():
            processed_text = processed_text.replace(old_name, new_name)
        for ent in ENTITY_TYPES:
            processed_text = processed_text.replace(f'EntityType.{ent}', ent)
        return processed_text

    def _replace_function_shorthands(self, processed_text: str, extra_variables: dict) -> str:
        """Swap the full FeatureScript builders for their preamble-defined shorthands."""
        processed_text = processed_text.replace('sketchEntityQuery(', 'sQuery(')
        processed_text = processed_text.replace('orderDisambiguation(', 'OD(')
        processed_text = processed_text.replace('topologyDisambiguation(', 'TD(')
        processed_text = processed_text.replace('originalSetDisambiguation(', 'OSD(')
        processed_text = processed_text.replace('trueDependencyDisambiguation(', 'TDD(')
        if 'assignVariable' in processed_text:
            processed_text = processed_text.replace('lookup(', 'getVariable(context, ')
        if extra_variables:
            for var, value in extra_variables.items():
                processed_text = processed_text.replace(f"lookup('{var}')", value)
        return processed_text
