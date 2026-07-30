import json
import re

import numpy as np

from src.fs_parser.params import is_query_definition
from src.fs_parser.query import rewrite_dummy_query, rewrite_makequery, rewrite_qcompressed
from src.fs_parser.sketch.elements import (
    skCircle,
    skEllipticalArc,
    skInterpolatedSpline,
    skLineSegment,
    skSpline,
    skSplineSegment,
    skText,
)
from src.fs_parser.values import long_round, parse_json_line


class SketchParser:
    SK_OP_NAME = r'[^(]+\([^,]+,\s*"([^"]+)"'
    SUPPORTED_OPS = (
        'skPoint',
        'skCircle',
        'skLineSegment',
        'skArc',
        'skInterpolatedSplineSegment',
        'skEllipticalArc',
    )
    SEMISUPPORTED_OPS = (
        'skEllipse',
        'skText',
        'skSpline',
        'skSplineSegment',
        'skInterpolatedSpline',
        'skBezier',
        'skImage',
    )

    def __init__(self, context, config):
        self.context = context
        self.config = config

    def invalid_sketch(self, text: str) -> bool:
        """Off by default. Can be used to skip empty sketches, however these sketches sometimes useful"""
        ops = list(self.SUPPORTED_OPS + self.SEMISUPPORTED_OPS)
        ops.remove('skImage')
        other_ops = any([op in text for op in ops])
        return not other_ops

    def parse(self, op_id: str, text: str) -> tuple[str, str | None]:
        """Parse one sketch block into cleaned FeatureScript, or (op_id, None) if empty."""
        if op_id in self.context.unreported_sketches:
            return op_id, None
        if op_id in self.context.sketches.keys():
            sketch_info = self.context.sketches[op_id]
            estimated_op_id = op_id
        else:  # still may lead to errors as feature name in definition and feature name in op call may be different
            lines = text.split('\n')[2:]
            for line in lines:
                if 'newSketch' in line:
                    estimated_op_id = line.split(',')[1].strip()  # this gives 'id + "F0"'
                    estimated_op_id = estimated_op_id.split('"')[1]
                    break
            else:
                raise KeyError(op_id)
            sketch_info = self.context.sketches.get(estimated_op_id)
            self.context.feature_names[estimated_op_id] = self.context.feature_names.pop(op_id)
        # initialize data structures
        local_query = {}
        result = []
        lines = text.split('\n')[2:]
        num_of_lines = len(lines)
        idx = 0
        initial_guess = None
        initial_guess_name = None
        important_guess = {}
        # start parsing
        result.append('        {\n')
        while idx < num_of_lines:
            line = lines[idx].strip()
            if line == '{':
                count = 1
                while count > 0:
                    idx += 1
                    count += lines[idx].count('{')
                    count -= lines[idx].count('}')
                idx += 1
                continue
            elif re.match(r'^\w+\s*=\s*dummyQuery\(', line):
                line = rewrite_dummy_query(line)
            elif re.match(r'^\w+\s*=\s*qCompressed\(', line):
                line = rewrite_qcompressed(line)
            elif self.config.debug:
                pass
            elif 'const initialGuess' in line:
                initial_guess_name = line.split('=')[0]
                initial_guess = parse_json_line(line)
                for k, v in initial_guess.items():
                    if sketch_info.entities.get(k) and (
                        isinstance(sketch_info.entities[k], skText)
                        or isinstance(sketch_info.entities[k], skEllipticalArc)
                    ):
                        # for skText use normalization
                        if isinstance(sketch_info.entities[k], skText):
                            direction = np.array(v[2:4])
                            direction = direction / np.linalg.norm(direction)
                            v[2], v[3] = direction[0], direction[1]
                            # smaller tolerance as IG works in meters
                            if isinstance(v, list):
                                v = [long_round(element, tolerance=1e-5) for element in v]
                            else:
                                v = long_round(v, tolerance=1e-5)
                        else:
                            # for skEllipticalArc we need higher precision
                            if isinstance(v, list):
                                v = [long_round(element, tolerance=1e-10) for element in v]
                            else:
                                v = long_round(v, tolerance=1e-10)
                        important_guess[k] = v
                        sketch_info.entities[k].add_initial_guess(important_guess[k])
                # we will add this information in the end
                idx += 1
                continue
            elif 'annotation' in line or line == '':
                idx += 1
                continue
            elif '= newSketch' in line or '=newSketch' in line:
                if ', "asVersion"' in line:
                    line = line[: line.rfind(', "asVersion"')] + '});'
            elif 'skSetInitialGuess' in line:
                if len(important_guess) == 0:
                    idx += 1
                    continue
                else:
                    # put initial guess before
                    line = (
                        initial_guess_name
                        + ' = '
                        + json.dumps(important_guess)
                        + ';\n'
                        + self.config.default_space
                        + line
                    )
            elif 'skSolve' in line:
                result.append(self.config.default_space + line + '\n')
                break
            elif '_query;' in line:
                query_name = line.split('_query')[0][4:] + '_query'
                new_query_name = f'Q{len(local_query)}'
                local_query[query_name] = new_query_name
                line = line.replace(query_name, new_query_name)
            elif '=makeQuery' in line or '= makeQuery' in line:
                line = rewrite_makequery(line)
            elif line.startswith('sk'):
                match = re.search(self.SK_OP_NAME, line)
                if match:
                    op_name = match.group(1)
                else:
                    raise RuntimeError(f'Failed to detect name: {line}')

                if self._construct_sketch_element(line, op_name, sketch_info, initial_guess) == 'skip':
                    idx += 1
                    continue
                # if geometry not found, skip it - user could just remove it
                if not sketch_info.entities.get(op_name):
                    idx += 1
                    continue
                # check for duplicates:
                dub_id = sketch_info.entities[op_name].duplicate_id
                if dub_id is not None and self.context.entities.get(dub_id.split('.')[0]) is not None:
                    # the element have duplicate that already has been added
                    # so we use the short name of the first element, but the long name of the second
                    self.context.duplicated_entities[op_name] = self.context.entities.get(dub_id.split('.')[0])
                    if len(dub_id.split('.')) > 1:  # need to obtain smth like E.end
                        self.context.duplicated_entities[op_name] += '.' + '.'.join(dub_id.split('.')[1:])
                    idx += 1
                    continue
                if op_name.split('.')[0] not in self.context.entities:
                    self.context.entities[op_name.split('.')[0]] = f'E{len(self.context.entities)}'
                line = repr(sketch_info.entities[op_name])
            elif is_query_definition(line):
                pass
            else:
                raise NotImplementedError(f'unsupported line: {line}')
            # replace names
            for q_name, new_q_name in local_query.items():
                line = line.replace(q_name, new_q_name)
            result.append(self.config.default_space + line + '\n')
            idx += 1
        result.append('        }\n')
        # degenerate case
        if len(result) == 4:
            return estimated_op_id, None
        return estimated_op_id, ''.join(result)

    def _construct_sketch_element(self, line: str, op_name: str, sketch_info, initial_guess) -> str | None:
        """Build or update ``sketch_info.entities[op_name]`` from a sk* line.

        Returns ``'skip'`` for lines that carry no geometry (skImage), so the caller
        can skip them; raises ``NotImplementedError`` for unsupported ops.
        """
        if line.startswith(self.SUPPORTED_OPS):
            if line.startswith('skCircle'):
                if not sketch_info.entities.get(op_name):
                    radius = initial_guess[op_name][-2]
                    x, y = initial_guess[op_name][:2]
                    clockWise = initial_guess[op_name][-1] == 1.0
                    info = {
                        'sketchEntityId': op_name,
                        'isConstruction': '"construction" : true' in line,
                        'geometry': {'radius': radius, 'clockWise': clockWise, 'center2d': {'x': x, 'y': y}},
                    }
                    sketch_info.entities[op_name] = skCircle(info)
        elif line.startswith(self.SEMISUPPORTED_OPS):
            if line.startswith('skEllipse'):
                major_r = initial_guess[op_name][-2]
                minor_r = initial_guess[op_name][-1]
                sketch_info.entities[op_name].add_radius(major_r, minor_r)
            elif line.startswith('skText'):
                params = parse_json_line(line)
                sketch_info.entities[op_name].add_params(params)
            elif line.startswith(('skSplineSegment', 'skSpline')):
                correct_class = skSpline if line.startswith('skSpline') else skSplineSegment
                if not sketch_info.entities.get(op_name):
                    info = {'sketchEntityId': op_name, 'isConstruction': '"construction" : true' in line}
                    sketch_info.entities[op_name] = correct_class(info)
                elif isinstance(sketch_info.entities[op_name], skLineSegment):
                    info = {
                        'sketchEntityId': sketch_info.entities[op_name].id,
                        'isConstruction': sketch_info.entities[op_name].construction,
                    }
                    sketch_info.entities[op_name] = correct_class(info)
                sketch_info.entities[op_name].add_points(initial_guess[op_name])
            elif line.startswith('skInterpolatedSpline'):
                if not sketch_info.entities.get(op_name):
                    info = {
                        'sketchEntityId': op_name,
                        'isConstruction': '"construction" : true' in line,
                        'skipInit': True,
                    }
                    sketch_info.entities[op_name] = skInterpolatedSpline(info)
                sketch_info.entities[op_name].add_points(initial_guess[op_name])
            elif line.startswith('skBezier'):
                params = parse_json_line(line)
                sketch_info.entities[op_name].add_points(initial_guess[op_name], params)
            elif line.startswith('skImage'):
                # skip images as they do not affect the geometry
                return 'skip'
        else:
            raise NotImplementedError(f'unsupported sketch op: {line}')
