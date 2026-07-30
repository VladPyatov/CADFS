from src.fs_parser.values import long_round


class SketchElement:
    def __init__(self, info: dict, units: str = 'mm') -> None:
        self.construction = info['isConstruction']
        self.id = info['sketchEntityId']
        self.units = units
        self.vec = 'v'
        self.duplicate_id = None
        self.no_duplicates = False

    def _to_units(self, value) -> float:
        """Scale a raw API coordinate (metres) into the element's display units."""
        if self.units == 'mm':
            return value * 1000
        else:
            raise NotImplementedError(f'Unknown units: {self.units}')

    def _v(self, x, y, fn: str = None) -> str:
        """FeatureScript vector literal, e.g. 'v(1, 2) * mm', with rounded coords.

        ``fn`` overrides the constructor name (e.g. 'vector'); defaults to self.vec.
        """
        return f'{fn or self.vec}({long_round(x)}, {long_round(y)}) * {self.units}'

    def _points_str(self) -> str:
        """Bracketed, comma-joined vector literals for a points list."""
        return '[' + ', '.join(self._v(p[0], p[1]) for p in self.points) + ']'

    def _finish(self, base: str) -> str:
        """Append the optional construction flag and the closing brace."""
        if self.construction:
            base += ', "construction": true'
        return base + '}'


class skPoint(SketchElement):
    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)
        self.x = self._to_units(info['position2d']['x'])
        self.y = self._to_units(info['position2d']['y'])

    def __repr__(self) -> str:
        return f'skPoint(sketch, "{self.id}", ' + self.__str__() + ');'

    def __str__(self) -> str:
        base = '{' + f'"position": {self._v(self.x, self.y)}'
        return self._finish(base)


class skCircle(SketchElement):
    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)
        self.x = self._to_units(info['geometry']['center2d']['x'])
        self.y = self._to_units(info['geometry']['center2d']['y'])
        self.r = self._to_units(info['geometry']['radius'])
        self.clockWise = info['geometry']['clockWise']

    def __repr__(self) -> str:
        return f'skCircle(sketch, "{self.id}", ' + self.__str__() + ');'

    def __str__(self) -> str:
        base = '{' + f'"center": {self._v(self.x, self.y)}, "radius": {long_round(self.r)} * {self.units}'
        return self._finish(base)


class skEllipse(SketchElement):
    """
    NOTE: "majorRadius", "minorRadius" can not be recovered here, only with .fs file
    """

    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)
        self.x = self._to_units(info['geometry']['center2d']['x'])
        self.y = self._to_units(info['geometry']['center2d']['y'])
        self.majorAxis = (info['geometry']['majorAxis2d']['x'], info['geometry']['majorAxis2d']['y'])
        self.majorRadius = None
        self.minorRadius = None
        self.no_duplicates = True

    def add_radius(self, major, minor) -> None:
        self.majorRadius = self._to_units(major)
        self.minorRadius = self._to_units(minor)

    def __repr__(self) -> str:
        return f'skEllipse(sketch, "{self.id}", ' + self.__str__() + ');'

    def __str__(self) -> str:
        base = '{' + f'"center": {self._v(self.x, self.y)}'
        base += f', "majorRadius": {long_round(self.majorRadius)} * {self.units}'
        base += f', "minorRadius": {long_round(self.minorRadius)} * {self.units}'
        base += f', "majorAxis": {self.vec}({long_round(self.majorAxis[0])}, {long_round(self.majorAxis[1])})'
        return self._finish(base)


class skLineSegment(SketchElement):
    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)
        self.start_x = self._to_units(info['startPosition2d']['x'])
        self.start_y = self._to_units(info['startPosition2d']['y'])
        self.end_x = self._to_units(info['endPosition2d']['x'])
        self.end_y = self._to_units(info['endPosition2d']['y'])

    def __repr__(self) -> str:
        return f'skLineSegment(sketch, "{self.id}", ' + self.__str__() + ');'

    def __str__(self) -> str:
        base = '{' + f'"start": {self._v(self.start_x, self.start_y)}, "end": {self._v(self.end_x, self.end_y)}'
        return self._finish(base)


class skArc(SketchElement):
    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)
        self.start_x = self._to_units(info['startPosition2d']['x'])
        self.start_y = self._to_units(info['startPosition2d']['y'])
        self.mid_x = self._to_units(info['midPosition2d']['x'])
        self.mid_y = self._to_units(info['midPosition2d']['y'])
        self.end_x = self._to_units(info['endPosition2d']['x'])
        self.end_y = self._to_units(info['endPosition2d']['y'])

    def __repr__(self) -> str:
        return f'skArc(sketch, "{self.id}", ' + self.__str__() + ');'

    def __str__(self) -> str:
        base = (
            '{'
            + f'"start": {self._v(self.start_x, self.start_y)}, "mid": {self._v(self.mid_x, self.mid_y)}, "end": {self._v(self.end_x, self.end_y)}'
        )
        return self._finish(base)


class skText(SketchElement):
    """
    NOTE: font can not be recovered here, only with .fs file
    skText params do not work correctly if text is rotated,
    initial guess option is used instead
    """

    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)
        self.start_x = self._to_units(info['lowerLeftCornerPosition2d']['x'])
        self.start_y = self._to_units(info['lowerLeftCornerPosition2d']['y'])
        self.dir_x = self._to_units(info['baselineDirection2d']['x'])
        self.dir_y = self._to_units(info['baselineDirection2d']['y'])
        self.height = self._to_units(info['height'])
        # pts = recover_all_rectangle_points([self.start_x, self.start_y], [self.dir_x, self.dir_y], self.height)
        # self.start_x = pts['upper_left'][0]
        # self.start_y = pts['upper_left'][1]
        # self.end_x = pts['lower_right'][0]
        # self.end_y = pts['lower_right'][1]
        self.text = info['textString'].replace('\n', '\\n').replace("'", "\\'").replace('"', '\\"')
        self.mirrorHorizontal = False
        self.mirrorVertical = False
        self.fontName = 'OpenSans-Bold.ttf'

    def __repr__(self) -> str:
        return f'skText(sketch, "{self.id}", ' + self.__str__() + ');'

    def __str__(self) -> str:
        # base = '{' + f'"lowerLeftCornerPosition2d": {self.vec}({long_round(self.start_x)}, {long_round(self.start_y)}) * {self.units}'
        # base += f', "baselineDirection2d": {self.vec}({long_round(self.dir_x)}, {long_round(self.dir_y)}) * {self.units}'
        # base += f', "height": {long_round(self.height)} * {self.units}'
        base = '{' + f' "text": "{self.text}"'
        base += f', "fontName": "{self.fontName}"'
        return self._finish(base)

    def add_params(self, params: dict) -> None:
        self.fontName = params['fontName']
        mirrorHorizontal = params.get('mirrorHorizontal')
        if mirrorHorizontal is not None:
            self.mirrorHorizontal = mirrorHorizontal
        mirrorVertical = params.get('mirrorVertical')
        if mirrorVertical is not None:
            self.mirrorVertical = mirrorVertical
        # secondCorner = params.get('secondCorner')
        # if secondCorner is not None:
        #     self.end_x = self.start_x + self._to_units(secondCorner[0])
        #    self.end_y = self.start_y + self._to_units(secondCorner[1]) #+ self.height

    def add_initial_guess(self, params: list) -> None:
        """Adds initial guess parameters (for JSON format only)

        Args:
            params: a list containing [lowerLeftCorner_point_x, lowerLeftCorner_point_y, direction_x, direction_y, height]
        """
        self.lowerLeftCorner_point_x = self._to_units(params[0])
        self.lowerLeftCorner_point_y = self._to_units(params[1])
        self.direction_x = params[2]
        self.direction_y = params[3]
        self.height = self._to_units(params[4])


class skInterpolatedSpline(SketchElement):
    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)
        if info.get('skipInit'):
            return
        geometry = info['geometry']
        if not (geometry['startDerivative2d']['x'] == 0.0 and geometry['startDerivative2d']['y'] == 0.0):
            self.startDerivative2d = (
                self._to_units(geometry['startDerivative2d']['x']),
                self._to_units(geometry['startDerivative2d']['y']),
            )
        else:
            self.startDerivative2d = None
        if not (geometry['endDerivative2d']['x'] == 0.0 and geometry['endDerivative2d']['y'] == 0.0):
            self.endDerivative2d = (
                self._to_units(geometry['endDerivative2d']['x']),
                self._to_units(geometry['endDerivative2d']['y']),
            )
        else:
            self.endDerivative2d = None
        if not (geometry['startHandlePosition2d']['x'] == 0.0 and geometry['startHandlePosition2d']['y'] == 0.0):
            self.startHandlePosition2d = (
                self._to_units(geometry['startHandlePosition2d']['x']),
                self._to_units(geometry['startHandlePosition2d']['y']),
            )
        else:
            self.startHandlePosition2d = None
        if not (geometry['endHandlePosition2d']['x'] == 0.0 and geometry['endHandlePosition2d']['y'] == 0.0):
            self.endHandlePosition2d = (
                self._to_units(geometry['endHandlePosition2d']['x']),
                self._to_units(geometry['endHandlePosition2d']['y']),
            )
        else:
            self.endHandlePosition2d = None
        self.periodic = geometry['isPeriodic']
        self.points = []
        for p in geometry['interpolationPoints2d']:
            self.points.append((self._to_units(p['x']), self._to_units(p['y'])))
        # close the loop manually
        if self.points[0] != self.points[-1] and self.periodic:
            self.points.append(self.points[0])

    def add_points(self, pts: dict) -> None:
        # already initialized
        if hasattr(self, 'points') and len(self.points) > 0:
            return
        self.points = []
        self.periodic = False
        self.startDerivative2d = None
        self.endDerivative2d = None
        num_of_points = len(pts[2:]) // 2
        points = pts[2 : int(2 + num_of_points * 2)]
        for i in range(0, len(points), 2):
            self.points.append((self._to_units(points[i]), self._to_units(points[i + 1])))
        # if self.points[0] != self.points[-1] and self.periodic:
        #     self.points.append(self.points[0])

    def __repr__(self) -> str:
        return f'skFitSpline(sketch, "{self.id}", ' + self.__str__() + ');'

    def __str__(self) -> str:
        base = '{' + '"points": ' + self._points_str()
        if not self.periodic:
            if self.startDerivative2d is not None:
                base += (
                    f', "startDerivative": {self._v(self.startDerivative2d[0], self.startDerivative2d[1], "vector")}'
                )
            if self.endDerivative2d is not None:
                base += f', "endDerivative": {self._v(self.endDerivative2d[0], self.endDerivative2d[1], "vector")}'
        return self._finish(base)


class skInterpolatedSplineSegment(skInterpolatedSpline):
    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)


class skSplineSegment(SketchElement):
    """
    NOTE: points can not be recovered with API, only with .fs file
    """

    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)
        self.points = []
        self.periodic = False
        self.no_duplicates = True

    def add_points(self, pts: dict) -> None:
        num_of_points = pts[3]
        points = pts[4 : int(4 + num_of_points * 2)]
        for i in range(0, len(points), 2):
            self.points.append((self._to_units(points[i]), self._to_units(points[i + 1])))
        if self.points[0] != self.points[-1] and self.periodic:
            self.points.append(self.points[0])

    def __repr__(self) -> str:
        return f'skFitSpline(sketch, "{self.id}", ' + self.__str__() + ');'

    def __str__(self) -> str:
        base = '{' + '"points": ' + self._points_str()
        return self._finish(base)


class skEllipticalArc(SketchElement):
    """
    NOTE: parameters fully recovered in initial guess
    """

    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)
        geometry = info['geometry']
        self.center = (self._to_units(geometry['center2d']['x']), self._to_units(geometry['center2d']['y']))
        self.majorAxis = (geometry['majorAxis2d']['x'], geometry['majorAxis2d']['y'])
        self.start_parameter = info['startParameter']
        self.end_parameter = info['endParameter']

    def __repr__(self) -> str:
        return f'skEllipticalArc(sketch, "{self.id}", ' + self.__str__() + ');'

    def __str__(self) -> str:
        base = '{'
        if self.construction:
            base += '"construction": true'
        base += '}'
        return base

    def add_initial_guess(self, params: list) -> None:
        """Adds initial guess parameters (for JSON format only)

        Args:
            params: a list containing [center_x, center_y, majorAxis_x, majorAxis_y, majorRadius, minorRadius, startParameter, endParameter]
        """
        self.majorRadius = self._to_units(params[4])
        self.minorRadius = self._to_units(params[5])
        self.startParameter = params[6]
        self.endParameter = params[7]


class skBezier(SketchElement):
    """
    NOTE: points can not be recovered with API, only with .fs file
    TODO: check how it works on more samples
    """

    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)
        self.points = []
        self.no_duplicates = True

    def add_points(self, pts: dict, params: dict) -> None:
        num_of_points = pts[4]
        points = pts[5 : int(5 + num_of_points * 2)]
        for i in range(0, len(points), 2):
            self.points.append((self._to_units(points[i]), self._to_units(points[i + 1])))
        # manually close the loop
        if self.points[0] != self.points[-1] and params['geometryIsPeriodic']:
            self.points.append(self.points[0])

    def __repr__(self) -> str:
        return f'skBezier(sketch, "{self.id}", ' + self.__str__() + ');'

    def __str__(self) -> str:
        base = '{' + '"points": ' + self._points_str()
        return self._finish(base)


class skSpline(skSplineSegment):
    """
    NOTE: Can not be recovered with API, only with .fs file
    """

    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)
        self.periodic = True


class skImage(SketchElement):
    """
    NOTE: This operation is not supported
    """

    def __init__(self, info: dict, **kwargs) -> None:
        super().__init__(info, **kwargs)


_SK_CLASSES = {
    'skPoint': skPoint,
    'skCircle': skCircle,
    'skEllipse': skEllipse,
    'skLineSegment': skLineSegment,
    'skArc': skArc,
    'skText': skText,
    'skInterpolatedSpline': skInterpolatedSpline,
    'skInterpolatedSplineSegment': skInterpolatedSplineSegment,
    'skSplineSegment': skSplineSegment,
    'skEllipticalArc': skEllipticalArc,
    'skBezier': skBezier,
    'skSpline': skSpline,
    'skImage': skImage,
}


class Sketch:
    """Container of a sketch's parsed geometry, with duplicate/redundancy cleanup."""

    def __init__(self, sketch_info: dict, geometry_check: bool = True) -> None:
        self.with_duplicates = False
        self.name = sketch_info['name']
        self.featureId = sketch_info['featureId']
        self.entities = {}
        for entity in sketch_info['entities']:
            self._add_entity(entity)

        if geometry_check:
            self.line_check()
            self.delete_redundant_points()
            self.duplicate_detection()

    def line_check(self) -> None:
        """Reconstruct line segments that survive only as their .start/.end points."""
        lost_lines = {}
        for e_name, e in self.entities.items():
            if isinstance(e, skPoint) and e_name.endswith('.start'):
                assert self.entities.get(e_name[:-6] + '.end') is not None
                if self.entities.get(e_name[:-6]) is None:
                    entity = {
                        'sketchEntityType': 'skLineSegment',
                        'startPosition2d': {'x': 0, 'y': 0},
                        'endPosition2d': {'x': 0, 'y': 0},
                        'isConstruction': e.construction,
                        'sketchEntityId': e_name[:-6],
                    }
                    line = skLineSegment(entity)
                    line.start_x = self.entities[e_name].x
                    line.start_y = self.entities[e_name].y
                    line.end_x = self.entities[e_name[:-6] + '.end'].x
                    line.end_y = self.entities[e_name[:-6] + '.end'].y
                    lost_lines[e_name[:-6]] = line
        for k, v in lost_lines.items():
            self.entities[k] = v

    def delete_redundant_points(self) -> None:
        """Drop endpoint sub-points whose parent segment/arc is already present."""
        redundant_keys = []
        for e_name, e in self.entities.items():
            if isinstance(e, skPoint) and (e_name.endswith('.start') or e_name.endswith('.end')):
                corresponding_element = self.entities.get('.'.join(e_name.split('.')[:-1]))
                if corresponding_element is not None:
                    redundant_keys.append(e_name)
        for key in redundant_keys:
            self.entities.pop(key)

    def duplicate_detection(self) -> None:
        """Cross-link geometrically identical entities via their duplicate_id."""
        entities = list(self.entities.items())
        for entity_index_1 in range(len(entities)):
            e_name_1, e_obj_1 = entities[entity_index_1]
            if e_obj_1.duplicate_id is not None or e_obj_1.no_duplicates:
                continue
            params_1 = vars(e_obj_1).copy()
            params_1.pop('id')
            if isinstance(e_obj_1, skCircle):
                params_1.pop('clockWise')
            for entity_index_2 in range(entity_index_1 + 1, len(entities)):
                e_name_2, e_obj_2 = entities[entity_index_2]
                if (
                    e_obj_1.id.split('.')[0] == e_obj_2.id.split('.')[0]
                    or e_obj_2.duplicate_id is not None
                    or e_obj_2.no_duplicates
                ):
                    continue
                # has_different_direction = ( # TODO test this check
                #     'Mirror' in e_name_1 and 'Mirror' not in e_name_2 or
                #     'Mirror' in e_name_2 and 'Mirror' not in e_name_1
                # )
                # if has_different_direction:
                #     continue
                if type(e_obj_1) == type(e_obj_2):
                    is_duplicate = True
                    params_2 = vars(e_obj_2).copy()
                    params_2.pop('id')
                    if isinstance(e_obj_2, skCircle):
                        params_2.pop('clockWise')
                    for param_name in params_1.keys():
                        v1 = params_1[param_name]
                        v2 = params_2[param_name]
                        v1 = long_round(v1) if isinstance(v1, float) else v1
                        v2 = long_round(v2) if isinstance(v2, float) else v2
                        if v1 != v2:
                            is_duplicate = False
                            break
                    if is_duplicate:
                        self.with_duplicates = True
                        e_obj_1.duplicate_id = e_obj_2.id
                        e_obj_2.duplicate_id = e_obj_1.id

    def _add_entity(self, entity: dict) -> None:
        sk_type = entity['sketchEntityType']
        sk_class = _SK_CLASSES.get(sk_type)
        if sk_class is None:
            raise NameError(f"name '{sk_type}' is not defined")
        self.entities[entity['sketchEntityId']] = sk_class(entity)

    def __str__(self) -> str:
        result = ''
        for v in self.entities.values():
            result += repr(v) + '\n'
        return result
