import re

from src.fs_parser.params import (
    is_empty_query,
    is_false,
    is_true,
    is_zero_length,
    parse_param_block,
)
from src.fs_parser.values import clean_try_expression


class GeometricOperation:
    keyword: str = None  # FeatureScript function name, e.g. 'extrude'
    default_id: str = None  # id suffix used when the header regex misses
    clean_values: bool = True  # run clean_try_expression on parsed values
    greedy_block: bool = False  # match the parameter block with `.*` vs `.*?`

    def reduce(self, line: str) -> tuple[str, str, dict | None]:
        """Return (context, id, essential_params) for one op-call line."""
        context_part, id_part = self._header(line)
        params = self._parse_params(line)
        return context_part, id_part, self.filter_params(params, line)

    def _header(self, line: str) -> tuple[str, str]:
        """Extract the context and id arguments, falling back to sensible defaults."""
        match = re.search(self.keyword + r'\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,', line)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return 'context', f'id + "{self.default_id}"'

    def _parse_params(self, line: str) -> dict:
        inner = r'(.*)' if self.greedy_block else r'(.*?)'
        pattern = self.keyword + r'\s*\([^{]*\{\s*' + inner + r'\s*\}\s*\)'
        block = re.search(pattern, line, re.DOTALL)
        if not block:
            return {}
        return parse_param_block(block.group(1).strip(), clean_values=self.clean_values)

    @staticmethod
    def process_complex_value(value: str) -> str:
        """Clean a value unless it is empty (preserves the historical guard)."""
        if not value:
            return value
        return clean_try_expression(value)

    def filter_params(self, params: dict, line: str) -> dict | None:
        """Drop parameters equal to their FeatureScript default. Overridden per op."""
        raise NotImplementedError


class AssignVariable(GeometricOperation):
    keyword = 'assignVariable'
    default_id = 'AV1'
    clean_values = False

    def filter_params(self, params: dict, line: str) -> dict | None:
        varType = params.get('variableType', 'VariableType.ANY')
        value_types = {
            'VariableType.ANY': 'anyValue',
            'VariableType.ANGLE': 'angleValue',
            'VariableType.LENGTH': 'lengthValue',
            'VariableType.NUMBER': 'numberValue',
        }
        value_type = value_types.get(varType)
        essential_params = {}
        for key, value in params.items():
            if key == 'asVersion':
                continue
            if key == 'variableType' and varType == 'VariableType.ANY':
                continue
            if key == 'anyValue' and varType != 'VariableType.ANY':
                continue
            if key == 'angleValue' and varType != 'VariableType.ANGLE':
                continue
            if key == 'lengthValue' and varType != 'VariableType.LENGTH':
                continue
            if key == 'numberValue' and varType != 'VariableType.NUMBER':
                continue
            if key == 'value' and value_type is not None and value_type in params.keys():
                continue
            essential_params[key] = value
        return essential_params


class Extrude(GeometricOperation):
    keyword = 'extrude'
    default_id = 'F1'

    def filter_params(self, params: dict, line: str) -> dict | None:
        entities_match = re.search(r'"entities"\s*:\s*(qUnion\(\s*\[([^]]*)\]\s*\))', line, re.DOTALL)

        essential_params = {}

        if entities_match:
            entities_list = entities_match.group(2).strip()
            if entities_list.endswith(','):
                entities_list = entities_list[:-1]
            entities_value = f'qUnion([{entities_list}])'
            essential_params['entities'] = entities_value

        has_draft = is_true(params.get('hasDraft', False))
        has_second_direction = is_true(params.get('hasSecondDirection', False))
        has_second_direction_offset = is_true(params.get('hasSecondDirectionOffset', False))
        has_second_direction_draft = is_true(params.get('hasSecondDirectionDraft', False))

        draft_related = ['draftAngle', 'draftDirection', 'neutralPlane', 'draftPullDirection', 'hasDraft']

        second_dir_related = [
            'secondDirectionBound',
            'secondDirectionOppositeDirection',
            'secondDirectionDepth',
            'hasSecondDirection',
            'secondDirectionBoundEntityFace',
            'secondDirectionBoundEntityBody',
            'secondDirectionBoundEntityVertex',
            'secondDirectionBoundEntity',
            'secondDirectionOppositeExtrudeDirection',
        ]

        second_direction_draft_related = [
            'secondDirectionDraftAngle',
            'secondDirectionDraftPullDirection',
            'hasSecondDirectionDraft',
        ]

        second_direction_offset_related = [
            'secondDirectionOffsetDistance',
            'hasSecondDirectionOffset',
            'secondDirectionOffsetOppositeDirection',
        ]

        default_true = ['secondDirectionOppositeDirection']

        for key, value in params.items():
            if key == 'bodyType' and (
                'SOLID' in value or 'ExtendedToolBodyType.SOLID' in value or 'ToolBodyType.SOLID' in value
            ):
                continue
            if key == 'operationType' and ('NEW' in value or value == 'NewBodyOperationType.NEW'):
                continue
            if key in ['endBound', 'secondDirectionBound'] and 'BLIND' in value:
                continue
            if key == 'surfaceOperationType' and 'NewSurfaceOperationType.NEW' in value:
                continue
            if value == 'qUnion([])':
                continue
            if (value == 'false' or value is False) and key not in default_true:
                continue

            if key in draft_related and not has_draft:
                continue

            if key in second_dir_related and not has_second_direction:
                continue

            if key in second_direction_draft_related and not has_second_direction_draft:
                continue

            if key in second_direction_offset_related and not has_second_direction_offset:
                continue

            if key == 'asVersion':
                continue

            essential_params[key] = value

        return essential_params


class Cplane(GeometricOperation):
    keyword = 'cPlane'
    default_id = 'CP1'
    clean_values = False

    def filter_params(self, params: dict, line: str) -> dict | None:
        essential_params = {}
        cplane_type = params.get('cplaneType', 'CPlaneType.OFFSET')
        cplane_type = cplane_type.split('.')[-1]
        for key, value in params.items():
            if key == 'asVersion':
                continue
            if key == 'defaultType':
                continue
            if value == 'false' or value is False:
                continue
            if key == 'angle' and cplane_type != 'LINE_ANGLE':
                continue

            essential_params[key] = value
        return essential_params


class Cpoint(GeometricOperation):
    keyword = 'cPoint'
    default_id = 'CPt1'
    clean_values = False

    def filter_params(self, params: dict, line: str) -> dict | None:
        essential_params = {}
        for key, value in params.items():
            if key == 'asVersion':
                continue
            essential_params[key] = value
        return essential_params


class Chamfer(GeometricOperation):
    keyword = 'chamfer'
    default_id = 'CH1'

    def filter_params(self, params: dict, line: str) -> dict | None:
        chamferMethod = params.get('chamferMethod')
        if chamferMethod == 'ChamferMethod.FACE_OFFSET':
            params.pop('chamferMethod')

        chamfer_type = None
        chamfer_type_value = params.get('chamferType', 'EQUAL_OFFSETS')
        if 'EQUAL_OFFSETS' in chamfer_type_value:
            chamfer_type = 'EQUAL_OFFSETS'
            params.pop('chamferType', None)
        elif 'TWO_OFFSETS' in chamfer_type_value:
            chamfer_type = 'TWO_OFFSETS'
        elif 'OFFSET_ANGLE' in chamfer_type_value:
            chamfer_type = 'OFFSET_ANGLE'

        essential_params = {}

        for key, value in params.items():
            if key == 'asVersion':
                continue
            if key == 'tangentPropagation' and (value == 'false' or value is False):
                continue

            if key == 'width' and chamfer_type not in ['EQUAL_OFFSETS', 'OFFSET_ANGLE']:
                continue
            if key == 'width1' and chamfer_type != 'TWO_OFFSETS':
                continue
            if key == 'width2' and chamfer_type != 'TWO_OFFSETS':
                continue
            if key == 'angle' and chamfer_type != 'OFFSET_ANGLE':
                continue
            if key == 'oppositeDirection' and chamfer_type not in ['OFFSET_ANGLE', 'TWO_OFFSETS']:
                continue

            essential_params[key] = value

        return essential_params


class Fillet(GeometricOperation):
    keyword = 'fillet'
    default_id = 'FI1'

    def filter_params(self, params: dict, line: str) -> dict | None:
        essential_params = {}
        DEFAULT_FALSE = (
            'tangentPropagation',
            'isVariable',
            'createDetachedSurface',
            'useTrimmedFirstBound',
            'useTrimmedSecondBound',
        )
        for key, value in params.items():
            if key == 'asVersion':
                continue
            if key in DEFAULT_FALSE and value == 'false':
                continue
            if key == 'allowEdgeOverflow' and value == 'true':
                continue

            if key in ('startPartialType', 'endPartialType') and value in (
                'EndTypePartialFillet.PERCENTAGE',
                'PERCENTAGE',
            ):
                continue

            if key == 'crossSection':
                if value in ['FilletCrossSection.CIRCULAR', '"CIRCULAR"']:
                    continue

            if key == 'rho':
                cross_section = params.get('crossSection', '')
                if 'CONIC' not in cross_section:
                    continue

            if key == 'magnitude':
                cross_section = params.get('crossSection', '')
                if 'CURVATURE' not in cross_section:
                    continue

            if key == 'smoothTransition':
                is_variable = params.get('isVariable', 'false')
                if is_variable != 'true':
                    continue

            essential_params[key] = value

        return essential_params


class Revolve(GeometricOperation):
    keyword = 'revolve'
    default_id = 'R1'

    def filter_params(self, params: dict, line: str) -> dict | None:
        revolve_type = None
        revolve_type_value = params.get('revolveType', '')
        if 'TWO_DIRECTIONS' in revolve_type_value:
            revolve_type = 'TWO_DIRECTIONS'
        elif 'FULL' in revolve_type_value:
            revolve_type = 'FULL'
        elif 'SYMMETRIC' in revolve_type_value:
            revolve_type = 'SYMMETRIC'
        elif 'ONE_DIRECTION' in revolve_type_value:
            revolve_type = 'ONE_DIRECTION'

        essential_params = {}

        for key, value in params.items():
            if key == 'asVersion':
                continue

            if key == 'bodyType' and (
                'SOLID' in value or 'ExtendedToolBodyType.SOLID' in value or 'ToolBodyType.SOLID' in value
            ):
                continue

            if key == 'operationType' and ('NEW' in value or value == 'NewBodyOperationType.NEW'):
                continue

            if value == 'qUnion([])':
                continue
            if re.match(r'qUnion\(\s*\[\s*\]\s*\)', value):
                continue

            if is_false(value):
                continue

            if key == 'angleBack' and revolve_type != 'TWO_DIRECTIONS':
                continue

            if key == 'defaultScope':
                continue

            if key in ['angle', 'angleBack'] and revolve_type == 'FULL':
                continue

            if key in ['angle', 'angleBack']:
                if '.value' in value:
                    value = re.sub(r'\s*\}\s*\.value\s*', '}', value)

            essential_params[key] = value

        return essential_params


class Loft(GeometricOperation):
    keyword = 'loft'
    default_id = 'L1'

    def clean_connections(self, connections_value: str) -> str | None:
        return self._clean_object_array(connections_value)

    def clean_guides_array(self, guides_value: str) -> str | None:
        return self._clean_object_array(guides_value)

    def _clean_object_array(self, array_value: str) -> str | None:
        if array_value in ['[]', 'qUnion([])'] or re.match(r'qUnion\(\s*\[\s*\]\s*\)', array_value):
            return None

        if array_value.startswith('[') and array_value.endswith(']'):
            return self._process_object_array(array_value)

        return array_value

    def _process_object_array(self, array_str: str) -> str | None:
        inner_content = array_str[1:-1].strip()

        if not inner_content:
            return None

        cleaned_objects = []

        i = 0
        while i < len(inner_content):
            if inner_content[i] == '{':
                brace_count = 1
                j = i + 1

                while j < len(inner_content) and brace_count > 0:
                    if inner_content[j] == '{':
                        brace_count += 1
                    elif inner_content[j] == '}':
                        brace_count -= 1
                    j += 1

                if brace_count == 0:
                    obj_str = inner_content[i:j]
                    cleaned_obj = self._clean_single_object(obj_str)

                    if cleaned_obj:
                        cleaned_objects.append(cleaned_obj)

                    i = j
                    while i < len(inner_content) and inner_content[i] in ', \n\t':
                        i += 1
                else:
                    break
            else:
                i += 1

        if not cleaned_objects:
            return None

        return '[' + ', '.join(cleaned_objects) + ']'

    def _clean_single_object(self, obj_str: str) -> str | None:
        inner = obj_str[1:-1].strip()

        fields = {}

        field_pattern = r'"([^"]+)"\s*:\s*'

        i = 0
        while i < len(inner):
            match = re.search(field_pattern, inner[i:])
            if not match:
                break

            field_name = match.group(1)
            field_start = i + match.end()

            field_value, next_pos = self._extract_field_value(inner, field_start)

            processed_value = self.process_complex_value(field_value)

            if not self._is_empty_field(processed_value):
                fields[field_name] = processed_value

            i = field_start + next_pos
            while i < len(inner) and inner[i] in ', \n\t':
                i += 1

        if not fields:
            return None

        field_strings = [f'"{key}" : {value}' for key, value in fields.items()]
        return '{ ' + ', '.join(field_strings) + ' }'

    def _extract_field_value(self, text: str, start_pos: int) -> tuple[str, int]:
        i = start_pos

        while i < len(text) and text[i].isspace():
            i += 1

        if i >= len(text):
            return '', len(text) - start_pos

        if text[i:].startswith('qUnion('):
            paren_count = 0
            j = i
            while j < len(text):
                if text[j] == '(':
                    paren_count += 1
                elif text[j] == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        end_pos = j + 1
                        if end_pos < len(text) and text[end_pos : end_pos + 6] == '.value':
                            end_pos += 6
                        return text[i:end_pos], end_pos - start_pos
                j += 1

        elif text[i] == '[':
            bracket_count = 1
            j = i + 1
            while j < len(text) and bracket_count > 0:
                if text[j] == '[':
                    bracket_count += 1
                elif text[j] == ']':
                    bracket_count -= 1
                j += 1
            if bracket_count == 0:
                end_pos = j
                if end_pos < len(text) and text[end_pos : end_pos + 6] == '.value':
                    end_pos += 6
                return text[i:end_pos], end_pos - start_pos

        elif text[i] == '{':
            brace_count = 1
            j = i + 1
            while j < len(text) and brace_count > 0:
                if text[j] == '{':
                    brace_count += 1
                elif text[j] == '}':
                    brace_count -= 1
                j += 1
            if brace_count == 0:
                end_pos = j
                if end_pos < len(text) and text[end_pos : end_pos + 6] == '.value':
                    end_pos += 6
                return text[i:end_pos], end_pos - start_pos

        else:
            j = i
            while j < len(text) and text[j] not in ',}':
                j += 1
            return text[i:j].strip(), j - start_pos

        return text[i:], len(text) - start_pos

    def _is_empty_field(self, field_value: str) -> bool:
        field_value = field_value.strip()

        empty_patterns = ['', 'null', 'undefined']

        for pattern in empty_patterns:
            if field_value == pattern:
                return True

        return False

    def filter_params(self, params: dict, line: str) -> dict | None:
        essential_params = {}
        add_sections = params.get('addSections', False)
        add_sections = is_true(add_sections)
        start_condition = params.get('startCondition', 'LoftEndDerivativeType.DEFAULT')
        end_condition = params.get('endCondition', 'LoftEndDerivativeType.DEFAULT')
        for key, value in params.items():
            if key == 'asVersion':
                continue

            if key == 'bodyType' and (
                'SOLID' in value or 'ExtendedToolBodyType.SOLID' in value or 'ToolBodyType.SOLID' in value
            ):
                continue

            if key == 'operationType' and ('NEW' in value or value == 'NewBodyOperationType.NEW'):
                continue

            if key == 'surfaceOperationType' and ('NEW' in value or value == 'NewSurfaceOperationType.NEW'):
                continue

            if key == 'defaultScope' or key == 'defaultSurfaceScope':
                continue

            if key == 'sectionCount' and not add_sections:
                continue

            if key in ('startCondition', 'endCondition') and value == 'LoftEndDerivativeType.DEFAULT':
                continue

            if key == 'startMagnitude' and start_condition == 'LoftEndDerivativeType.DEFAULT':
                continue

            if key == 'endMagnitude' and end_condition == 'LoftEndDerivativeType.DEFAULT':
                continue

            if key == 'connections':
                cleaned_connections = self.clean_connections(value)
                if cleaned_connections is None:
                    continue
                value = cleaned_connections

            if key == 'guidesArray':
                cleaned_guides = self.clean_guides_array(value)
                if cleaned_guides is None:
                    continue
                value = cleaned_guides

            if value in ['qUnion([])', '[]']:
                continue
            if re.match(r'qUnion\(\s*\[\s*\]\s*\)', value):
                continue

            if is_false(value) and key not in ['makeSolid', 'isClosed']:
                continue

            essential_params[key] = value

        return essential_params


class Mirror(GeometricOperation):
    keyword = 'mirror'
    default_id = 'M1'
    greedy_block = True

    def filter_params(self, params: dict, line: str) -> dict | None:
        essential_params = {}

        for key, value in params.items():
            if key == 'asVersion':
                continue

            if key == 'patternType':
                if value in ['MirrorType.PART', 'PART']:
                    continue

            if value in ['qUnion([])', '[]']:
                continue
            if re.match(r'qUnion\(\s*\[\s*\]\s*\)', value):
                continue

            if key == 'operationType' and ('NEW' in value or value == 'NewBodyOperationType.NEW'):
                continue

            if key == 'instanceFunction':
                if re.search(r'(try)?[Ff]eatureList\(\s*\{\s*\}\s*\)', value):
                    continue

            if value == 'false' or value is False:
                continue

            if 'DEFAULT' in str(value):
                continue

            essential_params[key] = value

        return essential_params


class BooleanBodies(GeometricOperation):
    keyword = 'booleanBodies'
    default_id = 'BB1'

    def filter_params(self, params: dict, line: str) -> dict | None:
        has_offset = is_true(params.get('offset', False))

        essential_params = {}

        for key, value in params.items():
            if key == 'asVersion':
                continue

            if key == 'keepTools' and (value == 'false' or value is False):
                continue

            if key == 'offsetDistance' and not has_offset:
                continue

            if key == 'targets' and value in ['qUnion([])', '[]']:
                continue
            if key == 'targets' and re.match(r'qUnion\(\s*\[\s*\]\s*\)', value):
                continue

            if value == 'false' or value is False:
                continue

            if 'DEFAULT' in str(value):
                continue

            if value in ['[]', 'qUnion([])']:
                continue
            if re.match(r'qUnion\(\s*\[\s*\]\s*\)', value):
                continue

            essential_params[key] = value
        empty_op = 'tools' not in essential_params.keys() and 'targets' not in essential_params.keys()
        if empty_op:
            essential_params = None
        return essential_params


class Hole(GeometricOperation):
    keyword = 'hole'
    default_id = 'H1'
    greedy_block = True

    def filter_params(self, params: dict, line: str) -> dict | None:
        hole_style = 'SIMPLE'
        hole_style_value = params.get('holeStyle') or params.get('style', 'HoleStyle.SIMPLE')
        if 'C_BORE' in hole_style_value:
            hole_style = 'C_BORE'
        elif 'C_SINK' in hole_style_value:
            hole_style = 'C_SINK'
        elif 'SIMPLE' in hole_style_value:
            hole_style = 'SIMPLE'

        end_style = params.get('endStyle', '')

        def hole_depth_not_needed(end_style_value):
            style_upper = end_style_value.upper()
            return any(x in style_upper for x in ['UP_TO_NEXT', 'UP_TO_ENTITY', 'THROUGH'])

        def tapDrillDiameter_not_needed(end_style_value):
            style_upper = end_style_value.upper()
            return 'BLIND_IN_LAST' not in style_upper

        essential_params = {}

        for key, value in params.items():
            if key == 'asVersion':
                continue

            if key in ['cboreDiameter', 'cboreDepth', 'cBoreDiameter', 'cBoreDepth'] and hole_style != 'C_BORE':
                continue

            if key in ['csinkDiameter', 'csinkAngle', 'cSinkDiameter', 'cSinkAngle'] and hole_style != 'C_SINK':
                continue

            if key == 'holeDepth' and hole_depth_not_needed(end_style):
                continue

            if key == 'tapDrillDiameter' and tapDrillDiameter_not_needed(end_style):
                continue

            if key == 'oppositeDirection' and (value == 'false' or value is False):
                continue

            if value == 'false' or value is False:
                continue

            if value in ['lookupTablePath({ "standard" : "Custom" })', 'lookupTablePath({})']:
                continue

            if 'DEFAULT' in str(value):
                continue

            if value in ['qUnion([])', '[]']:
                continue
            if re.match(r'qUnion\(\s*\[\s*\]\s*\)', value):
                continue

            essential_params[key] = value

        return essential_params


class Shell(GeometricOperation):
    keyword = 'shell'
    default_id = 'SH1'

    def filter_params(self, params: dict, line: str) -> dict | None:
        essential_params = {}

        for key, value in params.items():
            if key == 'asVersion':
                continue

            if value == 'false' or value is False:
                continue

            if 'DEFAULT' in str(value):
                continue

            if value in ['[]', 'qUnion([])']:
                continue
            if re.match(r'qUnion\(\s*\[\s*\]\s*\)', value):
                continue

            essential_params[key] = value

        return essential_params


class Sweep(GeometricOperation):
    keyword = 'sweep'
    default_id = 'SW1'
    greedy_block = True

    def filter_params(self, params: dict, line: str) -> dict | None:
        essential_params = {}

        for key, value in params.items():
            if key == 'asVersion':
                continue

            if key == 'bodyType' and (
                'SOLID' in value or 'ExtendedToolBodyType.SOLID' in value or 'ToolBodyType.SOLID' in value
            ):
                continue

            if key == 'operationType' and ('NEW' in value or value == 'NewBodyOperationType.NEW'):
                continue

            if key == 'surfaceOperationType' and ('NEW' in value or value == 'NewSurfaceOperationType.NEW'):
                continue

            if value in ['qUnion([])', '[]']:
                continue
            if re.match(r'qUnion\(\s*\[\s*\]\s*\)', value):
                continue

            if is_false(value):
                continue

            if 'DEFAULT' in str(value):
                continue

            if key == 'profileControl' and 'NONE' in value:
                continue

            if key == 'defaultScope' or key == 'defaultSurfaceScope':
                continue

            essential_params[key] = value

        return essential_params


class Transform(GeometricOperation):
    keyword = 'transform'
    default_id = 'TR1'
    greedy_block = True

    def filter_params(self, params: dict, line: str) -> dict | None:
        transform_type = params.get('transformType', '')

        essential_params = {}

        for key, value in params.items():
            if key == 'asVersion':
                continue

            if is_empty_query(value):
                continue

            if key in ['dx', 'dy', 'dz']:
                if 'TRANSLATION_3D' not in transform_type:
                    continue
                if is_zero_length(value):
                    continue

            if key in ['transformLine', 'oppositeDirectionEntity']:
                if 'TRANSLATION_ENTITY' not in transform_type:
                    continue

            if key in ['transformAxis', 'angle']:
                if 'ROTATION' not in transform_type:
                    continue

            if key in ['transformDirection', 'distance']:
                if 'TRANSLATION_DISTANCE' not in transform_type:
                    continue

            if key == 'oppositeDirection':
                if 'TRANSLATION_DISTANCE' not in transform_type and 'ROTATION' not in transform_type:
                    continue
                if is_false(value):
                    continue

            if key in ['scalePoint', 'scale', 'scaleX', 'scaleY', 'scaleZ', 'uniform']:
                if 'SCALE_UNIFORMLY' not in transform_type:
                    continue

            if key in ['scaleX', 'scaleY', 'scaleZ']:
                uniform_val = params.get('uniform')
                if uniform_val is None or is_true(uniform_val):
                    continue

            if key == 'scale':
                uniform_val = params.get('uniform')
                if uniform_val is not None and is_false(uniform_val):
                    continue
                if value == 1.0 or value == '1.0':
                    continue

            if key == 'uniform' and is_true(value):
                continue

            if key in ['baseConnector', 'destinationConnector', 'oppositeDirectionMateAxis', 'secondaryAxisType']:
                if 'TRANSFORM_MATE_CONNECTORS' not in transform_type:
                    continue

            if key == 'makeCopy':
                if 'COPY' in transform_type:
                    continue

            essential_params[key] = value

        return essential_params


class CircularPattern(GeometricOperation):
    keyword = 'circularPattern'
    default_id = 'CP1'
    greedy_block = True

    def filter_params(self, params: dict, line: str) -> dict | None:
        pattern_type = params.get('patternType', 'PatternType.PART')

        essential_params = {}

        for key, value in params.items():
            if key == 'asVersion':
                continue

            if is_empty_query(value):
                continue

            if key == 'entities':
                if 'PART' not in pattern_type:
                    continue

            if key == 'faces':
                if 'FACE' not in pattern_type:
                    continue

            if key == 'instanceFunction':
                if 'FEATURE' not in pattern_type:
                    continue

            if key == 'booleanScope':
                default_scope = params.get('defaultScope')
                if default_scope is None or is_true(default_scope):
                    continue

            if key == 'skippedInstances':
                skip_instances = params.get('skipInstances')
                if skip_instances is None or is_false(skip_instances):
                    continue

            if key == 'oppositeDirection' and is_false(value):
                continue

            if key == 'equalSpace' and is_false(value):
                continue

            if key == 'isCentered' and is_false(value):
                continue

            if key == 'skipInstances' and is_false(value):
                continue

            if key == 'defaultScope':
                if is_true(value):
                    continue

            if key == 'patternType' and 'PART' in value and 'FACE' not in value and 'FEATURE' not in value:
                continue

            if key == 'operationType' and ('NEW' in value or value == 'NewBodyOperationType.NEW'):
                continue

            essential_params[key] = value

        return essential_params


class DeleteBodies(GeometricOperation):
    keyword = 'deleteBodies'
    default_id = 'DEL1'
    greedy_block = True

    def filter_params(self, params: dict, line: str) -> dict | None:
        essential_params = {}

        for key, value in params.items():
            if key == 'asVersion':
                continue

            if is_empty_query(value):
                continue

            essential_params[key] = value

        return essential_params
